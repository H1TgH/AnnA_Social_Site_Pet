import os
from datetime import datetime, timezone

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
import redis.asyncio as redis
from sqlalchemy import select

from src.database import SessionDep
from src.users.models import UserModel
from src.messages.models import MessageModel, ConversationParticipantModel, ConversationModel
from src.messages.utils import get_or_create_conversation
from src.ws.utils import get_current_user_ws


chat_ws_router = APIRouter()
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
r = redis.from_url(f'{redis_url}/2')

connections: dict[str, set[WebSocket]] = {}

async def broadcast(conversation_id: str, message: dict):
    if conversation_id not in connections:
        return
    
    disconnected = set()
    for ws in connections[conversation_id].copy():
        try:
            await ws.send_json(message)
        except Exception as e:
            disconnected.add(ws)
    
    if disconnected:
        connections[conversation_id] -= disconnected

async def verify_user_in_conversation(session, user_id, conversation_id):
    result = await session.execute(
        select(ConversationParticipantModel)
        .where(
            ConversationParticipantModel.conversation_id == conversation_id,
            ConversationParticipantModel.user_id == user_id
        )
    )
    return result.scalars().first() is not None

@chat_ws_router.websocket('/api/v1/ws/chat/{conversation_id}')
async def chat_ws(
    conversation_id: str,
    websocket: WebSocket,
    session: SessionDep,
    user: UserModel = Depends(get_current_user_ws)
):
    await websocket.accept()
    
    try:
        if not await verify_user_in_conversation(session, user.id, conversation_id):
            await websocket.close(code=4003, reason='Access denied to conversation')
            return
    except Exception as e:
        await websocket.close(code=4000, reason='Internal server error')
        return

    if conversation_id not in connections:
        connections[conversation_id] = set()
    connections[conversation_id].add(websocket)

    user_key = f'user:{user.id}:status'
    await r.set(user_key, 'online', ex=60)
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=45)
            except asyncio.TimeoutError:
                await r.expire(user_key, 60)
                try:
                    await websocket.send_json({'event': 'ping'})
                except:
                    break
                continue
            except WebSocketDisconnect:
                break

            try:
                await handle_websocket_event(data, session, user, conversation_id, websocket)
            except Exception as e:
                await websocket.send_json({
                    'event': 'error',
                    'message': 'Failed to process message'
                })

    except Exception as e:
        print(f'WebSocket connection error: {e}')
    finally:
        try:
            if conversation_id in connections:
                connections[conversation_id].discard(websocket)
                if not connections[conversation_id]:
                    del connections[conversation_id]
            
            await r.set(f'user:{user.id}:last_seen', datetime.now(timezone.utc).isoformat())
            await r.delete(user_key)
        except Exception as e:
            print(f'Error in WebSocket cleanup: {e}')

async def handle_websocket_event(data, session, user, conversation_id, websocket):
    event_type = data.get('event')
    
    if event_type == 'new_message':
        await handle_new_message(data, session, user, conversation_id)
    elif event_type == 'read_message':
        await handle_read_message(data, session, user, conversation_id)
    elif event_type == 'edit_message':
        await handle_edit_message(data, session, user, conversation_id)
    elif event_type == 'delete_message':
        await handle_delete_message(data, session, user, conversation_id, websocket)

async def handle_new_message(data, session, user, conversation_id):
    text = data.get('text', '').strip()
    if not text:
        return

    message = MessageModel(
        conversation_id=conversation_id,
        sender_id=user.id,
        text=text
    )
    session.add(message)
    await session.flush()
    
    conversation = await session.get(ConversationModel, conversation_id)
    if conversation:
        conversation.last_message_id = message.id
    
    await session.commit()

    await broadcast(conversation_id, {
        'event': 'new_message',
        'message': {
            'id': str(message.id),
            'sender_id': str(user.id),
            'text': text,
            'conversation_id': conversation_id,
            'created_at': message.created_at.isoformat(),
            'is_read': False,
            'is_edited': False
        }
    })

async def handle_read_message(data, session, user, conversation_id):
    message_id = data.get('message_id')
    if not message_id:
        return

    msg = await session.get(MessageModel, message_id)
    if msg and msg.conversation_id == conversation_id and msg.sender_id != user.id:
        msg.is_read = True
        await session.commit()
        
        await broadcast(conversation_id, {
            'event': 'message_read',
            'message_id': message_id,
            'reader_id': str(user.id)
        })

async def handle_edit_message(data, session, user, conversation_id):
    '''Обработка редактирования сообщения'''
    message_id = data.get('message_id')
    new_text = data.get('text', '').strip()
    
    if not message_id or not new_text:
        return

    msg = await session.get(MessageModel, message_id)
    if msg and msg.sender_id == user.id and msg.conversation_id == conversation_id:
        msg.text = new_text
        msg.is_edited = True
        msg.edited_at = datetime.now(timezone.utc)
        await session.commit()

        await broadcast(conversation_id, {
            'event': 'message_edited',
            'message': {
                'id': str(msg.id),
                'sender_id': str(msg.sender_id),
                'text': msg.text,
                'is_edited': msg.is_edited,
                'edited_at': msg.edited_at.isoformat(),
                'conversation_id': conversation_id
            }
        })

async def handle_delete_message(data, session, user, conversation_id, websocket):
    message_id = data.get('message_id')
    mode = data.get('mode', 'self')  # self / all
    
    if not message_id:
        return

    msg = await session.get(MessageModel, message_id)
    if not msg or msg.conversation_id != conversation_id:
        return

    if mode == 'self':
        if user.id not in msg.deleted_for:
            msg.deleted_for.append(user.id)
            await session.commit()
        
        await websocket.send_json({
            'event': 'message_deleted',
            'message_id': message_id,
            'mode': 'self'
        })
    elif mode == 'all' and msg.sender_id == user.id:
        await session.delete(msg)
        await session.commit()
        
        await broadcast(conversation_id, {
            'event': 'message_deleted',
            'message_id': message_id,
            'mode': 'all'
        })