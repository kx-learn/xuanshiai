"""Real login, MySQL and Redis business rehearsal; Tencent is forbidden, not faked."""
import asyncio
from datetime import UTC, datetime
import json
import os
from urllib.parse import urlparse
import uuid

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv('RUN_LIVE_BUSINESS') != '1' or os.getenv('RUN_LIVE_MYSQL') != '1',
    reason='Requires the owned temporary MySQL + Redis live-business runner',
)


def test_real_business_rehearsal_without_media(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from app.core.config import settings
    from app.core import redis as quota
    from app.db.session import engine, session_factory
    from app.main import app
    from app.services import discovery, live_v2 as live, live_media

    # Explicit execution flag is not enough to permit writes into a normal local database.
    database = make_url(settings.database_url)
    assert settings.environment == 'testing'
    assert settings.live_media_mode == 'disabled'
    assert settings.sms_provider == 'mock'
    assert database.host in ('127.0.0.1', 'localhost')
    assert database.database and 'test' in database.database.lower()
    assert urlparse(settings.redis_url).hostname in ('127.0.0.1', 'localhost')
    assert settings.live_sdk_app_id == 0
    for name in ('live_sdk_secret', 'live_cloud_secret_id', 'live_cloud_secret_key',
                 'live_cdn_push_key', 'live_cdn_play_key'):
        assert not getattr(settings, name), f'Test environment must leave {name} empty'

    clock = [int(datetime.now(UTC).timestamp())]
    monkeypatch.setattr(live, 'time', type('Clock', (), {'time': staticmethod(lambda: clock[0])}))
    cloud_attempts = []

    async def forbidden_cloud(*args, **kwargs):
        cloud_attempts.append('cloud_api')
        raise AssertionError('A media-disabled business session must not call Tencent')

    def forbidden_signature(*args, **kwargs):
        cloud_attempts.append('signature')
        raise AssertionError('A media-disabled business session must not generate media credentials')

    monkeypatch.setattr(live_media, 'cloud_call', forbidden_cloud)
    monkeypatch.setattr(live_media, 'signer', forbidden_signature)
    monkeypatch.setattr(live_media, 'signed_cdn_url', forbidden_signature)

    async def run():
        redis = quota.redis_client
        pubsub = None
        observed_revisions = []
        tokens = {}
        local_quota_before = dict(quota._local_quota_counts)
        try:
            assert await redis.ping() is True
            async with session_factory() as db:
                for uid in range(1001, 1022):
                    await db.execute(text(
                        "INSERT INTO users (id,phone,nickname,gender,birthday,is_married,data_complete_rate) "
                        "VALUES (:id,:phone,:name,:gender,'1996-05-01',1,100)"
                    ), {'id': uid, 'phone': f'13900{uid:06d}', 'name': f'业务演练用户{uid}',
                        'gender': 1 if uid in [1004, 1005, 1006, 1007, 1013] else 2})
                    await db.execute(text('INSERT INTO user_auth (user_id,realname_status) VALUES (:id,:status)'),
                                     {'id': uid, 'status': 0 if uid == 1018 else 2})
                    await db.execute(text('INSERT INTO user_profile_completion (user_id,score) VALUES (:id,100)'), {'id': uid})
                for uid in [1020, 1021]:
                    await db.execute(text("INSERT INTO user_role (user_id,role_code,status) VALUES (:id,'admin',1)"), {'id': uid})
                await db.commit()

            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://live-test') as client:
                for uid in range(1001, 1022):
                    phone = f'13900{uid:06d}'
                    sent = await client.post('/api/v1/auth/sms/send', json={'phone': phone, 'purpose': 'login'})
                    assert sent.status_code == 202, (uid, sent.status_code)
                    logged_in = await client.post('/api/v1/auth/phone/login', json={
                        'phone': phone, 'purpose': 'login', 'code': settings.sms_mock_code,
                        'device_id': f'live-business-{uid}', 'platform': 'mp-weixin',
                    })
                    assert logged_in.status_code == 200, (uid, logged_in.status_code)
                    payload = logged_in.json()
                    assert payload['user_id'] == uid
                    assert payload['need_bind_phone'] is False
                    tokens[uid] = payload['access_token']

                async def req(uid, method, path, expected=200, **kwargs):
                    headers = {'Authorization': 'Bearer ' + tokens[uid]} if uid is not None else {}
                    response = await client.request(method, '/api/v1' + path, headers=headers, **kwargs)
                    assert response.status_code == expected, (method, path, response.status_code, response.text)
                    return response.json() if response.content else None

                await req(None, 'GET', '/live/v2/sessions', 401)
                assert (await req(1004, 'GET', '/auth/me'))['id'] == 1004
                async with session_factory() as db:
                    sessions = (await db.execute(text(
                        'SELECT COUNT(*) FROM user_session WHERE user_id BETWEEN 1001 AND 1021 AND status=1'
                    ))).scalar_one()
                    assert sessions == 21

                # Searching existing accounts does not grant access to their private data or sessions.
                await req(1004, 'GET', '/live/v2/accounts?q=业务演练&page=1&page_size=20', 403)
                search = await req(1020, 'GET', '/live/v2/accounts?q=业务演练&page=1&page_size=20')
                assert search['total'] == 21 and search['has_more']
                assert len(search['items']) == 20
                assert all(set(item) == {'user_id', 'nickname', 'gender', 'eligible', 'missing'} for item in search['items'])
                assert 'phone' not in json.dumps(search)
                second_page = await req(1020, 'GET', '/live/v2/accounts?q=业务演练&page=2&page_size=20')
                assert len(second_page['items']) == 1 and not second_page['has_more']
                unverified = await req(1020, 'GET', '/live/v2/accounts?q=1018&page=1&page_size=20')
                assert unverified['items'][0]['eligible'] is False
                assert '实名认证' in unverified['items'][0]['missing']
                assert (await req(1020, 'GET', '/live/v2/accounts?q=没有此合成账号&page=1&page_size=20'))['items'] == []

                resources = await req(1020, 'GET', '/live/v2/resources')
                assert resources['media_mode'] == 'disabled'
                assert resources['ready'] and resources['business_ready']
                assert resources['missing'] == resources['business_missing'] == []
                assert resources['media_ready'] is False
                assert 'LIVE_SDK_SECRET' in resources['media_missing']

                create_body = {
                    'title': '真实四轮无媒体演练', 'scheduled_at': clock[0] + 3600, 'host_id': 1001,
                    'matchmaker_ids': [1002, 1003], 'male_ids': [1004, 1005, 1006, 1007],
                    'female_ids': [1008, 1009, 1010, 1011], 'main_order': [1004, 1008, 1005, 1009],
                    'spectator_ids': [1012], 'notice': '合成测试：仅向受邀人员展示已授权资料，未启用音视频。',
                }
                await req(1004, 'POST', '/live/v2/sessions', 403, json=create_body)
                await req(1020, 'POST', '/live/v2/sessions', 422, json={**create_body, 'host_id': 1020})
                created = await req(1020, 'POST', '/live/v2/sessions', 201, json=create_body)
                sid, root = created['id'], f"/live/v2/sessions/{created['id']}"
                assert created['media_mode'] == 'disabled'
                listings = await req(1020, 'GET', '/live/v2/sessions')
                assert listings['items'] and all(item['media_mode'] == 'disabled' for item in listings['items'])
                assert created['controller_id'] == 1001 and created['owner_id'] == 1020
                assert created['me']['role'] == 'operator' and len(created['members']) == 13
                await req(1021, 'GET', root, 404)
                await req(1017, 'GET', root, 404)
                assert not (await req(1021, 'GET', '/live/v2/sessions'))['items']

                async def notification_users(event, session_id=sid):
                    async with session_factory() as db:
                        return set((await db.execute(text(
                            'SELECT user_id FROM user_notification WHERE notification_type=:event '
                            "AND target_type='live_v2_session' AND target_id=:sid"
                        ), {'event': event, 'sid': session_id})).scalars().all())

                assert await notification_users('live_invitation') == set(range(1001, 1013))

                async def consume_revision(expected):
                    async with asyncio.timeout(3):
                        while True:
                            event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
                            if event is None:
                                continue
                            assert event['type'] == 'message'
                            assert event['channel'] == f'live:v2:{sid}:revision'
                            assert str(event['data']).isdecimal(), event
                            assert int(event['data']) == expected
                            observed_revisions.append(expected)
                            return

                async def command(uid, action, expected=200, **extra):
                    fresh = await req(uid, 'GET', root)
                    result = await req(uid, 'POST', root + '/commands', expected, json={
                        'command_id': uuid.uuid4().hex, 'expected_revision': fresh['revision'],
                        'action': action, **extra,
                    })
                    if expected == 200 and pubsub is not None:
                        await consume_revision(result['revision'])
                    return result

                async def confirm(uid):
                    await command(uid, 'accept', value=True, consent_version='live-trial-v1',
                                  display_name=f'本场用户{uid}', introduction='本人已授权的简短介绍')
                    return await command(uid, 'check_in', device_checked=False)

                await command(1012, 'reserve', value=True)
                declined = await command(1012, 'decline')
                assert declined['me']['invitation'] == 'declined'
                assert declined['me']['reserved'] is True and declined['me']['checked_in'] is False
                await confirm(1001)
                await command(1001, 'start', 409)
                for uid in range(1002, 1013):
                    checked = await confirm(uid)
                    assert checked['me']['accepted'] and checked['me']['checked_in']
                assert await notification_users('live_invitation_response') == {1020}

                async def edit(**changes):
                    fresh = await req(1020, 'GET', root)
                    body = {**create_body, **changes, 'expected_revision': fresh['revision']}
                    result = await req(1020, 'PUT', root, json=body)
                    create_body.update(changes)
                    return result

                fresh = await req(1020, 'GET', root)
                await req(1001, 'PUT', root, 403, json={**create_body, 'expected_revision': fresh['revision']})
                await req(1021, 'PUT', root, 404, json={**create_body, 'expected_revision': fresh['revision']})
                renamed = await edit(title='已调整标题的真实业务演练')
                assert all(member['checked_in'] for member in renamed['members'] if member['role'] != 'operator')
                await req(1020, 'PUT', root, 409, json={**create_body, 'expected_revision': fresh['revision']})
                reseated = await edit(male_ids=[1005, 1004, 1006, 1007])
                by_id = {member['user_id']: member for member in reseated['members']}
                assert by_id[1004]['invitation'] == by_id[1005]['invitation'] == 'pending'
                assert not by_id[1004]['checked_in'] and by_id[1008]['checked_in']
                await edit(male_ids=[1004, 1005, 1006, 1007])
                for uid in [1004, 1005]:
                    await confirm(uid)

                await edit(spectator_ids=[1013])
                await req(1012, 'GET', root, 404)
                assert (await req(1013, 'GET', root))['me']['invitation'] == 'pending'
                async with session_factory() as db:
                    indexed = set((await db.execute(text('SELECT user_id FROM live_v2_member WHERE session_id=:sid'), {'sid': sid})).scalars().all())
                    assert 1012 not in indexed and 1013 in indexed and len(indexed) == 13
                await edit(spectator_ids=[1012])
                await req(1013, 'GET', root, 404)
                changed = await edit(scheduled_at=clock[0] + 7200,
                                     notice='演练安排更新：只显示本人授权资料，本场音视频始终关闭。')
                assert all(member['invitation'] == 'pending' and not member['checked_in']
                           for member in changed['members'] if member['role'] != 'operator')
                for uid in range(1001, 1013):
                    await confirm(uid)
                assert {1012, 1013} <= await notification_users('live_changed')
                await command(1020, 'schedule')
                assert await notification_users('live_scheduled') == set(range(1001, 1013))

                # A second administrator owns a different session, not this one.
                other = await req(1021, 'POST', '/live/v2/sessions', 201, json={**create_body, 'title': '另一运营的独立场次'})
                other_root = f"/live/v2/sessions/{other['id']}"
                await req(1020, 'GET', other_root, 404)
                cancelled = await req(1021, 'POST', other_root + '/commands', json={
                    'command_id': uuid.uuid4().hex, 'expected_revision': other['revision'], 'action': 'cancel',
                })
                assert cancelled['status'] == 'cancelled'
                assert await notification_users('live_cancelled', other['id']) == set(range(1001, 1013))

                # From now on every successful room command must produce a real revision-only Redis event.
                pubsub = redis.pubsub()
                await pubsub.subscribe(f'live:v2:{sid}:revision')
                started = await command(1001, 'start')
                assert started['status'] == 'live' and len([member for member in started['members'] if member['on_stage']]) == 8
                assert not next(member for member in started['members'] if member['user_id'] == 1020)['on_stage']
                for uid in [1001, 1004, 1012]:
                    media_error = await req(uid, 'POST', root + '/credentials', 409)
                    assert '未启用音视频' in media_error['detail']
                await req(1020, 'PUT', root, 409, json={**create_body, 'expected_revision': started['revision']})
                await req(1004, 'POST', root + '/commands', 422, json={
                    'command_id': uuid.uuid4().hex, 'expected_revision': started['revision'],
                    'action': 'advance', 'role': 'host',
                })

                stale_control = {'command_id': uuid.uuid4().hex, 'expected_revision': started['revision'], 'action': 'advance'}
                taken = await command(1020, 'take_control', reason='主持连接中断，由运营明确接管')
                assert taken['controller_id'] == 1020
                assert next(member for member in taken['members'] if member['user_id'] == 1001)['role'] == 'host'
                assert not next(member for member in taken['members'] if member['user_id'] == 1020)['on_stage']
                await command(1001, 'advance', 403)
                await req(1001, 'POST', root + '/commands', 409, json=stale_control)
                await req(1001, 'POST', root + '/commands', 409, json=stale_control)
                paused = await command(1020, 'pause')
                remaining = paused['pause_remaining']
                clock[0] += 30
                await command(1001, 'resume', 403)
                await command(1020, 'return_control', reason='主持连接恢复，交还控场')
                resumed = await command(1001, 'resume')
                assert resumed['deadline'] == clock[0] + remaining
                await command(1020, 'advance', 403)

                await command(1001, 'advance')
                for uid in [1005, 1006, 1007, 1012]:
                    await command(uid, 'hand', 403, value=True)
                await command(1001, 'remove', 403, target_id=1020, reason='主持无权移出运营')
                await command(1001, 'stage', 403, target_id=1005, value=True)
                await command(1002, 'stage', 403, target_id=1008, value=False)
                await command(1002, 'hand', value=True)
                await command(1002, 'hand', value=False)
                await command(1003, 'hand', value=True)
                await command(1001, 'speaker', target_id=1003)
                await command(1008, 'hand', value=True)
                paused = await command(1001, 'pause')
                assert 'hand' not in (await req(1002, 'GET', root))['allowed_actions']
                await command(1002, 'hand', 409, value=True)
                await command(1001, 'advance', 409)
                await command(1001, 'resume')

                async def select_phase():
                    fresh = await req(1001, 'GET', root)
                    while fresh['phase'] != 'choice':
                        fresh = await command(1001, 'advance')
                    return fresh

                # Round one: interest is reversible; private choices produce three seat-ordered pairs.
                interest = await command(1001, 'advance')
                assert interest['phase'] == 'interest' and not any(member['hand'] for member in interest['members'])
                await command(1008, 'special', value=True, target_id=1004)
                await command(1008, 'special', value=False)
                await command(1008, 'special', 409, value=True, target_id=1004)
                await command(1009, 'light', value=True, target_id=1004)
                await command(1009, 'light', value=False)
                await command(1012, 'light', 403, value=True, target_id=1004)
                choice = await command(1001, 'advance')
                await command(1004, 'choose', targets=[1008])
                await command(1004, 'choose', targets=[1010, 1008, 1009])
                for uid in [1008, 1009, 1010]:
                    await command(uid, 'choose', value=True)
                for uid in [1001, 1002, 1003, 1005, 1012, 1020]:
                    await command(uid, 'choose', 403, targets=[1008], value=True)
                    private = await req(uid, 'GET', root)
                    assert private['me']['selection'] == [] and private['exchanges'] == []
                    assert 'selections' not in json.dumps(private) and 'user_sig' not in json.dumps(private)
                assert (await req(1004, 'GET', root))['me']['selection'] == [1010, 1008, 1009]
                await command(1001, 'advance', 409)
                clock[0] = choice['deadline']
                await command(1004, 'choose', 409, targets=[])
                first_pairs = await command(1001, 'advance')
                assert [pair['candidate_id'] for pair in first_pairs['exchanges']] == [1008, 1009, 1010]
                for _ in range(3):
                    clock[0] += 120
                    await command(1001, 'advance')
                await command(1001, 'advance')

                # Round two: mismatched unilateral intentions produce no substitute pairing.
                choice = await select_phase()
                assert choice['main_id'] == 1008
                await command(1008, 'choose', targets=[1006])
                await command(1006, 'choose', value=False)
                await command(1007, 'choose', value=True)
                clock[0] = choice['deadline']
                no_mutual = await command(1001, 'advance')
                assert no_mutual['exchanges'] == [] and no_mutual['phase'] == 'transition'
                await command(1001, 'advance')

                # Round three: only the completed pair earns a grant; the second participant exits.
                choice = await select_phase()
                assert choice['main_id'] == 1005
                await command(1005, 'choose', targets=[1010, 1008])
                for uid in [1008, 1010]:
                    await command(uid, 'choose', value=True)
                clock[0] = choice['deadline']
                await command(1001, 'advance')
                clock[0] += 120
                await command(1001, 'advance')
                await command(1001, 'pause')
                withdrawn = await command(1010, 'withdraw_exchange')
                assert withdrawn['status'] == 'paused' and withdrawn['phase'] == 'transition'
                assert [pair['status'] for pair in withdrawn['exchanges']] == ['completed', 'withdrawn']
                await command(1001, 'resume')
                await command(1001, 'advance')

                # Round four: an already-completed reverse pair is omitted; a new pair completes.
                choice = await select_phase()
                assert choice['main_id'] == 1009
                await command(1009, 'choose', targets=[1004, 1006])
                for uid in [1004, 1006]:
                    await command(uid, 'choose', value=True)
                clock[0] = choice['deadline']
                deduped = await command(1001, 'advance')
                assert [pair['candidate_id'] for pair in deduped['exchanges']] == [1006]
                clock[0] += 120
                await command(1001, 'advance')
                finished = await command(1001, 'advance')
                assert finished['phase'] == 'completed' and finished['round_index'] == 3
                await command(1020, 'remove', target_id=1004, reason='参与者已退出场内，保留已完成交流')
                await req(1004, 'GET', root, 403)
                ended = await command(1001, 'end')
                assert ended['status'] == 'ended' and ended['allowed_actions'] == []
                assert await notification_users('live_result') == set(range(1001, 1013))

                # Audit readers see actions and outcomes, never another person's private choice.
                await req(1008, 'GET', root + '/actions?page=1&page_size=20', 403)
                await req(1021, 'GET', root + '/actions?page=1&page_size=20', 404)
                audit = []
                page = 1
                while True:
                    result = await req(1002, 'GET', root + f'/actions?page={page}&page_size=20')
                    audit.extend(result['items'])
                    if not result['has_more']:
                        assert result['total'] == len(audit)
                        break
                    page += 1
                assert any(item['action'] == 'take_control' and item['outcome'] == 'accepted' for item in audit)
                assert any(item['action'] == 'return_control' and item['outcome'] == 'accepted' for item in audit)
                assert sum(item['action'] == 'advance' and item['user_id'] == 1001 and item['outcome'] == 'rejected' for item in audit) >= 2
                assert all(set(item) <= {'id', 'user_id', 'action', 'revision', 'outcome', 'target_id', 'reason', 'created_at'} for item in audit)
                for item in audit:
                    if item['action'] == 'choose':
                        assert item['target_id'] is None and item['reason'] == ''

                results = await req(1004, 'GET', root + '/results')
                assert results['media_mode'] == 'disabled'
                assert results['session_ended'] and len(results['items']) == 3
                grants = {item['peer_id']: item['id'] for item in results['items']}
                assert all(item['expires_at'] == clock[0] + 72 * 3600 for item in results['items'])
                peer_results = await req(1008, 'GET', root + '/results')
                assert next(item['id'] for item in peer_results['items'] if item['peer_id'] == 1004) == grants[1008]
                assert {item['peer_id'] for item in (await req(1005, 'GET', root + '/results'))['items']} == {1008}
                assert {item['peer_id'] for item in (await req(1010, 'GET', root + '/results'))['items']} == {1004}
                await req(1021, 'GET', root + '/results', 404)

                # Exhaust real Redis quota; a live grant must not consume or refund it.
                keys = {uid: await discovery._quota_key('apply', uid) for uid in [1004, 1008]}
                limit = settings.apply_daily_free_limit
                for key in keys.values():
                    await redis.set(key, str(limit), ex=3600)
                await req(1004, 'POST', '/discovery/applications/1011', 429, json={'message': '日常次数已经用完'})

                async def free_apply(uid, peer, grant, expected=201):
                    return await req(uid, 'POST', f'/discovery/applications/{peer}', expected,
                                     json={'message': '愿意自愿继续认识', 'live_opportunity_id': grant})

                applications = await asyncio.gather(
                    free_apply(1004, 1008, grants[1008]), free_apply(1008, 1004, grants[1008]),
                )
                assert applications[0]['id'] == applications[1]['id']
                assert all(int(value) == limit for value in await redis.mget(list(keys.values())))
                application = applications[0]
                await req(application['to_user_id'], 'POST', f"/discovery/applications/{application['id']}/reject",
                          json={'reason': '暂不进一步认识'})
                assert all(int(value) == limit for value in await redis.mget(list(keys.values())))
                replay = await free_apply(1004, 1008, grants[1008])
                assert replay['id'] == application['id'] and replay['status'] == 2
                assert not (await req(1004, 'GET', '/message/chat/permission?userId=1008'))['canChat']
                await free_apply(1004, 1011, grants[1008], 403)

                async with session_factory() as db:
                    await db.execute(text('UPDATE live_v2_opportunity SET expires_at=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE id=:id'), {'id': grants[1009]})
                    await db.commit()
                await free_apply(1004, 1009, grants[1009], 410)
                pending = await free_apply(1004, 1010, grants[1010])
                assert not (await req(1004, 'GET', '/message/chat/permission?userId=1010'))['canChat']
                await req(1004, 'POST', '/message/send', 403, json={
                    'userId': 1010, 'type': 'text', 'content': '未同意前不得发送', 'clientMessageId': uuid.uuid4().hex,
                })
                await req(1020, 'POST', f"/discovery/applications/{pending['id']}/accept", 404)
                await req(1010, 'POST', f"/discovery/applications/{pending['id']}/accept")
                assert (await req(1004, 'GET', '/message/chat/permission?userId=1010'))['canChat']
                sent = await req(1004, 'POST', '/message/send', json={
                    'userId': 1010, 'type': 'text', 'content': '场后双方同意，开始交流', 'clientMessageId': uuid.uuid4().hex,
                })
                assert sent['success'] and sent['messageId'] > 0
                assert any(item['content'] == '场后双方同意，开始交流' for item in await req(1010, 'GET', '/message/chat?userId=1004'))
                source = await req(1004, 'GET', '/message/applications?direction=outgoing')
                assert any(item['sourceText'] == '直播场后专属免费申请' for item in source['list'])
                assert all(int(value) == limit for value in await redis.mget(list(keys.values())))

                # A free opportunity still obeys existing block rules.
                fifth = (await req(1005, 'GET', root + '/results'))['items'][0]
                async with session_factory() as db:
                    await db.execute(text('INSERT INTO user_block (user_id,target_user_id) VALUES (1005,1008)'))
                    await db.commit()
                # Upstream visibility intentionally hides blocked profiles with 404.
                await free_apply(1005, 1008, fifth['id'], 404)

                async with session_factory() as db:
                    pairs = set((await db.execute(text('SELECT first_user_id,second_user_id FROM live_v2_opportunity WHERE session_id=:sid'), {'sid': sid})).tuples().all())
                    assert pairs == {(1004, 1008), (1004, 1009), (1004, 1010), (1005, 1008), (1006, 1009)}
                    assert (await db.execute(text('SELECT COUNT(*) FROM match_apply WHERE '
                        '(from_user_id=1004 AND to_user_id=1008) OR (from_user_id=1008 AND to_user_id=1004)'))).scalar_one() == 1
                    raw = (await db.execute(text('SELECT state FROM live_v2_session WHERE id=:sid'), {'sid': sid})).scalar_one()
                    stored = json.loads(raw) if isinstance(raw, str) else raw
                    assert stored['media_mode'] == 'disabled'
                    assert stored['media_room_id'] == stored['media_epoch'] == 0
                    assert stored['media_task_id'] is None
                    assert (await db.execute(text('SELECT COUNT(*) FROM live_v2_media_cleanup WHERE session_id=:sid'), {'sid': sid})).scalar_one() == 0
                await live_media.cleanup_once()
                assert len(observed_revisions) > 40
                assert observed_revisions == sorted(set(observed_revisions))
                assert quota._local_quota_counts == local_quota_before
                assert cloud_attempts == []
        finally:
            if pubsub is not None:
                await pubsub.aclose()
            await redis.aclose()
            await engine.dispose()

    asyncio.run(run())
