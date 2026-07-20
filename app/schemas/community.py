"""Schemas for community posts, comments and paper planes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CommunityPostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=9)
    video: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=128)
    topic_id: int | None = Field(default=None, ge=1)


class CommunityPostResponse(BaseModel):
    id: int
    user_id: int
    nickname: str | None
    avatar: str | None
    content: str
    images: list[str]
    video: str | None
    location: str | None
    like_count: int
    comment_count: int
    is_liked: bool
    created_at: datetime


class CommunityPostPage(BaseModel):
    items: list[CommunityPostResponse]
    page: int
    page_size: int
    total: int


class CommunityCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    parent_id: int | None = Field(default=None, ge=1)


class CommunityCommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    nickname: str | None
    avatar: str | None
    parent_id: int | None
    content: str
    like_count: int
    created_at: datetime


class PaperPlaneCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    images: list[str] = Field(default_factory=list, max_length=6)
    city: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=5)
    is_anonymous: bool = True


class PaperPlaneResponse(BaseModel):
    id: int
    content: str
    images: list[str]
    city: str | None
    tags: list[str]
    is_anonymous: bool
    reply_count: int
    created_at: datetime


class PaperPlaneReplyCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    is_anonymous: bool = True


class PaperPlaneReplyResponse(BaseModel):
    id: int
    plane_id: int
    user_id: int
    content: str
    is_anonymous: bool
    created_at: datetime
