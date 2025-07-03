from datetime import timedelta
from email.message import EmailMessage
import os

from aiosmtplib import send
from fastapi import APIRouter, HTTPException, status, Depends, Query
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.database import SessionDep
from src.users.models import UserModel
from src.users.schemas import RegistrationSchema, LoginSchema, PasswordResetSendEmailSchema, PasswordResetSchema
from src.users.utils import hash_password, create_access_token, verify_password
from src.users.utils import SECRET_KEY, ALGORITHM
from src.email_service.utils import send_confirmation_email


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

    await send_confirmation_email(user)

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
    session: SessionDep
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

    token = create_access_token(
        {'sub': str(user.id)},
        expires_delta=timedelta(days=1)
    )

    return {
        'access_token': token, 
        'token_type': 'bearer'
    }

@users_router.post('/api/v1/users/password-reset', tags=['Users'])
async def send_reset_password_url(
    email: PasswordResetSendEmailSchema,
    session: SessionDep
):
    user = await session.execute(
        select(UserModel)
        .where(email.email == UserModel.email)
    )
    result = user.scalar_one_or_none()

    if result is None:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User with this email not found'
        )
    
    token = create_access_token(
        {'sub': str(user.id)},
        expires_delta=timedelta(minutes=20)
    )

    frontend_base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    reset_url = f'{frontend_base_url}/password-reset?token={token}'

    message = EmailMessage()
    message['From'] = os.getenv('SMTP_FROM', 'no-reply@example.com')
    message['To'] = user.email
    message['Subject'] = 'Reset your password'

    message.set_content(
        f'Hello, {user.name}!\n\n'
        f'Please reset your password by clicking the link below:\n\n'
        f'{reset_url}\n\n'
        f'This link will expire in 20 minutes.\n'
    )

    await send(
        message,
        hostname=os.getenv('SMTP_HOST', 'smtp.gmail.com'),
        port=int(os.getenv('SMTP_PORT', 587)),
        username=os.getenv('SMTP_USER'),
        password=os.getenv('SMTP_PASSWORD'),
        start_tls=True
    )

@users_router.post('api/v1/users/create-password', tags=['Users'])
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
    