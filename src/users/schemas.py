from pydantic import BaseModel
from datetime import date

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
