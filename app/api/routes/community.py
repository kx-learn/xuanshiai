"""Community and paper-plane routes."""

from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, get_verified_user
from app.db.session import get_db
from app.schemas.community import (
    CommunityCommentCreate,
    CommunityCommentResponse,
    CommunityPostCreate,
    CommunityPostPage,
    CommunityPostResponse,
    PaperPlaneCreate,
    PaperPlaneReplyCreate,
    PaperPlaneReplyResponse,
    PaperPlaneResponse,
)
from app.services.community import (
    create_comment,
    create_paper_plane,
    create_post,
    delete_comment,
    delete_post,
    like_post,
    list_comments,
    list_paper_planes,
    list_posts,
    reply_paper_plane,
)

router = APIRouter(dependencies=[Depends(get_verified_user)])


@router.post("/community/posts", response_model=CommunityPostResponse, status_code=201, summary="发布动态")
async def post(body: CommunityPostCreate, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CommunityPostResponse:
    return await create_post(db, current.id, body)


@router.get("/community/posts", response_model=CommunityPostPage, summary="查看动态流")
async def feed(mode: Literal["latest", "following"] = Query("latest"), page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=50), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CommunityPostPage:
    return await list_posts(db, current.id, mode, page, page_size)


@router.delete("/community/posts/{post_id}", status_code=204, summary="删除动态")
async def remove_post(post_id: int = Path(..., ge=1), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await delete_post(db, current.id, post_id)


@router.put("/community/posts/{post_id}/like", response_model=CommunityPostResponse, summary="点赞动态")
async def like(post_id: int = Path(..., ge=1), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CommunityPostResponse:
    return await like_post(db, current.id, post_id, True)


@router.delete("/community/posts/{post_id}/like", response_model=CommunityPostResponse, summary="取消动态点赞")
async def unlike(post_id: int = Path(..., ge=1), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CommunityPostResponse:
    return await like_post(db, current.id, post_id, False)


@router.get("/community/posts/{post_id}/comments", response_model=list[CommunityCommentResponse], summary="查看动态评论")
async def comments(post_id: int = Path(..., ge=1), page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=50), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[CommunityCommentResponse]:
    return await list_comments(db, post_id, page, page_size)


@router.post("/community/posts/{post_id}/comments", response_model=CommunityCommentResponse, status_code=201, summary="发表评论")
async def comment(post_id: int = Path(..., ge=1), body: CommunityCommentCreate = Body(...), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> CommunityCommentResponse:
    return await create_comment(db, current.id, post_id, body)


@router.delete("/community/comments/{comment_id}", status_code=204, summary="删除评论")
async def remove_comment(comment_id: int = Path(..., ge=1), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await delete_comment(db, current.id, comment_id)


@router.post("/paper-planes", response_model=PaperPlaneResponse, status_code=201, summary="发送纸飞机")
async def send_plane(body: PaperPlaneCreate, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PaperPlaneResponse:
    return await create_paper_plane(db, current.id, body)


@router.get("/paper-planes", response_model=list[PaperPlaneResponse], summary="捡纸飞机")
async def planes(page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=50), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[PaperPlaneResponse]:
    return await list_paper_planes(db, current.id, page, page_size)


@router.get("/paper-planes/mine", response_model=list[PaperPlaneResponse], summary="查看我的纸飞机")
async def my_planes(page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=50), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[PaperPlaneResponse]:
    return await list_paper_planes(db, current.id, page, page_size, own=True)


@router.post("/paper-planes/{plane_id}/replies", response_model=PaperPlaneReplyResponse, status_code=201, summary="回复纸飞机")
async def reply(plane_id: int = Path(..., ge=1), body: PaperPlaneReplyCreate = Body(...), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PaperPlaneReplyResponse:
    return await reply_paper_plane(db, current.id, plane_id, body)
