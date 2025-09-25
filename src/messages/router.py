import os
from uuid import UUID
from datetime import timedelta, datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
import redis.asyncio as redis

from src.database import SessionDep
from src.minio import minio_client
from src.messages.schemas import MessageCreateSchema
from src.messages.models import MessageModel, ConversationModel, ConversationParticipantModel
from src.users.models import UserModel
from src.users.utils import get_current_user


redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
r = redis.from_url(f'{redis_url}/1')

messages_router = APIRouter()

@messages_router.post('/api/v1/messages')
async def send_message(
    message: MessageCreateSchema,
    session: SessionDep,
    conversation_id: UUID = Query(...),
    sender: UserModel = Depends(get_current_user)
):
    new_message = MessageModel(
        conversation_id=conversation_id,
        sender_id=sender.id,
        text=message.text
    )
    session.add(new_message)
    await session.flush()

    conversation = await session.get(ConversationModel, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Conversation not found'
        )
    conversation.last_message_id = new_message.id

    await session.commit()

    return {
        'message_id': new_message.id,
        'text': new_message.text,
        'sender_id': new_message.sender_id,
        'created_at': new_message.created_at
    }

@messages_router.get('/api/v1/messages')
async def get_user_conversations(
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    result = await session.execute(
        select(ConversationModel)
        .options(
            selectinload(ConversationModel.participants)
            .selectinload(ConversationParticipantModel.user)
        )
        .join(ConversationParticipantModel)
        .where(ConversationParticipantModel.user_id == user.id)
    )
    conversations = result.scalars().all()

    response = []
    for conv in conversations:
        last_msg = None
        if conv.last_message_id:
            last_msg_result = await session.get(MessageModel, conv.last_message_id)
            if last_msg_result:
                last_msg = {
                    'id': last_msg_result.id,
                    'text': last_msg_result.text,
                    'sender_id': last_msg_result.sender_id,
                    'created_at': last_msg_result.created_at
                }

        participants_result = []
        for p in conv.participants:
            if p.user.id == user.id:
                continue

            status = await r.get(f'user:{p.user.id}:status') or b'offline'
            status_str = status.decode() if isinstance(status, bytes) else str(status)
            
            avatar_url = None
            if p.user.avatar_url is not None:
                avatar_url = minio_client.presigned_get_object(
                    bucket_name='avatars',
                    object_name=p.user.avatar_url,
                    expires=timedelta(minutes=10)
                )

            participants_result.append({
                'id': p.user.id,
                'name': p.user.name,
                'surname': p.user.surname,
                'avatar_url': avatar_url,
                'status': status_str
            })

        response.append({
            'conversation_id': conv.id,
            'participants': participants_result,
            'last_message': last_msg
        })

    return response

@messages_router.get('/api/v1/messages/{conversation_id}')
async def get_conversation_history(
    conversation_id: UUID,
    session: SessionDep,
    user: UserModel = Depends(get_current_user),
    limit: int = Query(50, gt=0, le=100),
    cursor: datetime | None = Query(None)
):
    participant_result = await session.execute(
        select(ConversationParticipantModel)
        .where(
            ConversationParticipantModel.conversation_id == conversation_id,
            ConversationParticipantModel.user_id == user.id
        )
    )
    participant = participant_result.scalars().first()
    if not participant:
        raise HTTPException(status_code=403, detail='Access denied to this conversation')

    query = select(MessageModel).where(
        MessageModel.conversation_id == conversation_id,
        ~MessageModel.deleted_for.contains([user.id])
    )

    if cursor:
        query = query.where(MessageModel.created_at < cursor)

    query = query.order_by(MessageModel.created_at.desc()).limit(limit + 1)

    messages_result = await session.execute(query)
    messages = messages_result.scalars().all()

    if len(messages) > limit:
        messages = messages[:-1]
        next_cursor = messages[-1].created_at.isoformat()
    else:
        next_cursor = None

    return {
        'messages': [
            {
                'id': m.id,
                'sender_id': m.sender_id,
                'text': m.text,
                'is_read': m.is_read,
                'created_at': m.created_at
            } for m in messages
        ],
        'next_cursor': next_cursor,
        'has_more': next_cursor is not None
    }

@messages_router.delete('/api/v1/messages/{message_id}/self')
async def delete_message_for_self(
    message_id: UUID,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    message = await session.get(MessageModel, message_id)
    if not message:
        raise HTTPException(404, 'Message not found')

    if user.id not in message.deleted_for:
        message.deleted_for.append(user.id)
        await session.commit()

    return {'detail': 'Message deleted for self'}

@messages_router.delete('/api/v1/messages/{message_id}/all')
async def delete_message_for_all(
    message_id: UUID,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    message = await session.get(MessageModel, message_id)
    if not message:
        raise HTTPException(404, 'Message not found')

    if message.sender_id != user.id:
        raise HTTPException(403, 'Only sender can delete for all')

    await session.delete(message)
    await session.commit()

    return {'detail': 'Message deleted for all'}

@messages_router.get('/api/v1/conversation')
async def get_or_create_conversation_id(
    session: SessionDep,
    receiver_id: UUID = Query(...),
    sender: UserModel = Depends(get_current_user)
):
    receiver_result = await session.execute(
        select(UserModel).where(UserModel.id == receiver_id)
    )
    receiver = receiver_result.scalar_one_or_none()
    if receiver is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Receiver not found'
        )

    subquery = (
        select(ConversationParticipantModel.conversation_id)
        .where(ConversationParticipantModel.user_id.in_([sender.id, receiver_id]))
        .group_by(ConversationParticipantModel.conversation_id)
        .having(func.count(ConversationParticipantModel.user_id) == 2)
    )

    result = await session.execute(
        select(ConversationModel).where(ConversationModel.id.in_(subquery))
    )
    conversation = result.scalars().first()

    if conversation:
        return {'conversation_id': conversation.id}

    conversation = ConversationModel()
    session.add(conversation)
    await session.flush()

    session.add_all([
        ConversationParticipantModel(conversation_id=conversation.id, user_id=sender.id),
        ConversationParticipantModel(conversation_id=conversation.id, user_id=receiver_id)
    ])
    await session.commit()

    return {'conversation_id': conversation.id}
