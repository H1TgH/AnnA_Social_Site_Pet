from datetime import datetime, timedelta, timezone
import os

from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from src.database import SessionDep
from src.users.models import UserModel, RoleEnum


SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = 'HS256'

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({'exp': expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({
        'type': 'refresh',
        'exp': expire
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: SessionDep = Depends()
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await session.get(UserModel, user_id)
    if user is None:
        raise credentials_exception

    return user

async def get_current_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    if user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return user