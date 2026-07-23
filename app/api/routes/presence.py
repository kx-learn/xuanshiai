"""Authenticated online presence endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.presence import PresenceResponse, PresenceStatusRequest
from app.services.presence import get_status, heartbeat, set_status

router = APIRouter(prefix="/users/me/presence")


@router.post("/heartbeat", response_model=PresenceResponse, summary="刷新在线心跳")
async def presence_heartbeat(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PresenceResponse:
    return await heartbeat(db, current.id, current.session_id)


@router.post("/status", response_model=PresenceResponse, summary="设置在线或隐身状态")
async def presence_status(body: PresenceStatusRequest, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PresenceResponse:
    return await set_status(db, current.id, current.session_id, body)


@router.get("", response_model=PresenceResponse, summary="查询我的在线状态")
async def my_presence(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> PresenceResponse:
    return await get_status(db, current.id, current.session_id)
