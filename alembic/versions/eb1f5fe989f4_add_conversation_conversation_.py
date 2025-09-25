"""Add conversation, conversation participants and message models

Revision ID: eb1f5fe989f4
Revises: 1140d79d4c2f
Create Date: 2025-09-10 11:19:13.265259
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eb1f5fe989f4'
down_revision: Union[str, None] = '1140d79d4c2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаем таблицу conversations без FK на last_message_id
    op.create_table(
        'conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_message_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Создаем таблицу messages
    op.create_table(
        'messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('sender_id', sa.UUID(), nullable=False),
        sa.Column('text', sa.String(length=2000), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deleted_for', postgresql.ARRAY(sa.UUID()), nullable=False, server_default='{}'),
        sa.Column('is_edited', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Создаем индексы для messages
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False)
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False)
    op.create_index('ix_messages_created_at', 'messages', ['created_at'], unique=False)
    op.create_index('ix_messages_sender_id', 'messages', ['sender_id'], unique=False)

    # Создаем таблицу conversation_participants
    op.create_table(
        'conversation_participants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_user')
    )

    op.create_index('ix_conversation_participants_conversation_id', 'conversation_participants', ['conversation_id'], unique=False)
    op.create_index('ix_conversation_participants_user_id', 'conversation_participants', ['user_id'], unique=False)

    # После создания обеих таблиц создаем FK на last_message_id
    op.create_foreign_key(
        'fk_conversations_last_message',
        'conversations', 'messages',
        ['last_message_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Сначала удаляем FK на last_message_id
    op.drop_constraint('fk_conversations_last_message', 'conversations', type_='foreignkey')

    # Удаляем таблицу conversation_participants
    op.drop_index('ix_conversation_participants_user_id', table_name='conversation_participants')
    op.drop_index('ix_conversation_participants_conversation_id', table_name='conversation_participants')
    op.drop_table('conversation_participants')

    # Удаляем таблицу messages и ее индексы
    op.drop_index('ix_messages_sender_id', table_name='messages')
    op.drop_index('ix_messages_created_at', table_name='messages')
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_table('messages')

    # Удаляем таблицу conversations
    op.drop_table('conversations')
