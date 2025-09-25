from uuid import UUID, uuid4
from datetime import datetime, timedelta

from fastapi import APIRouter, Query, HTTPException, status, Depends
from sqlalchemy import select, desc, update, delete, func
from sqlalchemy.orm import selectinload

from src.database import SessionDep
from src.minio import minio_client
from src.users.models import UserModel
from src.posts.models import PostsModel, PostImagesModel, PostLikesModel, PostCommentsModel
from src.users.utils import get_current_user
from src.posts.schemas import PostCreationSchema, CommentCreationSchema


posts_router = APIRouter()


@posts_router.post('/api/v1/posts')
async def create_post(
    post_data: PostCreationSchema,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    if post_data.images and len(post_data.images) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Maximum 10 images allowed per post'
        )

    new_post = PostsModel(
        user_id=user.id,
        text=post_data.text
    )
    session.add(new_post)
    await session.flush()

    images_with_url = []
    if post_data.images:
        for idx, obj_name in enumerate(post_data.images, start=1):
            image = PostImagesModel(
                post_id=new_post.id,
                image_url=obj_name,
                position=idx
            )
            session.add(image)

            url = minio_client.presigned_get_object(
                bucket_name='posts',
                object_name=obj_name,
                expires=timedelta(minutes=10)
            )
            images_with_url.append(url)

    await session.commit()

    return {
        'post_id': str(new_post.id),
        'text': new_post.text,
        'images': images_with_url,
        'created_at': new_post.created_at
    }

@posts_router.get('/api/v1/posts/upload-url')
async def get_post_image_upload_url(
    user: UserModel = Depends(get_current_user)
):
    object_name = f'{uuid4()}.png'
    url = minio_client.presigned_put_object(
        bucket_name='posts',
        object_name=f'posts/{object_name}',
        expires=timedelta(minutes=10)
    )
    return {
        'upload_url': url,
        'object_name': f'posts/{object_name}'
    } 

@posts_router.get('/api/v1/posts/{user_id}')
async def get_user_posts(
    user_id: UUID,
    session: SessionDep,
    limit: int = Query(10, gt=0, le=50),
    cursor: datetime | None = Query(None),
    user: UserModel = Depends(get_current_user)
):
    terget_user_result = await session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    target_user = terget_user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User not found'
        )

    query = select(PostsModel).options(
        selectinload(PostsModel.images),
        selectinload(PostsModel.comments)
    ).where(PostsModel.user_id == user_id)
    if cursor:
        query = query.where(PostsModel.created_at < cursor)
    query = query.order_by(PostsModel.created_at.desc()).limit(limit + 1)

    posts_result = await session.execute(query)
    posts = posts_result.scalars().all()

    if len(posts) > limit:
        next_cursor = posts[-1].created_at
        posts = posts[:-1]
    else:
        next_cursor = None

    post_ids = [post.id for post in posts]
    likes_result = await session.execute(
        select(PostLikesModel.post_id).where(
            PostLikesModel.post_id.in_(post_ids),
            PostLikesModel.user_id == user.id
        )
    )
    liked_post_ids = {post_id for post_id, in likes_result.all()}

    response = []
    for post in posts:
        images_with_url = [
            minio_client.presigned_get_object(
                bucket_name='posts',
                object_name=img.image_url,
                expires=timedelta(minutes=10)
            )
            for img in post.images
        ]

        is_liked = post.id in liked_post_ids

        likes_count = await session.scalar(
            select(func.count(PostLikesModel.id)).where(PostLikesModel.post_id == post.id)
        )
        
        response.append(
            {
                'id': post.id,
                'text': post.text,
                'created_at': post.created_at,
                'updated_at': post.updated_at,
                'images': images_with_url,
                'likes_count': likes_count,
                'comments_count': len(post.comments),
                'is_liked': is_liked
            }
    )

    return {
        'posts': response,
        'next_cursor': next_cursor,
        'has_more': bool(next_cursor)
    }

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
            status_code=status.HTTP_400_BAD_REQUEST,
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

@posts_router.post('/api/v1/posts/like/{post_id}')
async def put_like(
    session: SessionDep,
    post_id: UUID,
    user: UserModel = Depends(get_current_user)
):
    post_result = await session.execute(
        select(PostsModel)
        .where(PostsModel.id==post_id)
    )
    post = post_result.scalar_one_or_none()

    if post is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Post not found'
        )
    
    like_result = await session.execute(
        select(PostLikesModel)
        .where(PostLikesModel.post_id==post_id)
        .where(PostLikesModel.user_id==user.id)
    )
    existing_like = like_result.scalar_one_or_none()

    if existing_like:
        raise(HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User already liked this post'
        ))
    
    new_like = PostLikesModel(post_id=post_id, user_id=user.id)
    session.add(new_like)
    await session.commit()

    return {'detail': 'Post liked successfully'}

@posts_router.delete('/api/v1/posts/like/{post_id}')
async def remove_like(
    session: SessionDep,
    post_id: UUID,
    user: UserModel = Depends(get_current_user) 
):
    post_result = await session.execute(
        select(PostsModel).where(PostsModel.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Post not found'
        )

    like_result = await session.execute(
        select(PostLikesModel).where(
            PostLikesModel.post_id == post_id,
            PostLikesModel.user_id == user.id
        )
    )
    like = like_result.scalar_one_or_none()
    if not like:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User has not liked this post'
        )

    await session.execute(
        delete(PostLikesModel)
        .where(PostLikesModel.id == like.id)
    )
    await session.commit()

    return {'detail': 'Like removed'}

@posts_router.post('/api/v1/posts/comment/{post_id}')
async def create_comment(
    post_id: str,
    comment_data: CommentCreationSchema,
    session: SessionDep,
    user: UserModel = Depends(get_current_user)
):
    post_result = await session.execute(
        select(PostsModel)
        .where(PostsModel.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Post not found'
        )

    if comment_data.parent_id:
        parent_result = await session.execute(
            select(PostCommentsModel)
            .where(PostCommentsModel.id == comment_data.parent_id)
        )
        parent_comment = parent_result.scalar_one_or_none()
        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Parent comment not found'
            )
    else:
        parent_comment = None

    new_comment = PostCommentsModel(
        post_id=post.id,
        user_id=user.id,
        text=comment_data.text,
        parent_id=comment_data.parent_id
    )

    session.add(new_comment)
    await session.commit()
    await session.refresh(new_comment)

    return {
        'id': str(new_comment.id),
        'post_id': str(post.id),
        'user_id': str(user.id),
        'text': new_comment.text,
        'parent_id': new_comment.parent_id,
        'created_at': new_comment.created_at
    }

@posts_router.get('/api/v1/posts/comments/{post_id}')
async def get_post_comments(
    post_id: UUID,
    session: SessionDep,
    limit: int = Query(10, gt=0, le=50),
    cursor: str | None = Query(None),
    user: UserModel = Depends(get_current_user)
):
    post_result = await session.execute(
        select(PostsModel).where(PostsModel.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Post not found'
        )

    query = select(PostCommentsModel).options(
        selectinload(PostCommentsModel.replies)
    ).where(
        PostCommentsModel.post_id == post_id,
        PostCommentsModel.parent_id == None
    )

    if cursor:
        query = query.where(PostCommentsModel.created_at < cursor)

    query = query.order_by(desc(PostCommentsModel.created_at)).limit(limit)

    result = await session.execute(query)
    comments = result.scalars().all()

    response = []
    for comment in comments:
        response.append({
            'id': comment.id,
            'user_id': comment.user_id,
            'text': comment.text,
            'created_at': comment.created_at,
            'replies': [
                {
                    'id': r.id,
                    'user_id': r.user_id,
                    'text': r.text,
                    'created_at': r.created_at
                }
                for r in sorted(comment.replies or [], key=lambda x: x.created_at)
            ]
        })

    next_cursor = comments[-1].created_at if comments else None

    return {
        'comments': response,
        'next_cursor': next_cursor
    }
