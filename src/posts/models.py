from datetime import datetime
from uuid import uuid4, UUID

from sqlalchemy import ForeignKey, String, Text, SmallInteger, DateTime, func, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from src.database import Base


class PostsModel(Base):
    __tablename__ = 'posts'

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    images = relationship('PostImagesModel', back_populates='post')
    likes = relationship('PostLikesModel', back_populates='post')
    comments = relationship('PostCommentsModel', back_populates='post')

    __table_args__ = (
        Index('ix_posts_user_created', 'user_id', 'created_at'),
    )


class PostImagesModel(Base):
    __tablename__ = 'post_images'

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid4,
    )

    post_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('posts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    image_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    position: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    post = relationship('PostsModel', back_populates='images')

    __table_args__ = (
        UniqueConstraint('post_id', 'position', name='uq_post_images_post_position'),
        Index('ix_post_images_post_position', 'post_id', 'position'),
        CheckConstraint('position BETWEEN 1 AND 10', name='ck_post_images_position_1_10'),
    )


class PostLikesModel(Base):
    __tablename__ = 'post_likes'

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid4,
    )

    post_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('posts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    post = relationship('PostsModel', back_populates='likes')

    __table_args__ = (
        UniqueConstraint('post_id', 'user_id', name='uq_post_likes_post_user'),
        Index('ix_post_likes_user', 'user_id'),
    )


class PostCommentsModel(Base):
    __tablename__ = 'post_comm'

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid4,
    )

    post_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('posts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)

    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('post_comm.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    post = relationship('PostsModel', back_populates='comments')
    replies = relationship('PostCommentsModel', back_populates='parent', remote_side=[id])
    parent = relationship('PostCommentsModel', back_populates='replies')


    __table_args__ = (
        Index('ix_post_comm_post_created', 'post_id', 'created_at'),
        Index('ix_post_comm_parent', 'parent_id'),
    )
