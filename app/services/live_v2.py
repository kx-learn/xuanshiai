"""SQL transactions and role-filtered realtime snapshots for the invited trial."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.core.config import settings
from app.schemas.live_v2 import (LiveCommand, LiveCreateRequest, LiveList, LiveOpportunity,
    LiveReport, LiveReportRequest, LiveResults, LiveState, SessionSummary, LiveUpdateRequest,
    LiveAccount, LiveAccountList, LiveActionRecord, LiveActionList)
from app.services.live_domain import apply_command, completed_pairs, member_for, new_session, snapshot
from app.services.live_permissions import authorize, CONTROL_ACTIONS
from app.services.notifications import emit_notification

logger = logging.getLogger(__name__)


async def is_admin(db: AsyncSession, uid: int) -> bool:
    return bool((await db.execute(text("SELECT 1 FROM user_role WHERE user_id=:uid AND role_code='admin' AND status=1 LIMIT 1"), {'uid': uid})).scalar())


async def load_session(db: AsyncSession, sid: int, uid: int, *, lock=False, allow_removed=False) -> LiveState:
    result = await db.execute(text('SELECT s.state FROM live_v2_session s JOIN live_v2_member m ON m.session_id=s.id '
        'WHERE s.id=:sid AND m.user_id=:uid' + (' FOR UPDATE' if lock else '')), {'sid': sid, 'uid': uid})
    raw = result.scalar()
    if not raw:
        raise HTTPException(404, '场次不存在或未受邀')
    state = LiveState.model_validate_json(raw) if isinstance(raw, str) else LiveState.model_validate(raw)
    if member_for(state, uid).removed and not allow_removed:
        raise HTTPException(403, '已被移出本场')
    return state


async def save_session(db: AsyncSession, state: LiveState):
    await db.execute(text('UPDATE live_v2_session SET title=:title, scheduled_at=:scheduled, status=:status, state=:state WHERE id=:id'),
        {'id': state.id, 'title': state.title, 'scheduled': state.scheduled_at,
         'status': state.status, 'state': state.model_dump_json()})


async def create_session(db: AsyncSession, uid: int, body: LiveCreateRequest):
    if body.scheduled_at < int(time.time()):
        raise HTTPException(422, '排期必须在未来')
    state = new_session(body, uid, media_mode=settings.live_media_mode)
    await verify_roster(db, state)
    result = await db.execute(text('INSERT INTO live_v2_session (owner_id,title,scheduled_at,state) VALUES (:owner,:title,:scheduled,:state)'),
        {'owner': uid, 'title': state.title, 'scheduled': state.scheduled_at, 'state': state.model_dump_json()})
    state.id = result.lastrowid
    await save_session(db, state)
    await db.execute(text('INSERT INTO live_v2_member (session_id,user_id) VALUES (:sid,:uid)'),
        [{'sid': state.id, 'uid': member.user_id} for member in state.members])
    await notify_members(db, state, 'live_invitation', '直播场次邀请', '请查看本场安排，独立确认或拒绝邀请。')
    await db.commit()
    return snapshot(state, uid, int(time.time()))


async def verify_roster(db: AsyncSession, state: LiveState):
    for member in state.members:
        user = (await db.execute(text('SELECT id, gender, status FROM users WHERE id=:id'), {'id': member.user_id})).mappings().first()
        if not user or user['status'] != 1:
            raise HTTPException(422, f'名单账号 {member.user_id} 不可用')
        expected = {'male': 1, 'female': 2}.get(member.group)
        if expected and user['gender'] != expected:
            raise HTTPException(422, f'名单账号 {member.user_id} 的组别与本人资料不一致')
        if member.role != 'operator':
            await verify_attendee(db, member.user_id)


async def notify_members(db, state, event, title, content, *, recipients=None):
    ids = recipients if recipients is not None else [m.user_id for m in state.members if m.user_id != state.owner_id]
    for uid in ids:
        await emit_notification(db, recipient_user_id=uid, actor_user_id=None, event_type=event,
            title=title, content=content, target_type='live_v2_session', target_id=state.id,
            payload={'session_id': state.id, 'page': 'pagesSub/live/detail'})


async def update_session(db: AsyncSession, sid: int, uid: int, body: LiveUpdateRequest):
    from app.services.live_domain import edit_roster
    state = await load_session(db, sid, uid, lock=True)
    before = state.model_copy(deep=True)
    edit_roster(state, uid, body)
    if state.scheduled_at < int(time.time()):
        raise HTTPException(422, '排期必须在未来')
    await verify_roster(db, state)
    previous, current = {m.user_id for m in before.members}, {m.user_id for m in state.members}
    if before.media_room_id:
        await retire_media(db, before)
    for removed in previous - current:
        await db.execute(text('DELETE FROM live_v2_member WHERE session_id=:sid AND user_id=:uid'), {'sid': sid, 'uid': removed})
    for added in current - previous:
        await db.execute(text('INSERT INTO live_v2_member (session_id,user_id) VALUES (:sid,:uid)'), {'sid': sid, 'uid': added})
    await save_session(db, state)
    await notify_members(db, state, 'live_changed', '直播安排已更新', '请查看最新安排；需要重新确认的人员须再次确认并签到。', recipients=(previous | current) - {uid})
    await record_action(db, state, uid, 'edit_roster', uuid.uuid4().hex, '', {'outcome': 'accepted'})
    await db.commit()
    await publish_revision(sid, state.revision)
    return snapshot(state, uid, int(time.time()))


async def list_sessions(db: AsyncSession, uid: int) -> LiveList:
    rows = (await db.execute(text('SELECT s.state FROM live_v2_session s JOIN live_v2_member m ON m.session_id=s.id '
        'WHERE m.user_id=:uid ORDER BY s.scheduled_at DESC LIMIT 50'), {'uid': uid})).scalars().all()
    items = []
    for raw in rows:
        state = LiveState.model_validate_json(raw) if isinstance(raw, str) else LiveState.model_validate(raw)
        member = member_for(state, uid)
        if not member.removed:
            items.append(SessionSummary(id=state.id, title=state.title, scheduled_at=state.scheduled_at,
                status=state.status, role=member.role, media_mode=state.media_mode))
    return LiveList(items=items, can_manage=await is_admin(db, uid))


def qualification_missing(row) -> list[str]:
    today = datetime.now(UTC).date()
    birth = row['birthday'] if row else None
    adult = birth is not None and today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day)) >= 18
    return [label for label, valid in [('账号正常', row and row['status'] == 1), ('年满18岁', adult),
        ('绑定手机', row and bool(row['phone'])), ('实名认证', row and row['realname_status'] == 2)] if not valid]


async def verify_attendee(db: AsyncSession, uid: int):
    row = (await db.execute(text('SELECT u.birthday,u.phone,u.status,a.realname_status FROM users u '
        'LEFT JOIN user_auth a ON a.user_id=u.id WHERE u.id=:id'), {'id': uid})).mappings().first()
    if qualification_missing(row):
        raise HTTPException(403, '本场参与须年满18岁、绑定手机并完成实名认证')


async def search_accounts(db: AsyncSession, query: str, page: int, page_size: int) -> LiveAccountList:
    where = " WHERE CAST(u.id AS CHAR)=:q OR LOCATE(:q,COALESCE(u.nickname,''))>0"
    params = {'q': query.strip(), 'limit': page_size, 'offset': (page - 1) * page_size}
    if not params['q']:
        raise HTTPException(422, '请输入账号 ID 或昵称')
    total = (await db.execute(text('SELECT COUNT(*) FROM users u' + where), params)).scalar_one()
    rows = (await db.execute(text('SELECT u.id,u.nickname,u.gender,u.birthday,u.phone,u.status,a.realname_status '
        'FROM users u LEFT JOIN user_auth a ON a.user_id=u.id' + where + ' ORDER BY u.id LIMIT :limit OFFSET :offset'), params)).mappings().all()
    items = [LiveAccount(user_id=row['id'], nickname=row['nickname'] or '未设置昵称', gender=row['gender'] or 0,
        eligible=not qualification_missing(row), missing=qualification_missing(row)) for row in rows]
    return LiveAccountList(items=items, page=page, page_size=page_size, total=total, has_more=page * page_size < total)


async def record_action(db, state, uid, action, command_id, digest, audit):
    await db.execute(text('INSERT INTO live_v2_action (session_id,user_id,command_id,request_hash,action,revision,audit) '
        'VALUES (:sid,:uid,:cid,:hash,:action,:revision,:audit)'), {'sid': state.id, 'uid': uid, 'cid': command_id,
        'hash': digest, 'action': action, 'revision': state.revision, 'audit': json.dumps(audit, ensure_ascii=False)})


async def retire_media(db, state):
    await db.execute(text('INSERT INTO live_v2_media_cleanup (session_id,room_id,task_id) VALUES (:sid,:room,:task)'),
        {'sid': state.id, 'room': state.media_room_id, 'task': state.media_task_id})


async def execute(db: AsyncSession, sid: int, uid: int, cmd: LiveCommand):
    from app.services.live_media import resources
    state = await load_session(db, sid, uid, lock=True)
    digest = hashlib.sha256(cmd.model_dump_json().encode()).hexdigest()
    prior = (await db.execute(text('SELECT request_hash,audit FROM live_v2_action WHERE session_id=:sid AND user_id=:uid AND command_id=:cid'),
        {'sid': sid, 'uid': uid, 'cid': cmd.command_id})).mappings().first()
    if prior:
        if prior['request_hash'] != digest:
            raise HTTPException(409, '同一操作编号不能提交不同内容')
        previous_audit = json.loads(prior['audit']) if isinstance(prior['audit'], str) else prior['audit']
        if previous_audit.get('outcome') == 'rejected':
            raise HTTPException(previous_audit['status_code'], previous_audit['error'])
        return snapshot(state, uid, int(time.time()))
    before = state.model_copy(deep=True)
    now = int(time.time())
    try:
        if state.revision != cmd.expected_revision:
            raise HTTPException(409, '场次已更新，请刷新后重新确认操作')
        authorize(state, member_for(state, uid), cmd, now)
        if cmd.action in ('accept', 'check_in', 'choose') or (cmd.action in ('hand', 'light', 'special') and cmd.value):
            await verify_attendee(db, uid)
        if cmd.action in ('start', 'rehearse'):
            await verify_roster(db, state)
            gate = resources(rehearsal=cmd.action == 'rehearse', media_mode=state.media_mode)
            if not gate.ready:
                raise HTTPException(503, '音视频试点资源尚未就绪：' + '、'.join(gate.missing))
        apply_command(state, uid, cmd, now)
    except HTTPException as exc:
        if cmd.action in CONTROL_ACTIONS | {'take_control', 'return_control', 'end', 'remove'}:
            await record_action(db, before, uid, cmd.action, cmd.command_id, digest,
                {'outcome': 'rejected', 'status_code': exc.status_code, 'error': exc.detail})
            await db.commit()
        raise
    if state.media_epoch != before.media_epoch and before.media_room_id:
        # Rotating the room invalidates old room-bound publish tickets immediately.
        await retire_media(db, before)
        state.media_task_id = None
    if state.status == 'ended' and before.status != 'ended':
        expires = datetime.fromtimestamp(now, UTC).replace(tzinfo=None) + timedelta(hours=72)
        for first, second in completed_pairs(state):
            await db.execute(text('INSERT IGNORE INTO live_v2_opportunity (session_id,first_user_id,second_user_id,expires_at) VALUES (:sid,:first,:second,:expires)'),
                {'sid': sid, 'first': first, 'second': second, 'expires': expires})
        await notify_members(db, state, 'live_result', '直播场次已结束', '可查看本人交流结果；是否申请认识由您自主决定。')
    elif cmd.action in ('schedule', 'cancel'):
        await notify_members(db, state, 'live_cancelled' if cmd.action == 'cancel' else 'live_scheduled',
            '直播场次已取消' if cmd.action == 'cancel' else '直播场次已排期', '请查看场次的最新安排。')
    elif cmd.action in ('accept', 'decline'):
        await notify_members(db, state, 'live_invitation_response', '直播邀请已有答复', '请查看参与者的确认状态。', recipients=[state.owner_id])
    # Private selections are not copied into operation logs or realtime payloads.
    audit = {'outcome': 'accepted', 'target_id': cmd.target_id if cmd.action in ('remove', 'stage', 'speaker') else None,
             'reason': cmd.reason if cmd.action in ('remove', 'take_control', 'return_control', 'skip_round') else '',
             'consent_version': cmd.consent_version if cmd.action == 'accept' else None}
    await record_action(db, state, uid, cmd.action, cmd.command_id, digest, audit)
    await save_session(db, state)
    await db.commit()
    await publish_revision(sid, state.revision)
    return snapshot(state, uid, now)


async def publish_revision(sid: int, revision: int):
    try:
        # No choices, profiles or role-specific data in a shared Redis channel.
        await redis_client.publish(f'live:v2:{sid}:revision', str(revision))
    except RedisError:
        logger.warning('Live event delivery unavailable; clients must refresh snapshots')


async def results(db: AsyncSession, sid: int, uid: int) -> LiveResults:
    state = await load_session(db, sid, uid, allow_removed=True)
    rows = (await db.execute(text('SELECT * FROM live_v2_opportunity WHERE session_id=:sid AND '
        '(first_user_id=:uid OR second_user_id=:uid) ORDER BY id'), {'sid': sid, 'uid': uid})).mappings().all()
    now = int(time.time())
    items = []
    for row in rows:
        peer = row['second_user_id'] if row['first_user_id'] == uid else row['first_user_id']
        expires = int(row['expires_at'].replace(tzinfo=UTC).timestamp())
        items.append(LiveOpportunity(id=row['id'], session_id=sid, peer_id=peer,
            peer_name=member_for(state, peer).display_name, expires_at=expires,
            application_id=row['application_id'], status='used' if row['application_id'] else ('expired' if expires <= now else 'available')))
    return LiveResults(items=items, session_ended=state.status == 'ended', media_mode=state.media_mode)


async def action_history(db, sid: int, uid: int, page: int, page_size: int) -> LiveActionList:
    state = await load_session(db, sid, uid)
    if member_for(state, uid).role not in ('host', 'matchmaker', 'operator'):
        raise HTTPException(403, '仅本场工作人员可查看操作记录')
    params = {'sid': sid, 'limit': page_size, 'offset': (page - 1) * page_size}
    total = (await db.execute(text('SELECT COUNT(*) FROM live_v2_action WHERE session_id=:sid'), params)).scalar_one()
    rows = (await db.execute(text('SELECT id,user_id,action,revision,audit,created_at FROM live_v2_action '
        'WHERE session_id=:sid ORDER BY id DESC LIMIT :limit OFFSET :offset'), params)).mappings().all()
    items = []
    for row in rows:
        audit = json.loads(row['audit']) if isinstance(row['audit'], str) else row['audit']
        items.append(LiveActionRecord(id=row['id'], user_id=row['user_id'], action=row['action'],
            revision=row['revision'], outcome=audit.get('outcome', 'accepted'), target_id=audit.get('target_id'),
            reason=audit.get('reason', ''), created_at=int(row['created_at'].replace(tzinfo=UTC).timestamp())))
    return LiveActionList(items=items, page=page, page_size=page_size, total=total, has_more=page * page_size < total)


async def report(db: AsyncSession, sid: int, uid: int, body: LiveReportRequest):
    state = await load_session(db, sid, uid)
    member_for(state, body.target_id)
    result = await db.execute(text('INSERT INTO live_v2_report (session_id,reporter_id,target_id,reason) VALUES (:sid,:uid,:target,:reason)'),
        {'sid': sid, 'uid': uid, 'target': body.target_id, 'reason': body.reason})
    await db.commit()
    return LiveReport(id=result.lastrowid, target_id=body.target_id, reason=body.reason, status='open')


async def reports(db: AsyncSession, sid: int, uid: int):
    state = await load_session(db, sid, uid)
    if uid != state.owner_id and member_for(state, uid).role != 'host':
        raise HTTPException(403, '仅主持或场次运营可处理举报')
    rows = (await db.execute(text('SELECT id,target_id,reason,status,resolution FROM live_v2_report WHERE session_id=:sid ORDER BY id DESC LIMIT 100'), {'sid': sid})).mappings().all()
    return [LiveReport(**row) for row in rows]
