"""Administrative moderation routes."""

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_admin
from app.db.session import get_db
from app.schemas.admin import MediaReviewRequest, MediaReviewResponse, ReportReviewRequest, ReportReviewResponse
from app.services.profile import review_media
from app.services.social import review_report

router = APIRouter(prefix="/admin")


@router.patch("/media/{media_id}/review", response_model=MediaReviewResponse, summary="审核用户媒体")
async def review_user_media(media_id: int = Path(..., ge=1), body: MediaReviewRequest = Body(...), admin: CurrentUser = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> MediaReviewResponse:
    return await review_media(db, media_id, body)


@router.patch("/reports/{report_id}/review", response_model=ReportReviewResponse, summary="处理用户举报")
async def review_user_report(report_id: int = Path(..., ge=1), body: ReportReviewRequest = Body(...), admin: CurrentUser = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> ReportReviewResponse:
    return await review_report(db, report_id, body)
