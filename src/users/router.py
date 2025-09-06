from datetime import timedelta, date, datetime
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException, status, Depends, Query, Response
from jose import JWTError, jwt
from sqlalchemy import select, update, or_, and_
from sqlalchemy.exc import IntegrityError

from src.database import SessionDep
from src.minio import minio_client
from src.users.models import UserModel
from src.users.schemas import RegistrationSchema, LoginSchema, PasswordResetSendEmailSchema, PasswordResetSchema, AvatarUpdateSchema, UserDataUpdateSchema
from src.users.utils import hash_password, create_access_token, create_refresh_token, verify_password, get_current_user
from src.users.utils import SECRET_KEY, ALGORITHM
from src.email_service.tasks import send_confirmation_email_task, send_password_reset_email_task


users_router = APIRouter()

@users_router.post('/api/v1/public/register', tags=['Users'])
async def register_user(
    data: RegistrationSchema,
    session: SessionDep
):
    user_exists = await session.execute(
        select(UserModel)
        .where(UserModel.email == data.email)
    )
    if user_exists.scalar():
        raise HTTPException(
            status_code=400, 
            detail='Email already registered'
        )

    hashed_password = hash_password(data.password)

    user = UserModel(
        email=data.email,
        password=hashed_password,
        name=data.name,
        surname=data.surname,
        birthday=data.birthday,
        gender=data.gender,
    )
    session.add(user)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=400, 
            detail='User creation failed'
        )

    token = create_access_token({'sub': str(user.id)}, expires_delta=timedelta(hours=2))

    send_confirmation_email_task.delay(user.id, user.email, user.name)

    return {'message': 'Registration successful. Please confirm your email.'}

@users_router.get('/api/v1/public/confirm-email', tags=['Users'])
async def confirm_email(
    session: SessionDep,
    token: str = Query(...)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise HTTPException(
                status_code=400, 
                detail='Invalid token'
            )
    except JWTError:
        raise HTTPException(
            status_code=400, 
            detail='Invalid or expired token'
        )

    result = await session.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
    )
    user: UserModel | None = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=400, 
            detail='User not found'
        )

    if user.is_email_confirmed:
        return {'message': 'Email already confirmed'}

    user.is_email_confirmed = True
    await session.commit()

    return {'message': 'Email successfully confirmed'}

@users_router.post('/api/v1/public/login', tags=['Users'])
async def login_user(
    credentials: LoginSchema,
    session: SessionDep,
    response: Response
):
    result = await session.execute(
        select(UserModel)
        .where(UserModel.email == credentials.email)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(credentials.password, user.password):
        raise HTTPException(
            status_code=401, 
            detail='Invalid email or password'
        )

    if not user.is_email_confirmed:
        raise HTTPException(
            status_code=403, 
            detail='Please confirm your email first'
        )

    access_token = create_access_token(
        {
            'sub': str(user.id)
        },
        expires_delta=timedelta(minutes=30)
    )
    refresh_token = create_refresh_token(
        {
            'sub': str(user.id),
        },
        expires_delta=timedelta(days=7)
    )

    response.set_cookie(
        key='access_token',
        value=access_token,
        httponly=True,
        max_age=30*60,
        path='/'
    )
    response.set_cookie(
        key='refresh_token',
        value=refresh_token,
        httponly=True,
        max_age=60*60*24*7,
        path='/'
    )

    return {'message': 'Login successful'}

@users_router.post('/refresh_token', tags=['auth'])
async def refresh_token(refresh_token: str = Cookie(...)):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get('type') != 'refresh':
            raise HTTPException(status_code=401, detail='Invalid token type')
        
        user_id = payload.get('sub')
        if not user_id:
            raise HTTPException(status_code=401, detail='Invalid token payload')

        new_access_token = create_access_token({'sub': user_id}, expires_delta=timedelta(minutes=15))
        return {'access_token': new_access_token}

    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid or expired refresh token')

@users_router.post('/api/v1/users/password-reset', tags=['Users'])
async def send_reset_password_url(
    email: PasswordResetSendEmailSchema,
    session: SessionDep
):
    user_result = await session.execute(
        select(UserModel)
        .where(email.email == UserModel.email)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User with this email not found'
        )

    send_password_reset_email_task.delay(str(user.id), user.email, user.name)

    return {'message': 'Password reset email sent if the email exists.'}

@users_router.post('/api/v1/users/update-password', tags=['Users'])
async def create_new_password(
    new_password: PasswordResetSchema,
    session: SessionDep,
    token: str = Query(...)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise HTTPException(
                status_code=400, 
                detail='Invalid token'
            )
    except JWTError:
        raise HTTPException(
            status_code=400, 
            detail='Invalid or expired token'
        )

    result = await session.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=400, 
            detail='User not found'
        )

    password = hash_password(new_password.new_password)

    await session.execute(
        update(UserModel)
        .where(UserModel.id == user.id)
        .values(password=password)
    )

    await session.commit()

@users_router.get('/api/v1/users/avatar/upload-url')
async def get_avatar_upload_url(
    user: UserModel = Depends(get_current_user)
):
    object_name = f'avatars/{user.id}.png'
    url = minio_client.presigned_put_object(
        bucket_name = 'avatars',
        object_name=object_name,
        expires=timedelta(minutes=10)
    )

    return {
        'upload_url': url,
        'object_name': object_name
    }

@users_router.post('/api/v1/users/avatar')
async def save_avatar(
    data: AvatarUpdateSchema,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    user.avatar_url = data.object_name
    await session.commit()

    avatar_url = minio_client.presigned_get_object(
        bucket_name='avatars',
        object_name=user.avatar_url,
        expires=timedelta(minutes=10)
    )
    
    return {'avatar_url': avatar_url}

@users_router.get('/api/v1/users/me')
async def get_current_user_profile(
    user: UserModel = Depends(get_current_user)
):
    avatar_url = None
    if user.avatar_url:
        avatar_url = minio_client.presigned_get_object(
            bucket_name='avatars',
            object_name=user.avatar_url,
            expires=timedelta(minutes=10)
        )

    return {
        'id': str(user.id),
        'name': user.name,
        'surname': user.surname,
        'status': user.status,
        'birthday': user.birthday,
        'gender': user.gender,
        'role': user.role,
        'avatar_url': avatar_url
    }

@users_router.get('/api/v1/users/{user_id}')
async def get_user_by_id(
    user_id: str,
    session: SessionDep
):
    user_result = await session.execute(
        select(UserModel)
        .where(UserModel.id==user_id)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User not found'
        )
    
    avatar_url = None
    if user.avatar_url:
        avatar_url = minio_client.presigned_get_object(
            bucket_name='avatars',
            object_name=user.avatar_url,
            expires=timedelta(minutes=10)
        )
    
    return {
        'id': str(user.id),
        'name': user.name,
        'surname': user.surname,
        'status': user.status,
        'birthday': user.birthday,
        'gender': user.gender,
        'role': user.role,
        'avatar_url': avatar_url
    }

@users_router.post('/api/v1/users/logout')
async def logout(response: Response):
    response.delete_cookie(key='access_token', path='/')
    response.delete_cookie(key='refresh_token', path='/')

    return {'message': 'Logged out successfully'}

@users_router.patch('/api/v1/users/me')
async def update_user_data(
    data: UserDataUpdateSchema,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail='No data provided for update'
        )

    result = await session.execute(
        update(UserModel)
        .where(UserModel.id == user.id)
        .values(**update_data)
        .returning(UserModel)
    )
    updated_user = result.scalar_one()
    await session.commit()

    return {
        'id': str(updated_user.id),
        'name': updated_user.name,
        'surname': updated_user.surname,
        'status': updated_user.status,
        'birthday': updated_user.birthday,
        'gender': updated_user.gender,
        'role': updated_user.role,
        'avatar_url': updated_user.avatar_url
    }

@users_router.get('/api/v1/search')
async def search_users(
    session: SessionDep,
    user: UserModel = Depends(get_current_user),
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    cursor: datetime | None = Query(None),
    sex: Literal['MALE', 'FEMALE', 'NULL'] | None = Query(None),
    age_min: int | None = Query(None, ge=0),
    age_max: int | None = Query(None, le=200),
    birthday: date | None = Query(None)
):
    filters = [UserModel.id != user.id]

    full_name = q.lower().split()
    for name in full_name:
        filters.append(
            or_(
                UserModel.name.ilike(f'%{name}%'),
                UserModel.surname.ilike(f'%{name}%')
            )
        )

    if sex and sex == 'NULL':
        filters.append(UserModel.gender == None)
    elif sex is not None:
        filters.append(UserModel.gender == sex)

    today = date.today()
    if age_min is not None:
        max_birthday = today - timedelta(days=age_min*365)
        filters.append(UserModel.birthday <= max_birthday)
    if age_max is not None:
        min_birthday = today - timedelta(days=age_max*365)
        filters.append(UserModel.birthday >= min_birthday)

    if birthday is not None:
        filters.append(UserModel.birthday == birthday)

    if cursor is not None:
        filters.append(UserModel.created_at <= cursor)

    query = select(UserModel).where(and_(*filters)).limit(limit + 1)
    results = await session.execute(query)
    users = results.scalars().all()

    if len(users) > limit:
        next_cursor = users[-1].created_at
        users = users[:-1]
    else:
        next_cursor = None

    response = []
    for user in users:
        if user.avatar_url:
            avatar_url = minio_client.presigned_get_object(
                bucket_name = 'avatars',
                object_name=user.avatar_url,
                expires=timedelta(minutes=10)
            )
        else:
            avatar_url = None
        response.append(
            {
                'id': user.id,
                'name': user.name,
                'surname': user.surname,
                'birthday': user.birthday,
                'avatar_url': avatar_url
            }
        )
        
    return {
        'users': response,
        'next_cursor': next_cursor,
        'has_more': bool(next_cursor)
    }
