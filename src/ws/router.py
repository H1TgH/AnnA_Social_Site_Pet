import os
from uuid import UUID
from datetime import datetime
import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy import select
from src.users.models import UserModel
from src.database import SessionDep
from src.users.utils import get_current_user

ws_router = APIRouter()

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_presence = f'{redis_url}/1'
r = redis.from_url(redis_presence)

@ws_router.get('/api/v1/users/{user_id}/status')
async def get_user_status(
    user_id: UUID,
    session: SessionDep,
    current_user: UserModel = Depends(get_current_user)
):
    user_result = await session.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
    )
    target_user = user_result.scalar_one_or_none()
    
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User not found'
        )
    
    user_key = f'user:{user_id}:status'
    last_seen_key = f'user:{user_id}:last_seen'
    
    status_online = await r.get(user_key)
    if status_online:
        return {
            'user_id': str(user_id),
            'status': 'online',
            'last_seen': None
        }
    
    last_seen = await r.get(last_seen_key)
    if last_seen:
        if isinstance(last_seen, bytes):
            last_seen = last_seen.decode('utf-8')
        
        try:
            last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            return {
                'user_id': str(user_id),
                'status': 'offline',
                'last_seen': last_seen_dt.isoformat()
            }
        except (ValueError, AttributeError) as e:
            print(f'Error parsing last_seen time: {e}')
    
    return {
        'user_id': str(user_id),
        'status': 'offline',
        'last_seen': None
    }