"""Invitation-only live matchmaking; business actions use authenticated HTTP."""
import asyncio
import contextlib
import time

from fastapi import APIRouter, Depends, HTTPException, Path, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_admin, get_current_user
from app.core.redis import redis_client
from app.db.session import get_db, session_factory
from app.schemas.live_v2 import (LiveCommand, LiveCreateRequest, LiveCredentials, LiveList,
    LiveReport, LiveReportRequest, LiveReportResolution, LiveResources, LiveResults, LiveSnapshot,
    LiveUpdateRequest, LiveAccountList, LiveActionList)
from app.services import live_v2 as live, live_media
from app.services.live_domain import snapshot

router = APIRouter(prefix='/live/v2', tags=['直播相亲'])


@router.get('/accounts', response_model=LiveAccountList, summary='运营搜索已有账号以维护名单')
async def accounts(q: str = Query(min_length=1, max_length=64, description='昵称子串或精确账号ID'),
                   page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50),
                   current: CurrentUser = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await live.search_accounts(db, q, page, page_size)


@router.get('/resources', response_model=LiveResources)
async def resource_status(current: CurrentUser = Depends(get_current_user)):
    return live_media.resources()


@router.get('/sessions', response_model=LiveList)
async def sessions(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.list_sessions(db, current.id)


@router.post('/sessions', response_model=LiveSnapshot, status_code=201)
async def create(body: LiveCreateRequest, current: CurrentUser = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await live.create_session(db, current.id, body)


@router.get('/sessions/{sid}', response_model=LiveSnapshot)
async def detail(sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    state = await live.load_session(db, sid, current.id)
    return snapshot(state, current.id, int(time.time()))


@router.post('/sessions/{sid}/commands', response_model=LiveSnapshot)
async def command(body: LiveCommand, sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.execute(db, sid, current.id, body)


@router.put('/sessions/{sid}', response_model=LiveSnapshot, summary='本场运营完整更新场前信息与名单')
async def update(body: LiveUpdateRequest, sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.update_session(db, sid, current.id, body)


@router.get('/sessions/{sid}/actions', response_model=LiveActionList, summary='本场工作人员分页查看脱敏操作记录')
async def actions(sid: int = Path(gt=0), page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50),
                  current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.action_history(db, sid, current.id, page, page_size)


@router.post('/sessions/{sid}/credentials', response_model=LiveCredentials)
async def credentials(sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live_media.get_credentials(db, sid, current.id)


@router.get('/sessions/{sid}/results', response_model=LiveResults)
async def results(sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.results(db, sid, current.id)


@router.post('/sessions/{sid}/reports', response_model=LiveReport, status_code=201)
async def report(body: LiveReportRequest, sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.report(db, sid, current.id, body)


@router.get('/sessions/{sid}/reports', response_model=list[LiveReport])
async def reports(sid: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await live.reports(db, sid, current.id)


@router.post('/sessions/{sid}/reports/{report_id}/resolve', response_model=LiveReport)
async def resolve(body: LiveReportResolution, sid: int = Path(gt=0), report_id: int = Path(gt=0), current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await live.reports(db, sid, current.id)
    report = next((item for item in items if item.id == report_id), None)
    if report is None:
        raise HTTPException(404, '举报记录不存在')
    await db.execute(text("UPDATE live_v2_report SET status='resolved',resolution=:reason,resolved_by=:uid,resolved_at=UTC_TIMESTAMP() WHERE id=:id"), {'reason': body.reason, 'uid': current.id, 'id': report_id})
    await db.commit()
    return report.model_copy(update={'status': 'resolved', 'resolution': body.reason})


@router.websocket('/sessions/{sid}/events')
async def events(ws: WebSocket, sid: int):
    """Header authentication; periodic revalidation also catches revoked logins."""
    bearer = ws.headers.get('authorization', '')
    if not bearer.startswith('Bearer ') or session_factory is None or sid < 1:
        await ws.close(code=4401)
        return
    auth = HTTPAuthorizationCredentials(scheme='Bearer', credentials=bearer[7:])
    uid = None
    pubsub = redis_client.pubsub()
    try:
        async with session_factory() as db:
            user = await get_current_user(auth, db)
            await live.load_session(db, sid, user.id)
        uid = user.id
        await pubsub.subscribe(f'live:v2:{sid}:revision')
        await ws.accept()
        revision = -1
        while True:
            async with session_factory() as db:
                user = await get_current_user(auth, db)
                state = await live.load_session(db, sid, uid)
            await redis_client.set(f'live:v2:{sid}:online:{uid}', '1', ex=30)
            if state.revision != revision:
                await ws.send_json({'type': 'snapshot', 'snapshot': snapshot(state, uid, int(time.time())).model_dump()})
                revision = state.revision
            else:
                await ws.send_json({'type': 'heartbeat', 'server_time': int(time.time())})
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=10)
            await asyncio.sleep(0.05)
    except HTTPException as exc:
        with contextlib.suppress(RuntimeError):
            await ws.close(code=4401 if exc.status_code == 401 else 4403)
    except RedisError:
        with contextlib.suppress(RuntimeError):
            await ws.close(code=1013)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        with contextlib.suppress(RedisError):
            await pubsub.aclose()
            if uid:
                await redis_client.delete(f'live:v2:{sid}:online:{uid}')
