"""Authoritative small-session state transitions, independent of transports."""
import secrets

from fastapi import HTTPException

from app.schemas.live_v2 import (Exchange, LiveCommand, LiveCreateRequest, LiveMe,
                              LiveSnapshot, LiveState, Member, PublicMember, RoundState, LiveUpdateRequest)

from app.services.live_permissions import authorize, capabilities, candidates

PHASE_SECONDS = {'intro': 180, 'question': 240, 'interest': 60, 'choice': 60,
                 'exchanges': 120, 'transition': 60, 'completed': 0}


def new_session(body: LiveCreateRequest, owner_id: int, *, media_mode='trtc') -> LiveState:
    members = [Member(user_id=body.host_id, role='host')]
    members += [Member(user_id=uid, role='matchmaker') for uid in body.matchmaker_ids]
    for group, ids in [('male', body.male_ids), ('female', body.female_ids)]:
        members += [Member(user_id=uid, role='guest', group=group, seat=i + 1) for i, uid in enumerate(ids)]
    members += [Member(user_id=uid, role='spectator') for uid in body.spectator_ids]
    if owner_id in [m.user_id for m in members]:
        raise HTTPException(422, '运营必须独立于主持、红娘、嘉宾及观众名单')
    members.append(Member(user_id=owner_id, role='operator', display_name='场次运营', accepted=True, invitation='accepted'))
    return LiveState(title=body.title, scheduled_at=body.scheduled_at, notice=body.notice,
                     owner_id=owner_id, controller_id=body.host_id, media_mode=media_mode, members=members,
                     rounds=[RoundState(main_id=uid) for uid in body.main_order])


def member_for(state: LiveState, uid: int) -> Member:
    member = next((m for m in state.members if m.user_id == uid), None)
    if member is None:
        raise HTTPException(404, '场次不存在或未受邀')
    return member


def edit_roster(state: LiveState, uid: int, body: LiveUpdateRequest):
    if uid != state.owner_id:
        raise HTTPException(403, '仅本场运营可修改名单')
    if state.status not in ('draft', 'scheduled'):
        raise HTTPException(409, '开场后名单与四轮安排已锁定')
    if body.expected_revision != state.revision:
        raise HTTPException(409, '场次已更新，请刷新后重新编辑')
    revised = new_session(body, uid, media_mode=state.media_mode)
    previous = {m.user_id: m for m in state.members}
    old_order = [r.main_id for r in state.rounds]
    new_order = body.main_order
    reset_all = (state.scheduled_at, state.notice) != (body.scheduled_at, body.notice)
    def main_position(order, user_id):
        return order.index(user_id) if user_id in order else -1
    for index, member in enumerate(revised.members):
        old = previous.get(member.user_id)
        if old is None:
            continue
        if member.role == 'operator':
            if old.role == 'operator':
                revised.members[index] = old.model_copy(deep=True)
            continue
        changed = old.removed or reset_all or (old.role, old.group, old.seat) != (member.role, member.group, member.seat)
        changed = changed or main_position(old_order, member.user_id) != main_position(new_order, member.user_id)
        if not changed:
            revised.members[index] = old.model_copy(deep=True)
        else:
            member.reserved = old.reserved
            member.attendance = 'reserved' if old.reserved else 'invited'
    # Preparation edits invalidate any old media rehearsal stage as well.
    _stage(state, [])
    state.speaker_id = None
    state.media_room_id, state.media_task_id = 0, None
    state.members, state.rounds = revised.members, revised.rounds
    for member in state.members:
        member.hand = False
        if member.attendance == 'onstage':
            member.attendance = 'backstage'
    state.title, state.scheduled_at, state.notice = revised.title, revised.scheduled_at, revised.notice
    state.controller_id = revised.controller_id
    state.revision += 1


def candidate_ids(state: LiveState) -> list[int]:
    return candidates(state)


def completed_pairs(state: LiveState) -> set[tuple[int, int]]:
    return {tuple(sorted((p.main_id, p.candidate_id))) for r in state.rounds
            for p in r.exchanges if p.status == 'completed'}


def _phase(state: LiveState, phase: str, now: int):
    for member in state.members:
        member.hand = False
    state.speaker_id = None
    state.current.phase = phase
    state.current.deadline = None if state.status == 'paused' else now + PHASE_SECONDS[phase]
    if state.status == 'paused':
        state.pause_remaining = PHASE_SECONDS[phase]


def _stage(state: LiveState, ids: list[int]):
    if len(ids) > 8:
        raise HTTPException(409, '舞台最多 8 路出镜')
    if state.stage_ids != ids:
        state.stage_ids = ids
        if state.media_mode == 'trtc':
            state.media_epoch += 1
            state.media_room_id = secrets.randbelow(4294967293) + 1
    for member in state.members:
        if member.user_id in ids:
            member.attendance = 'onstage'
        elif member.attendance == 'onstage':
            member.attendance = 'backstage'


def _round_stage(state: LiveState):
    staff = [m.user_id for m in state.members if m.role in ('host', 'matchmaker')
             and m.checked_in and not m.removed and m.attendance != 'left']
    main = member_for(state, state.current.main_id)
    ids = staff + ([main.user_id] if main.checked_in and not main.removed and main.attendance != 'left' else []) + candidate_ids(state)
    _stage(state, ids)
    state.speaker_id = main.user_id if main.user_id in ids else None


def _next_exchange(state: LiveState, now: int):
    next_pair = next((p for p in state.current.exchanges if p.status == 'queued'), None)
    if next_pair is None:
        _phase(state, 'transition', now)
        return
    next_pair.status, next_pair.started_at = 'active', now
    _phase(state, 'exchanges', now)
    state.speaker_id = next_pair.main_id if next_pair.main_id in state.stage_ids else None


def _advance(state: LiveState, now: int):
    current = state.current
    if current.phase in ('choice', 'exchanges') and now < (current.deadline or now):
        raise HTTPException(409, '当前环节尚未截止；需要中止交流请由参与者退出')
    if current.phase in ('intro', 'question', 'interest'):
        _phase(state, {'intro': 'question', 'question': 'interest', 'interest': 'choice'}[current.phase], now)
    elif current.phase == 'choice':
        chosen = current.selections.get(str(current.main_id), [])
        completed = completed_pairs(state)
        current.exchanges = [Exchange(main_id=current.main_id, candidate_id=uid)
            for uid in candidate_ids(state) if uid in chosen
            and current.main_id in current.selections.get(str(uid), [])
            and tuple(sorted((current.main_id, uid))) not in completed]
        _next_exchange(state, now)
    elif current.phase == 'exchanges':
        pair = next(p for p in current.exchanges if p.status == 'active')
        pair.status, pair.ended_at = 'completed', now
        _next_exchange(state, now)
    elif current.phase == 'transition':
        current.phase = 'completed'
        if state.round_index < 3:
            state.round_index += 1
            _phase(state, 'intro', now)
            _round_stage(state)
    else:
        raise HTTPException(409, '四轮已完成，请结束场次')


def _leave(state: LiveState, member: Member, now: int):
    member.attendance, member.hand = 'left', False
    state.current.lights.pop(str(member.user_id), None)
    state.current.selections.pop(str(member.user_id), None)
    member.special_target = None
    if member.user_id in state.stage_ids:
        _stage(state, [uid for uid in state.stage_ids if uid != member.user_id])
    if state.speaker_id == member.user_id:
        state.speaker_id = None
    had_active = False
    for pair in state.current.exchanges:
        if member.user_id in (pair.main_id, pair.candidate_id) and pair.status in ('queued', 'active'):
            had_active = had_active or pair.status == 'active'
            pair.status, pair.ended_at = 'withdrawn', now
    if had_active:
        _next_exchange(state, now)


def apply_command(state: LiveState, uid: int, cmd: LiveCommand, now: int):
    """Policy is shared with snapshots; caller holds the SQL session row lock."""
    member = member_for(state, uid)
    authorize(state, member, cmd, now)
    action = cmd.action
    if action == 'accept':
        if cmd.consent_version != 'live-trial-v1' or not cmd.value or not cmd.display_name.strip():
            raise HTTPException(422, '请填写展示称呼并明确同意本场告知')
        member.accepted, member.invitation, member.consent_at = True, 'accepted', now
        member.display_name, member.introduction = cmd.display_name.strip(), cmd.introduction.strip()
    elif action == 'decline':
        member.accepted, member.invitation, member.checked_in = False, 'declined', False
        member.consent_at = None
        _leave(state, member, now)
        member.attendance = 'reserved' if member.reserved else 'invited'
    elif action == 'reserve':
        member.reserved = cmd.value
        if not member.checked_in:
            member.attendance = 'reserved' if cmd.value else 'invited'
    elif action == 'check_in':
        if state.media_mode == 'trtc' and member.role != 'spectator' and not cmd.device_checked:
            raise HTTPException(403, '请先完成真实设备检测')
        member.checked_in = True
        member.attendance = 'onstage' if uid in state.stage_ids else 'backstage'
    elif action == 'schedule':
        state.status = 'scheduled'
    elif action in ('start', 'rehearse'):
        if action == 'start':
            state.status = 'live'
            _phase(state, 'intro', now)
        _round_stage(state)
    elif action in ('end', 'cancel'):
        state.status, state.ended_at = ('ended' if action == 'end' else 'cancelled'), now
        _stage(state, [])
        state.current.deadline, state.speaker_id = None, None
        for participant in state.members:
            participant.hand = False
        for pair in state.current.exchanges:
            if pair.status in ('active', 'queued'):
                pair.status, pair.ended_at = 'withdrawn', now
    elif action == 'leave':
        _leave(state, member, now)
    elif action == 'remove':
        target = member_for(state, cmd.target_id)
        target.removed = True
        _leave(state, target, now)
    elif action in ('take_control', 'return_control'):
        state.controller_id = state.owner_id if action == 'take_control' else next(m.user_id for m in state.members if m.role == 'host')
    elif action == 'skip_round':
        state.current.skip_reason = cmd.reason.strip()
        _phase(state, 'transition', now)
    elif action == 'pause':
        state.status = 'paused'
        state.pause_remaining = max(0, (state.current.deadline or now) - now)
        state.current.deadline = None
        for participant in state.members:
            participant.hand = False
    elif action == 'resume':
        state.status = 'live'
        state.current.deadline = now + state.pause_remaining
    elif action == 'advance':
        _advance(state, now)
    elif action == 'extend':
        state.current.deadline += cmd.seconds
    elif action == 'speaker':
        state.speaker_id = cmd.target_id
        member_for(state, cmd.target_id).hand = False
    elif action == 'stage':
        ids = [i for i in state.stage_ids if i != cmd.target_id]
        _stage(state, ids + [cmd.target_id] if cmd.value else ids)
        if not cmd.value and state.speaker_id == cmd.target_id:
            state.speaker_id = None
    elif action == 'hand':
        member.hand = cmd.value
    elif action == 'withdraw_exchange':
        pairs = [p for p in state.current.exchanges if uid in (p.main_id, p.candidate_id) and p.status in ('queued', 'active')]
        active = any(p.status == 'active' for p in pairs)
        for pair in pairs:
            pair.status, pair.ended_at = 'withdrawn', now
        if active:
            _next_exchange(state, now)
    elif action == 'choose':
        state.current.selections[str(uid)] = cmd.targets if uid == state.current.main_id else ([state.current.main_id] if cmd.value else [])
    elif action == 'light':
        if cmd.value:
            state.current.lights[str(uid)] = cmd.target_id
        else:
            state.current.lights.pop(str(uid), None)
    elif action == 'special':
        if cmd.value:
            member.special_spent, member.special_target = True, cmd.target_id
        else:
            member.special_target = None
    state.revision += 1


def snapshot(state: LiveState, uid: int, now: int) -> LiveSnapshot:
    member = member_for(state, uid)
    allowed, targets = capabilities(state, member, now)
    # Explicit public allowlist: no private state, SDK tickets or audit reasons.
    public = [PublicMember(user_id=m.user_id, role=m.role, group=m.group, seat=m.seat,
        display_name=m.display_name if m.accepted else '受邀用户',
        introduction=m.introduction if m.accepted else '', attendance=m.attendance,
        on_stage=m.user_id in state.stage_ids, hand=m.hand,
        light_target=state.current.lights.get(str(m.user_id)), special_target=m.special_target,
        invitation='accepted' if m.accepted else m.invitation, checked_in=m.checked_in, removed=m.removed)
        for m in state.members]
    return LiveSnapshot(id=state.id, title=state.title, scheduled_at=state.scheduled_at,
        status=state.status, revision=state.revision, server_time=now, notice=state.notice,
        round_index=state.round_index, main_id=state.current.main_id, phase=state.current.phase,
        deadline=state.current.deadline, pause_remaining=state.pause_remaining,
        speaker_id=state.speaker_id, media_epoch=state.media_epoch, media_mode=state.media_mode,
        controller_id=state.controller, owner_id=state.owner_id, main_order=[r.main_id for r in state.rounds],
        can_edit=uid == state.owner_id and state.status in ('draft', 'scheduled'),
        can_read_actions=member.role in ('host', 'matchmaker', 'operator') and not member.removed,
        members=public,
        me=LiveMe(user_id=uid, role=member.role, accepted=member.accepted, reserved=member.reserved,
            invitation='accepted' if member.accepted else member.invitation,
            checked_in=member.checked_in, removed=member.removed,
            special_remaining=0 if member.special_spent else 1,
            selection=state.current.selections.get(str(uid), [])),
        allowed_actions=allowed, allowed_targets=targets, exchanges=state.current.exchanges)
