from datetime import date
from typing import Optional

from pydantic import BaseModel

from src.users.models import GenderEnum


class RegistrationSchema(BaseModel):
    email: str
    password: str
    name: str
    surname: str
    birthday: date
    gender: GenderEnum | None = None

class LoginSchema(BaseModel):
    email: str
    password: str

class TokenSchema(BaseModel):
    access_token: str
    token_type: str = 'bearer'

class PasswordResetSendEmailSchema(BaseModel):
    email: str

class PasswordResetSchema(BaseModel):
    new_password: str

class AvatarUpdateSchema(BaseModel):
    object_name: str

class UserDataUpdateSchema(BaseModel):
    name: Optional[str] = None
    surname: Optional[str] = None
    status: Optional[str] = None
    birthday: Optional[date] = None
    gender: Optional[str] = None

    class Config:
        json_encoders = {
            date: lambda date: date.isoformat()
        }
