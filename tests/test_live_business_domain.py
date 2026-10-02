"""Business-only live regressions: actual domain rules, no database or cloud mocks."""
import pytest
from fastapi import HTTPException

from app.schemas.live_v2 import Exchange, LiveCommand, LiveCreateRequest, LiveState, LiveUpdateRequest
from app.services import live_domain
from app.services.live_domain import apply_command, member_for, new_session, snapshot


def roster():
    return LiveCreateRequest(
        title='真实业务演练', scheduled_at=1000, host_id=1,
        matchmaker_ids=[2, 3], male_ids=[4, 5, 6, 7], female_ids=[8, 9, 10, 11],
        main_order=[4, 8, 5, 9], spectator_ids=[12],
        notice='受邀业务演练，仅展示授权资料，本场未启用音视频。',
    )


def ready_session():
    state = new_session(roster(), 20)
    state.id = 1
    for member in state.members:
        member.accepted = True
        member.checked_in = True
        member.attendance = 'backstage'
    return state


def command(state, uid, action, now=1000, **fields):
    apply_command(state, uid, LiveCommand(
        command_id=f'business-{state.revision:04d}', expected_revision=state.revision,
        action=action, **fields,
    ), now)


def in_question():
    state = ready_session()
    command(state, 1, 'start')
    command(state, 1, 'advance')
    assert state.current.phase == 'question'
    return state


def assert_rejected_without_mutation(state, uid, action, expected_status, **fields):
    before = state.model_dump()
    with pytest.raises(HTTPException) as error:
        command(state, uid, action, **fields)
    assert error.value.status_code == expected_status
    assert state.model_dump() == before


def test_host_cannot_remove_session_operator():
    state = in_question()
    assert_rejected_without_mutation(
        state, 1, 'remove', 403, target_id=20, reason='无权移出本场运营',
    )


@pytest.mark.parametrize('owner_id', [1, 2, 4, 12])
def test_operator_must_be_independent_of_every_roster_role(owner_id):
    with pytest.raises(HTTPException) as error:
        new_session(roster(), owner_id)
    assert error.value.status_code == 422


@pytest.mark.parametrize('uid', [5, 6, 7])
def test_backstage_guests_cannot_request_speaking_in_an_unrelated_round(uid):
    state = in_question()
    assert_rejected_without_mutation(state, uid, 'hand', 403, value=True)
    assert 'hand' not in snapshot(state, uid, 1000).allowed_actions


@pytest.mark.parametrize('uid', [2, 3, 8])
def test_question_participants_can_request_and_retract_speaking(uid):
    state = in_question()
    command(state, uid, 'hand', value=True)
    assert member_for(state, uid).hand is True
    assert 'hand' in snapshot(state, uid, 1000).allowed_actions
    command(state, uid, 'hand', value=False)
    assert member_for(state, uid).hand is False


@pytest.mark.parametrize('phase', ['intro', 'interest', 'choice', 'transition'])
def test_matchmaker_cannot_request_a_question_outside_question_phase(phase):
    state = ready_session()
    command(state, 1, 'start')
    state.current.phase = phase
    assert_rejected_without_mutation(state, 2, 'hand', 409, value=True)
    assert 'hand' not in snapshot(state, 2, 1000).allowed_actions


def test_phase_change_clears_question_queue_and_assigned_question_speaker():
    state = in_question()
    command(state, 2, 'hand', value=True)
    command(state, 8, 'hand', value=True)
    command(state, 1, 'speaker', target_id=2)
    assert state.speaker_id == 2
    command(state, 1, 'advance')
    assert state.current.phase == 'interest'
    assert all(not member.hand for member in state.members)
    assert state.speaker_id != 2


def test_paused_snapshot_does_not_advertise_new_questions_or_choices():
    state = in_question()
    command(state, 1, 'pause', now=1010)
    assert 'hand' not in snapshot(state, 2, 1010).allowed_actions
    assert 'hand' not in snapshot(state, 8, 1010).allowed_actions
    assert 'choose' not in snapshot(state, 4, 1010).allowed_actions
    assert 'advance' not in snapshot(state, 1, 1010).allowed_actions
    assert 'resume' in snapshot(state, 1, 1010).allowed_actions
    assert_rejected_without_mutation(state, 2, 'hand', 409, value=True, now=1010)


def test_choice_action_disappears_at_authoritative_deadline():
    state = in_question()
    command(state, 1, 'advance')
    command(state, 1, 'advance')
    assert 'choose' in snapshot(state, 4, 1059).allowed_actions
    assert 'choose' not in snapshot(state, 4, 1060).allowed_actions
    assert 'choose' not in snapshot(state, 8, 1060).allowed_actions


def test_closed_session_has_no_actions_for_any_role():
    state = in_question()
    command(state, 20, 'end')
    for uid in [1, 2, 3, 4, 5, 8, 12, 20]:
        assert snapshot(state, uid, 1000).allowed_actions == []


def test_takeover_changes_controller_not_public_roles_or_stage_members():
    state = in_question()
    stage_before = list(state.stage_ids)
    command(state, 20, 'take_control', reason='主持网络中断，由运营暂时接管')
    assert state.controller_id == 20
    assert snapshot(state, 20, 1000).controller_id == 20
    assert member_for(state, 1).role == 'host'
    assert member_for(state, 20).role == 'operator'
    assert state.stage_ids == stage_before
    assert 20 not in state.stage_ids
    assert 'advance' in snapshot(state, 20, 1000).allowed_actions
    assert 'advance' not in snapshot(state, 1, 1000).allowed_actions
    assert 'choose' not in snapshot(state, 20, 1000).allowed_actions


@pytest.mark.parametrize('action,fields', [
    ('advance', {}), ('pause', {}), ('extend', {'seconds': 30}),
    ('speaker', {'target_id': 2}), ('stage', {'target_id': 8, 'value': False}),
])
def test_original_host_cannot_control_flow_after_operator_takeover(action, fields):
    state = in_question()
    command(state, 20, 'take_control', reason='主持暂时失联')
    assert_rejected_without_mutation(state, 1, action, 403, **fields)


def test_operator_can_pause_and_return_control_to_host():
    state = in_question()
    command(state, 20, 'take_control', reason='主持暂时失联')
    command(state, 20, 'pause', now=1020)
    remaining = state.pause_remaining
    command(state, 20, 'return_control', reason='主持已恢复连接')
    assert state.controller_id == 1
    assert 'resume' in snapshot(state, 1, 1100).allowed_actions
    assert 'resume' not in snapshot(state, 20, 1100).allowed_actions
    command(state, 1, 'resume', now=1100)
    assert state.current.deadline == 1100 + remaining


@pytest.mark.parametrize('uid', [1, 2, 4, 12])
def test_non_operator_cannot_take_control(uid):
    state = in_question()
    assert_rejected_without_mutation(state, uid, 'take_control', 403, reason='越权接管')


def test_takeover_requires_an_explicit_reason():
    state = in_question()
    assert_rejected_without_mutation(state, 20, 'take_control', 422, reason='   ')


def test_host_cannot_skip_a_round_while_main_guest_is_still_present():
    state = in_question()
    assert_rejected_without_mutation(state, 1, 'skip_round', 409, reason='仍在场不能跳轮')


@pytest.mark.parametrize('departure', ['leave', 'remove'])
def test_controller_can_confirm_skip_after_main_guest_departure(departure):
    state = in_question()
    if departure == 'leave':
        command(state, 4, 'leave')
    else:
        command(state, 20, 'remove', target_id=4, reason='主嘉宾需退出本场')
    assert 'skip_round' in snapshot(state, 1, 1000).allowed_actions
    command(state, 1, 'skip_round', reason='主嘉宾已明确离场，确认跳过本轮')
    assert state.round_index > 0 or state.current.phase in ('transition', 'completed')
    assert not any(pair.status == 'completed' for pair in state.rounds[0].exchanges)


def test_skipping_after_departure_still_requires_reason():
    state = in_question()
    command(state, 4, 'leave')
    assert_rejected_without_mutation(state, 1, 'skip_round', 422, reason=' ')


def test_disabled_media_checkin_does_not_claim_device_check_or_allocate_rtc_room():
    state = ready_session()
    state.media_mode = 'disabled'
    member_for(state, 4).checked_in = False
    command(state, 4, 'check_in', device_checked=False)
    assert member_for(state, 4).checked_in is True
    command(state, 1, 'start')
    assert state.status == 'live'
    assert state.stage_ids == [1, 2, 3, 4, 8, 9, 10, 11]
    assert state.media_room_id == 0
    assert state.media_task_id is None
    assert snapshot(state, 4, 1000).media_mode == 'disabled'


def test_trtc_checkin_still_requires_real_device_confirmation():
    state = ready_session()
    member_for(state, 4).checked_in = False
    assert_rejected_without_mutation(state, 4, 'check_in', 403, device_checked=False)


def consented_session():
    state = ready_session()
    for member in state.members:
        member.invitation = 'accepted'
        member.consent_at = 900
        member.display_name = f'已确认用户{member.user_id}'
        member.introduction = f'用户{member.user_id}已授权的公开介绍'
    return state


def update_body(state, **changes):
    fields = roster().model_dump()
    fields.update(changes)
    return LiveUpdateRequest(expected_revision=state.revision, **fields)


def assert_confirmation_reset(member):
    assert member.accepted is False
    assert member.invitation == 'pending'
    assert member.checked_in is False
    assert member.consent_at is None
    assert member.attendance in ('invited', 'reserved')


@pytest.mark.parametrize('uid', [1, 2, 3, 4, 8, 12, 21])
def test_only_session_owner_can_edit_roster(uid):
    state = consented_session()
    before = state.model_dump()
    with pytest.raises(HTTPException) as error:
        live_domain.edit_roster(state, uid, update_body(state, title='不能越权修改'))
    assert error.value.status_code == 403
    assert state.model_dump() == before


@pytest.mark.parametrize('status', ['live', 'paused', 'ended', 'cancelled'])
def test_roster_edit_is_closed_after_start_or_cancellation(status):
    state = consented_session()
    state.status = status
    before = state.model_dump()
    with pytest.raises(HTTPException) as error:
        live_domain.edit_roster(state, 20, update_body(state, male_ids=[4, 5, 6, 13]))
    assert error.value.status_code == 409
    assert state.model_dump() == before


@pytest.mark.parametrize('changes,affected', [
    ({'host_id': 2, 'matchmaker_ids': [1, 3]}, {1, 2}),
    ({'male_ids': [5, 4, 6, 7]}, {4, 5}),
    ({'main_order': [5, 8, 4, 9]}, {4, 5}),
    ({'main_order': [6, 8, 5, 9]}, {4, 6}),
])
def test_role_seat_and_main_order_edits_reset_only_affected_confirmations(changes, affected):
    state = consented_session()
    state.status = 'scheduled'
    before = {member.user_id: member.model_dump() for member in state.members}
    live_domain.edit_roster(state, 20, update_body(state, **changes))
    for member in state.members:
        if member.user_id in affected:
            assert_confirmation_reset(member)
        else:
            assert member.model_dump() == before[member.user_id]
    assert [round_.main_id for round_ in state.rounds] == changes.get('main_order', [4, 8, 5, 9])
    assert state.controller == changes.get('host_id', 1)
    assert state.status == 'scheduled'


@pytest.mark.parametrize('changes', [
    {'scheduled_at': 2000},
    {'notice': '场次告知变更：仅向受邀人员展示，未启用真实音视频。'},
])
def test_time_or_notice_change_requires_every_participant_to_reconfirm(changes):
    state = consented_session()
    operator_before = member_for(state, 20).model_dump()
    live_domain.edit_roster(state, 20, update_body(state, **changes))
    for member in state.members:
        if member.user_id == 20:
            assert member.model_dump() == operator_before
        else:
            assert_confirmation_reset(member)
    for field, value in changes.items():
        assert getattr(state, field) == value


def test_title_only_edit_preserves_every_confirmation():
    state = consented_session()
    before = [member.model_dump() for member in state.members]
    live_domain.edit_roster(state, 20, update_body(state, title='调整场次标题'))
    assert state.title == '调整场次标题'
    assert [member.model_dump() for member in state.members] == before


def test_roster_replacement_removes_old_invitee_and_adds_unconfirmed_new_account():
    state = consented_session()
    before = {member.user_id: member.model_dump() for member in state.members}
    live_domain.edit_roster(state, 20, update_body(
        state, male_ids=[4, 5, 6, 13], spectator_ids=[14],
    ))
    assert {member.user_id for member in state.members} == {1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14, 20}
    assert_confirmation_reset(member_for(state, 13))
    assert_confirmation_reset(member_for(state, 14))
    assert member_for(state, 13).role == 'guest'
    assert member_for(state, 13).group == 'male'
    assert member_for(state, 13).seat == 4
    assert member_for(state, 14).role == 'spectator'
    for member in state.members:
        if member.user_id not in (13, 14):
            assert member.model_dump() == before[member.user_id]


def test_owner_cannot_edit_themselves_into_host_roster():
    state = consented_session()
    before = state.model_dump()
    with pytest.raises(HTTPException) as error:
        live_domain.edit_roster(state, 20, update_body(state, host_id=20))
    assert error.value.status_code == 422
    assert state.model_dump() == before


def legacy_payload():
    payload = consented_session().model_dump()
    payload['owner_id'] = 1
    payload['members'] = [member for member in payload['members'] if member['user_id'] != 20]
    payload.pop('media_mode')
    payload.pop('controller_id')
    for member in payload['members']:
        member.pop('invitation')
    for round_ in payload['rounds']:
        round_.pop('skip_reason')
    return payload


def test_legacy_owner_host_overlap_requires_roster_repair_before_start():
    state = LiveState.model_validate(legacy_payload())
    assert 'start' not in snapshot(state, 1, 1000).allowed_actions
    assert_rejected_without_mutation(state, 1, 'start', 409)


def test_legacy_ended_history_defaults_preserve_private_choices_and_completed_results():
    payload = legacy_payload()
    payload.update(status='ended', revision=27, round_index=3, ended_at=4800)
    payload['rounds'][0].update(
        phase='completed', selections={'4': [8, 10], '8': [4], '10': []},
        exchanges=[Exchange(main_id=4, candidate_id=8, status='completed', started_at=1060, ended_at=1180).model_dump()],
    )
    state = LiveState.model_validate(payload)
    assert state.media_mode == 'trtc'
    assert state.controller == 1
    assert state.status == 'ended'
    assert state.revision == 27
    assert state.round_index == 3
    assert state.ended_at == 4800
    assert state.rounds[0].selections == payload['rounds'][0]['selections']
    assert [pair.model_dump() for pair in state.rounds[0].exchanges] == payload['rounds'][0]['exchanges']
    assert all(member.invitation == 'accepted' for member in state.members)
    assert all(round_.skip_reason == '' for round_ in state.rounds)
    assert live_domain.completed_pairs(state) == {(4, 8)}
    assert snapshot(state, 1, 5000).allowed_actions == []


@pytest.mark.parametrize('departure', ['leave', 'remove'])
def test_confirmed_skip_can_advance_to_next_round_without_departed_main(departure):
    state = in_question()
    if departure == 'leave':
        command(state, 4, 'leave')
    else:
        command(state, 20, 'remove', target_id=4, reason='主嘉宾退出本场')
    command(state, 1, 'skip_round', reason='确认主嘉宾离场并跳过本轮')
    assert 'advance' in snapshot(state, 1, 1060).allowed_actions
    command(state, 1, 'advance', now=1060)
    assert state.round_index == 1
    assert state.current.main_id == 8
    assert state.current.phase == 'intro'
    assert state.rounds[0].phase == 'completed'
    assert state.rounds[0].skip_reason == '确认主嘉宾离场并跳过本轮'
    assert 4 not in state.stage_ids
