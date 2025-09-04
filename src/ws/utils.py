from fastapi import WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select
from jose import jwt, JWTError

from src.database import SessionDep
from src.users.models import UserModel
from src.users.utils import ALGORITHM, SECRET_KEY


async def get_current_user_ws(
    websocket: WebSocket,
    session: SessionDep
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate WebSocket credentials',
    )

    token = None

    if 'refresh_token' in websocket.cookies:
        token = websocket.cookies.get('refresh_token')

    if not token:
        token = websocket.query_params.get('token')

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_result = await session.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user
