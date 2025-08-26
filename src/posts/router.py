from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, status, Depends
from sqlalchemy import select, join, and_, desc
from sqlalchemy.orm import selectinload

from src.database import SessionDep
from src.users.models import UserModel
from src.posts.models import PostsModel, PostImagesModel, PostLikesModel, PostCommentsModel
from src.users.utils import get_current_user


posts_router = APIRouter()

@posts_router.get('/api/v1/posts/{user_id}')
async def get_user_posts(
    user_id: UUID,
    session: SessionDep,
    limit: int = Query(10, gt=0, le=50),
    cursor: datetime | None = Query(...),
    user: UserModel = Depends(get_current_user)
):
    user_result = await session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found'
        )

    query = select(PostsModel).options(
        selectinload(PostsModel.images),
        selectinload(PostsModel.likes),
        selectinload(PostsModel.comments)
    ).where(PostsModel.user_id == user_id)
    if cursor:
        query = query.where(PostsModel.created_at <= cursor)
    query = query.order_by(PostsModel.created_at.desc()).limit(limit)

    posts_result = await session.execute(query)
    posts = posts_result.scalars().all()

    response = []
    for post in posts:
        response.append({
            'id': post.id,
            'text': post.text,
            'created_at': post.created_at,
            'updated_at': post.updated_at,
            'images': [img.image_url for img in post.images],
            'likes_count': len(post.likes),
            'comments_count': len(post.comments)
        })

    return {'posts': response}

@posts_router.get('/api/v1/posts/photos/{user_id}')
async def get_user_photos_feed(
    user_id: UUID,
    session: SessionDep,
    limit: int = Query(10, gt=0, le=50),
    cursor: datetime | None = Query(None),
    user: UserModel = Depends(get_current_user)
):
    user_result = await session.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found'
        )

    query = select(
        PostImagesModel.id,
        PostImagesModel.post_id,
        PostImagesModel.image_url,
        PostImagesModel.position,
        PostsModel.created_at
    ).join(PostsModel, PostImagesModel.post_id == PostsModel.id
    ).where(PostsModel.user_id == user_id)

    if cursor:
        query = query.where(PostsModel.created_at < cursor)

    query = query.order_by(desc(PostsModel.created_at)).limit(limit)

    result = await session.execute(query)
    photos = result.all()

    next_cursor = photos[-1].created_at if photos else None

    return {
        'photos': [
            {
                'id': p.id,
                'post_id': p.post_id,
                'image_url': p.image_url,
                'position': p.position,
                'created_at': p.created_at
            }
            for p in photos
        ],
        'next_cursor': next_cursor
    }
