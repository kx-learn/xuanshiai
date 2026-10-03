"""Executable trial rules. No cloud, clock sleeps or database mocks."""
import pytest
from fastapi import HTTPException

from app.schemas.live_v2 import LiveCommand, LiveCreateRequest
from app.services.live_domain import apply_command, new_session, snapshot


def session():
    state = new_session(LiveCreateRequest(title='受邀场次', scheduled_at=1000,
        host_id=1, matchmaker_ids=[2, 3], male_ids=[4, 5, 6, 7],
        female_ids=[8, 9, 10, 11], main_order=[4, 8, 5, 9], spectator_ids=[12],
        notice='现场音视频向受邀人员展示，不提供公开回放。'), 20)
    state.id = 1
    for member in state.members:
        member.accepted = True
        member.checked_in = True
        member.attendance = 'backstage'
    return state


def act(state, user, action, now=1000, **fields):
    apply_command(state, user, LiveCommand(action=action, command_id='test-command',
        expected_revision=state.revision, **fields), now)


def at_choice():
    state = session()
    act(state, 1, 'start')
    for _ in range(3):
        act(state, 1, 'advance')
    assert state.current.phase == 'choice'
    return state


def test_eight_stage_slots_and_four_round_main_order():
    state = session()
    act(state, 1, 'start')
    assert state.stage_ids == [1, 2, 3, 4, 8, 9, 10, 11]
    assert [r.main_id for r in state.rounds] == [4, 8, 5, 9]


def test_private_choices_are_never_exposed_to_host_matchmakers_or_spectators():
    state = at_choice()
    act(state, 4, 'choose', targets=[10, 8, 9])
    act(state, 8, 'choose', value=True)
    act(state, 9, 'choose', value=False)
    for uid in [1, 2, 3, 9, 12, 20]:
        view = snapshot(state, uid, 1001)
        assert 'choices' not in view.model_dump_json()
        assert view.me.selection == ([] if uid != 9 else [])
        assert view.exchanges == []
    assert snapshot(state, 4, 1001).me.selection == [10, 8, 9]
    act(state, 1, 'advance', now=1060)
    assert [(p.main_id, p.candidate_id) for p in state.current.exchanges] == [(4, 8)]


def test_modify_selection_until_server_deadline_and_no_early_disclosure():
    state = at_choice()
    act(state, 4, 'choose', targets=[8, 9])
    act(state, 4, 'choose', now=1059, targets=[10])
    with pytest.raises(HTTPException) as error:
        act(state, 1, 'advance', now=1059)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        act(state, 4, 'choose', now=1060, targets=[8])
    assert state.current.selections['4'] == [10]


def test_lights_do_not_constrain_choice_and_strong_interest_is_not_queue_priority():
    state = session()
    act(state, 1, 'start')
    act(state, 1, 'advance')
    act(state, 1, 'advance')
    act(state, 10, 'special', value=True, target_id=4)
    act(state, 10, 'special', value=False)
    with pytest.raises(HTTPException):
        act(state, 10, 'special', value=True, target_id=4)
    act(state, 1, 'advance')
    act(state, 4, 'choose', targets=[10, 9, 8])
    for uid in [8, 9, 10]:
        act(state, uid, 'choose', value=True)
    act(state, 1, 'advance', now=1060)
    assert [p.candidate_id for p in state.current.exchanges] == [8, 9, 10]


def test_pause_preserves_remaining_time_and_blocks_guest_actions():
    state = at_choice()
    act(state, 1, 'pause', now=1020)
    with pytest.raises(HTTPException):
        act(state, 4, 'choose', now=1030, targets=[8])
    act(state, 1, 'resume', now=1200)
    assert state.current.deadline == 1240


@pytest.mark.parametrize('uid', [1, 2, 3, 5, 12, 20])
def test_non_current_guests_cannot_choose_on_behalf(uid):
    state = at_choice()
    with pytest.raises(HTTPException):
        act(state, uid, 'choose', targets=[8], value=True)


def test_no_mutual_match_skips_exchange_and_withdrawn_pair_gets_no_completion():
    state = at_choice()
    act(state, 1, 'advance', now=1060)
    assert state.current.phase == 'transition'
    state = at_choice()
    act(state, 4, 'choose', targets=[8, 9])
    act(state, 8, 'choose', value=True)
    act(state, 9, 'choose', value=True)
    act(state, 1, 'advance', now=1060)
    act(state, 8, 'withdraw_exchange', now=1061)
    assert state.current.exchanges[0].status == 'withdrawn'
    assert state.current.exchanges[1].status == 'active'
    act(state, 1, 'advance', now=1181)
    assert state.current.exchanges[1].status == 'completed'


def test_completed_pair_cannot_be_matched_again_in_same_session():
    state = at_choice()
    act(state, 4, 'choose', targets=[8])
    act(state, 8, 'choose', value=True)
    act(state, 1, 'advance', now=1060)
    act(state, 1, 'advance', now=1180)
    act(state, 1, 'advance', now=1240)
    for _ in range(3):
        act(state, 1, 'advance', now=1240)
    act(state, 8, 'choose', now=1241, targets=[4])
    act(state, 4, 'choose', now=1241, value=True)
    act(state, 1, 'advance', now=1300)
    assert state.current.exchanges == []


def test_special_interest_can_be_retracted_after_interest_window_while_paused():
    state = session()
    act(state, 1, 'start')
    act(state, 1, 'advance')
    act(state, 1, 'advance')
    act(state, 8, 'special', value=True, target_id=4)
    act(state, 1, 'advance')
    act(state, 1, 'pause')
    act(state, 8, 'special', value=False)
    assert next(m for m in state.members if m.user_id == 8).special_target is None


def test_leaving_active_exchange_during_pause_keeps_next_exchange_paused():
    state = at_choice()
    act(state, 4, 'choose', targets=[8, 9])
    for uid in [8, 9]:
        act(state, uid, 'choose', value=True)
    act(state, 1, 'advance', now=1060)
    act(state, 1, 'pause', now=1070)
    act(state, 8, 'leave', now=1090)
    assert state.status == 'paused' and state.current.deadline is None
    act(state, 1, 'resume', now=1200)
    assert state.current.deadline == 1320


def test_rehearsal_allows_stage_checks_without_starting_formal_rounds():
    state = session()
    act(state, 1, 'rehearse')
    act(state, 1, 'stage', target_id=8, value=False)
    assert state.status == 'draft' and 8 not in state.stage_ids
    act(state, 1, 'stage', target_id=8, value=True)
    act(state, 1, 'speaker', target_id=8)
    assert state.speaker_id == 8 and state.current.deadline is None


def test_participant_may_withdraw_exchange_while_host_pauses():
    state = at_choice()
    act(state, 4, 'choose', targets=[8])
    act(state, 8, 'choose', value=True)
    act(state, 1, 'advance', now=1060)
    act(state, 1, 'pause', now=1070)
    act(state, 8, 'withdraw_exchange', now=1080)
    assert state.current.exchanges[0].status == 'withdrawn'
    assert state.status == 'paused' and state.current.phase == 'transition'
    assert state.current.deadline is None
