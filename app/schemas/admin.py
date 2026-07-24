"""Administrative moderation schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class MediaReviewRequest(BaseModel):
    status: Literal[1, 2, 3]
    reason: str | None = Field(default=None, max_length=255)


class MediaReviewResponse(BaseModel):
    media_id: int
    user_id: int
    status: Literal[1, 2, 3]
    reason: str | None


class ReportReviewRequest(BaseModel):
    status: Literal[1, 2]
    result: str = Field(min_length=1, max_length=255)


class ReportReviewResponse(BaseModel):
    report_id: int
    status: Literal[1, 2]
    result: str




class CertificationReviewRequest(BaseModel):
    status: Literal[2, 3]
    reason: str | None = Field(default=None, max_length=255)


class CertificationReviewResponse(BaseModel):
    user_id: int
    kind: Literal["education", "house", "marriage"]
    status: Literal[2, 3]
    reason: str | None
