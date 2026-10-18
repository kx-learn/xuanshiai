"""Emotion-lab endpoints for the current MBTI-only release."""

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_verified_user
from app.db.session import get_db
from app.schemas.message import (
    EmotionAnswersUpdate,
    EmotionLabSummary,
    EmotionProfileSource,
    EmotionProfileSourceUpdate,
    EmotionSessionCreate,
)
from app.services.emotion_lab import (
    discard_assessment,
    get_summary,
    save_answers as save_assessment_answers,
    set_profile_source,
    start_assessment,
    submit_assessment,
)
from app.schemas.message import EmotionSessionSnapshot

router = APIRouter(prefix="/emotion-lab", dependencies=[Depends(get_verified_user)])


@router.get("/summary", response_model=EmotionLabSummary, summary="获取情感实验室摘要")
async def summary(
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionLabSummary:
    return await get_summary(db, current.id)


@router.put("/profile-source", response_model=EmotionProfileSource, summary="确认并同步 MBTI 到资料")
async def profile_source(
    body: EmotionProfileSourceUpdate = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionProfileSource:
    return await set_profile_source(db, current.id, body)


@router.post(
    "/sessions", response_model=EmotionSessionSnapshot, summary="创建 MBTI 测试会话"
)
async def create_session(
    body: EmotionSessionCreate = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionSessionSnapshot:
    return await start_assessment(db, current.id, body)


@router.put(
    "/sessions/{session_id}/answers", response_model=EmotionSessionSnapshot, summary="保存 MBTI 答案"
)
async def save_answers(
    session_id: str = Path(..., min_length=1, max_length=128),
    body: EmotionAnswersUpdate = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionSessionSnapshot:
    return await save_assessment_answers(db, current.id, session_id, body)


@router.post(
    "/sessions/{session_id}/submit", response_model=EmotionSessionSnapshot, summary="提交 MBTI 测试"
)
async def submit_session(
    session_id: str = Path(..., min_length=1, max_length=128),
    body: EmotionAnswersUpdate = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionSessionSnapshot:
    return await submit_assessment(db, current.id, session_id, body)


@router.post(
    "/sessions/{session_id}/discard", response_model=EmotionSessionSnapshot, summary="放弃 MBTI 草稿"
)
async def discard_session(
    session_id: str = Path(..., min_length=1, max_length=128),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionSessionSnapshot:
    return await discard_assessment(db, current.id, session_id)
