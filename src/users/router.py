from datetime import timedelta
from email.message import EmailMessage
import os

from aiosmtplib import send
from fastapi import APIRouter, Cookie, HTTPException, status, Depends, Query, Response
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.database import SessionDep
from src.minio import minio_client
from src.users.models import UserModel
from src.users.schemas import RegistrationSchema, LoginSchema, PasswordResetSendEmailSchema, PasswordResetSchema
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
    object_name: str,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    user.avatar_url = object_name
    await session.commit()
    
    return {'message': 'Avatar saved'}

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
        'email': user.email,
        'name': user.name,
        'surname': user.surname,
        'birthday': user.birthday,
        'gender': user.gender,
        'role': user.role,
        'is_email_confirmed': user.is_email_confirmed,
        'is_online': user.is_online,
        'last_visit': user.last_visit,
        'avatar_url': avatar_url
    }