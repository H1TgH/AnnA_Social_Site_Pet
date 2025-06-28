from datetime import timedelta

from fastapi import APIRouter, HTTPException, status, Depends, Query
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.database import SessionDep
from src.users.models import UserModel
from src.users.schemas import RegistrationSchema
from src.users.utils import hash_password, create_access_token
from src.users.utils import SECRET_KEY, ALGORITHM
from src.email_service.utils import send_confirmation_email


users_router = APIRouter()

@users_router.post('/api/v1/public/register', tags=['Users'])
async def register_user(
    data: RegistrationSchema,
    session: SessionDep
):
    user_exists = await session.execute(select(UserModel).where(UserModel.email == data.email))
    if user_exists.scalar():
        raise HTTPException(status_code=400, detail='Email already registered')

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
        raise HTTPException(status_code=400, detail='User creation failed')

    token = create_access_token({'sub': str(user.id)}, expires_delta=timedelta(hours=2))

    await send_confirmation_email(user)

    return {'message': 'Registration successful. Please confirm your email.'}

@users_router.post('/api/v1/public/confirm-email', tags=['Users'])
async def confirm_email(
    session: SessionDep,
    token: str = Query(...)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise HTTPException(status_code=400, detail='Invalid token')
    except JWTError:
        raise HTTPException(status_code=400, detail='Invalid or expired token')

    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user: UserModel | None = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=400, detail='User not found')

    if user.is_email_confirmed:
        return {'message': 'Email already confirmed'}

    user.is_email_confirmed = True
    await session.commit()

    return {'message': 'Email successfully confirmed'}