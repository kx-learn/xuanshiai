"""One room policy for command authorization and per-user UI capabilities."""
from fastapi import HTTPException

from app.schemas.live_v2 import LiveCommand, LiveState, LiveTargets, Member

CONTROL_ACTIONS = {'rehearse', 'start', 'pause', 'resume', 'extend', 'advance', 'speaker', 'stage', 'skip_round'}


def present(member: Member) -> bool:
    return member.checked_in and member.accepted and not member.removed and member.attendance != 'left'


def candidates(state: LiveState) -> list[int]:
    main = next(m for m in state.members if m.user_id == state.current.main_id)
    return [m.user_id for m in sorted(state.members, key=lambda m: m.seat)
            if m.role == 'guest' and m.group != main.group and present(m)]


def ready_to_start(state: LiveState) -> bool:
    required = [m for m in state.members if m.role in ('host', 'matchmaker', 'guest')]
    return (len(required) == 11 and state.owner_id not in [m.user_id for m in required]
            and all(present(m) for m in required))


def role_actions(state: LiveState, member: Member) -> set[str]:
    actions = {'accept', 'decline', 'reserve', 'check_in', 'leave'} if member.role != 'operator' else set()
    if member.user_id == state.controller and (member.role == 'operator' or present(member)):
        actions |= CONTROL_ACTIONS | {'end'}
    if member.user_id == state.owner_id:
        actions |= {'schedule', 'cancel', 'remove', 'end', 'take_control', 'return_control'}
    elif member.role == 'host' and member.user_id == state.controller:
        actions.add('remove')
    if member.role == 'guest':
        actions |= {'light', 'special', 'withdraw_exchange'}
        if member.user_id == state.current.main_id or member.user_id in candidates(state):
            actions.add('choose')
    if member.role == 'matchmaker' or member.user_id in candidates(state):
        actions.add('hand')
    return actions


def capabilities(state: LiveState, member: Member, now: int) -> tuple[list[str], LiveTargets]:
    targets = LiveTargets()
    if member.removed or state.status in ('ended', 'cancelled'):
        return [], targets
    before = state.status in ('draft', 'scheduled')
    live = state.status == 'live'
    paused = state.status == 'paused'
    current = state.current
    main = next(m for m in state.members if m.user_id == current.main_id)
    relevant = present(member) and (member.user_id == main.user_id or member.user_id in candidates(state))
    deadline_open = current.deadline is not None and now < current.deadline
    rehearsal = before and bool(state.stage_ids) and state.media_mode == 'trtc'
    conditions = {
        'accept': before or (member.role == 'spectator' and not member.accepted),
        'decline': before,
        'reserve': before or live or paused,
        'check_in': member.accepted and member.attendance != 'left',
        'leave': member.attendance != 'left',
        'schedule': state.status == 'draft',
        'cancel': before,
        'start': before and ready_to_start(state),
        'rehearse': before and ready_to_start(state) and state.media_mode == 'trtc',
        'pause': live,
        'resume': paused,
        'extend': live and deadline_open,
        'advance': live and (present(main) or bool(current.skip_reason)) and current.phase != 'completed'
                   and (current.phase not in ('choice', 'exchanges') or not deadline_open),
        'speaker': live or rehearsal,
        'stage': live or rehearsal,
        'remove': True,
        'end': True,
        'take_control': state.controller != state.owner_id,
        'return_control': state.controller == state.owner_id and any(m.role == 'host' and present(m) for m in state.members),
        'skip_round': live and not present(main) and current.phase != 'completed' and not current.skip_reason,
        'hand': live and current.phase == 'question' and present(member) and deadline_open,
        'choose': live and relevant and present(main) and current.phase == 'choice' and deadline_open,
        'light': (live and relevant and present(main) and current.phase == 'interest' and deadline_open)
                 or str(member.user_id) in current.lights,
        'special': (live and relevant and present(main) and current.phase == 'interest' and deadline_open and not member.special_spent)
                   or member.special_target is not None,
        'withdraw_exchange': (live or paused) and any(member.user_id in (p.main_id, p.candidate_id)
                                                     and p.status in ('active', 'queued') for p in current.exchanges),
    }
    allowed = sorted(action for action in role_actions(state, member) if conditions[action])
    if 'remove' in allowed:
        targets.remove_ids = [m.user_id for m in state.members if not m.removed
            and m.user_id not in (state.owner_id, member.user_id)
            and (m.role != 'host' or member.user_id == state.owner_id)]
    eligible_stage = [m.user_id for m in state.members if present(m)
        and (m.role in ('host', 'matchmaker') or m.user_id == main.user_id or m.user_id in candidates(state))]
    if 'stage' in allowed:
        targets.stage_ids = eligible_stage
    if 'speaker' in allowed:
        speaking = [m.user_id for m in state.members if m.role == 'host']
        if rehearsal or current.phase == 'question':
            speaking = eligible_stage
        elif current.phase == 'intro':
            speaking.append(main.user_id)
        elif current.phase == 'exchanges':
            speaking += [uid for p in current.exchanges if p.status == 'active' for uid in (p.main_id, p.candidate_id)]
        targets.speaker_ids = [uid for uid in state.stage_ids if uid in speaking]
    if relevant and present(main):
        peers = candidates(state) if member.user_id == main.user_id else [main.user_id]
        if live and current.phase == 'interest' and deadline_open:
            targets.interest_ids = peers
        if 'choose' in allowed:
            targets.choice_ids = peers
    return allowed, targets


def authorize(state: LiveState, member: Member, cmd: LiveCommand, now: int):
    if member.removed:
        raise HTTPException(403, '已被移出本场')
    if state.status in ('ended', 'cancelled'):
        raise HTTPException(409, '场次已结束或取消')
    if cmd.action not in role_actions(state, member):
        raise HTTPException(403, '本场角色或当前控场权不允许此操作')
    allowed, targets = capabilities(state, member, now)
    # Retraction is always safe for one's own public interest, including during pause.
    retract = cmd.action in ('light', 'special') and not cmd.value and member.role == 'guest'
    if cmd.action not in allowed and not retract:
        raise HTTPException(409, '当前环节、截止时间或人员准备情况不允许此操作，请刷新场次')
    scope = {'remove': targets.remove_ids, 'stage': targets.stage_ids, 'speaker': targets.speaker_ids}
    if cmd.action in scope and cmd.target_id not in scope[cmd.action]:
        raise HTTPException(403, '不能对该人员执行此操作')
    if cmd.action in ('remove', 'take_control', 'return_control', 'skip_round') and not cmd.reason.strip():
        raise HTTPException(422, '必须填写操作原因')
    if cmd.action in ('light', 'special') and cmd.value:
        if not present(member) or (member.user_id != state.current.main_id and member.user_id not in candidates(state)):
            raise HTTPException(403, '不属于本轮有效嘉宾')
        if cmd.target_id not in targets.interest_ids or (cmd.action == 'special' and member.special_spent):
            raise HTTPException(409, '当前无法向此人表达意向，或特别心动次数已用完')
    if cmd.action == 'choose' and member.user_id == state.current.main_id:
        if len(set(cmd.targets)) != len(cmd.targets) or not set(cmd.targets) <= set(targets.choice_ids):
            raise HTTPException(422, '请选择最多三位不重复的本轮有效候选人')
