import os
from datetime import datetime, timezone
import redis.asyncio as redis
import asyncio
from fastapi import APIRouter, WebSocket, Depends, WebSocketDisconnect
from dotenv import load_dotenv
from src.users.models import UserModel
from src.ws.utils import get_current_user_ws

presence_ws_router = APIRouter()

load_dotenv()
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_presence_ws = f'{redis_url}/1'
r = redis.from_url(redis_presence_ws)

@presence_ws_router.websocket('/api/v1/ws/presence')
async def presence_ws(
    websocket: WebSocket,
    user: UserModel = Depends(get_current_user_ws)
):
    await websocket.accept()
    user_key = f'user:{user.id}:status'
    
    # Устанавливаем статус онлайн
    await r.set(user_key, 'online')
    print(f'User {user.id} ({user.name}) connected and set online')
    
    try:
        while True:
            # Продлеваем время жизни ключа
            await r.expire(user_key, 60)
            
            try:
                # Ждем сообщение от клиента с таймаутом
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                print(f'Received ping from user {user.id}: {message}')
            except asyncio.TimeoutError:
                print(f'Timeout for user {user.id}, continuing...')
                continue
            except WebSocketDisconnect:
                print(f'WebSocket disconnected for user {user.id}')
                break
                
    except Exception as e:
        print(f'WebSocket error for user {user.id}: {e}')
    finally:
        # При отключении устанавливаем время последнего визита
        last_seen_key = f'user:{user.id}:last_seen'
        await r.set(last_seen_key, datetime.now(timezone.utc).isoformat())
        # Удаляем ключ онлайн статуса
        await r.delete(user_key)
        print(f'User {user.id} disconnected and marked offline')