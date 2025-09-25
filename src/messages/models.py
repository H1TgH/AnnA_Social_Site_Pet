from uuid import uuid4, UUID
from datetime import datetime

from sqlalchemy import ForeignKey, String, DateTime, func, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ARRAY

from src.database import Base

class ConversationModel(Base):
    __tablename__ = 'conversations'

    id: Mapped[UUID] = mapped_column(
        PGUUID,
        primary_key=True,
        default=uuid4
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    participants = relationship(
        'ConversationParticipantModel',
        back_populates='conversation',
        cascade='all, delete-orphan'
    )

    last_message_id: Mapped[UUID] = mapped_column(
        PGUUID,
        ForeignKey('messages.id', ondelete='SET NULL'),
        nullable=True
    )

    last_message = relationship(
            'MessageModel',
            foreign_keys=[last_message_id],
            uselist=False
        )

    messages = relationship(
        'MessageModel',
        back_populates='conversation',
        foreign_keys='MessageModel.conversation_id'
    )

class ConversationParticipantModel(Base):
    __tablename__ = 'conversation_participants'

    id: Mapped[UUID] = mapped_column(
        PGUUID,
        primary_key=True,
        default=uuid4
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID,
        ForeignKey('conversations.id', ondelete='CASCADE'),
        index=True,
        nullable=False
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID,
        ForeignKey('users.id', ondelete='CASCADE'),
        index=True,
        nullable=False
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    conversation = relationship('ConversationModel', back_populates='participants')
    user = relationship('UserModel')

    __table_args__ = (
        UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_user'),
    )

class MessageModel(Base):
    __tablename__ = 'messages'

    id: Mapped[UUID] = mapped_column(
        PGUUID,
        primary_key=True,
        default=uuid4
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID,
        ForeignKey('conversations.id', ondelete='CASCADE'),
        index=True,
        nullable=False
    )

    sender_id: Mapped[UUID] = mapped_column(
        PGUUID,
        ForeignKey('users.id', ondelete='CASCADE'),
        index=True,
        nullable=False
    )

    text: Mapped[str] = mapped_column(
        String(2000),
        nullable=False
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    deleted_for: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID),
        default=list,
        nullable=False
    )

    is_edited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True
    )

    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    conversation = relationship(
        'ConversationModel',
        back_populates='messages',
        foreign_keys=[conversation_id]
    )
    sender = relationship('UserModel', backref='messages')

    __table_args__ = (
        Index('ix_messages_conversation_created', 'conversation_id', 'created_at'),
    )
