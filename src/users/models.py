from datetime import date, datetime
from enum import Enum as PyEnum
from uuid import uuid4, UUID

from sqlalchemy import Boolean, Date as PGDate, DateTime as PGDateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from src.database import Base


class GenderEnum(str, PyEnum):
    MALE = 'MALE'
    FEMALE = 'FEMALE'

class RoleEnum(str, PyEnum):
    USER = 'USER'
    ADMIN = 'ADMIN'

class UserModel(Base):
    __tablename__ = 'users'

    id: Mapped[UUID] = mapped_column(
        PGUUID,
        primary_key=True,
        unique=True,
        nullable=False,
        default=uuid4,
        index=True
    )

    email: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True
    )

    surname: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True
    )

    birthday: Mapped[date] = mapped_column(
        PGDate,
        nullable=False,
        index=True
    )

    gender: Mapped[GenderEnum] = mapped_column(
        Enum(GenderEnum, name='gender_enum'),
        nullable=True,
        index=True
    )

    role: Mapped[RoleEnum] = mapped_column(
        Enum(RoleEnum, name='role_enum'),
        nullable=False,
        server_default=RoleEnum.USER.value
    )

    is_email_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default='false'
    )

    is_online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default='false'
    )

    last_visit: Mapped[datetime] = mapped_column(
        PGDateTime,
        nullable=False,
        server_default=func.now()
    )

    password: Mapped[str] = mapped_column(
        String(60),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        PGDateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        PGDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )