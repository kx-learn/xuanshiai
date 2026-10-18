"""Loopback TCP WebSocket integration with actual login, MySQL and Redis."""
import asyncio
from datetime import UTC, datetime
import json
import os
import socket
from urllib.parse import urlparse
import uuid

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv('RUN_LIVE_BUSINESS') != '1' or os.getenv('RUN_LIVE_MYSQL') != '1',
    reason='Requires the owned temporary MySQL + Redis live-business runner',
)


def test_real_websocket_role_privacy_reconnect_and_revocation():
    from httpx import AsyncClient
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    import uvicorn
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed, InvalidStatus

    from app.core.config import settings
    from app.core.redis import redis_client
    from app.db.session import engine, session_factory
    from app.main import app

    database = make_url(settings.database_url)
    assert settings.environment == 'testing'
    assert settings.live_media_mode == 'disabled'
    assert settings.sms_provider == 'mock'
    assert database.host in ('127.0.0.1', 'localhost')
    assert database.database and 'test' in database.database.lower()
    assert urlparse(settings.redis_url).hostname in ('127.0.0.1', 'localhost')

    async def run():
        server = None
        server_task = None
        listener = None
        sockets = {}
        all_sockets = []
        last_revision = {}
        tokens = {}
        try:
            assert await redis_client.ping() is True
            async with session_factory() as db:
                for uid in range(2001, 2022):
                    await db.execute(text(
                        "INSERT INTO users (id,phone,nickname,gender,birthday,is_married,data_complete_rate) "
                        "VALUES (:id,:phone,:name,:gender,'1996-05-01',1,100)"
                    ), {'id': uid, 'phone': f'13900{uid:06d}', 'name': f'实时业务演练用户{uid}',
                        'gender': 1 if uid in [2004, 2005, 2006, 2007] else 2})
                    await db.execute(text('INSERT INTO user_auth (user_id,realname_status) VALUES (:id,2)'), {'id': uid})
                    await db.execute(text('INSERT INTO user_profile_completion (user_id,score) VALUES (:id,100)'), {'id': uid})
                for uid in [2020, 2021]:
                    await db.execute(text("INSERT INTO user_role (user_id,role_code,status) VALUES (:id,'admin',1)"), {'id': uid})
                await db.commit()

            # A bound loopback socket reserves the random port for this server only.
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            listener.setblocking(False)
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(
                app, host='127.0.0.1', port=port, loop='asyncio', lifespan='off',
                log_level='error', access_log=False, timeout_graceful_shutdown=12,
            ))
            server_task = asyncio.create_task(server.serve(sockets=[listener]))
            async with asyncio.timeout(5):
                while not server.started:
                    if server_task.done():
                        await server_task
                        raise AssertionError('The owned loopback API server stopped before startup')
                    await asyncio.sleep(0.01)

            async with AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                for uid in range(2001, 2022):
                    phone = f'13900{uid:06d}'
                    sent = await client.post('/api/v1/auth/sms/send', json={'phone': phone, 'purpose': 'login'})
                    assert sent.status_code == 202, (uid, sent.status_code)
                    logged_in = await client.post('/api/v1/auth/phone/login', json={
                        'phone': phone, 'purpose': 'login', 'code': settings.sms_mock_code,
                        'device_id': f'live-ws-{uid}', 'platform': 'mp-weixin',
                    })
                    assert logged_in.status_code == 200, (uid, logged_in.status_code)
                    assert logged_in.json()['user_id'] == uid
                    tokens[uid] = logged_in.json()['access_token']

                async def req(uid, method, path, expected=200, **kwargs):
                    response = await client.request(method, '/api/v1' + path,
                        headers={'Authorization': 'Bearer ' + tokens[uid]}, **kwargs)
                    assert response.status_code == expected, (method, path, response.status_code, response.text)
                    return response.json() if response.content else None

                create_body = {
                    'title': '真实 WebSocket 多角色演练', 'scheduled_at': int(datetime.now(UTC).timestamp()) + 3600,
                    'host_id': 2001, 'matchmaker_ids': [2002, 2003],
                    'male_ids': [2004, 2005, 2006, 2007], 'female_ids': [2008, 2009, 2010, 2011],
                    'main_order': [2004, 2008, 2005, 2009], 'spectator_ids': [2012],
                    'notice': '合成实时测试：仅展示本人授权资料，本场不使用音视频服务。',
                }
                created = await req(2020, 'POST', '/live/v2/sessions', 201, json=create_body)
                sid, root = created['id'], f"/live/v2/sessions/{created['id']}"
                ws_url = f'ws://127.0.0.1:{port}/api/v1{root}/events'

                async def command(uid, action, expected=200, **fields):
                    fresh = await req(uid, 'GET', root)
                    return await req(uid, 'POST', root + '/commands', expected, json={
                        'command_id': uuid.uuid4().hex, 'expected_revision': fresh['revision'],
                        'action': action, **fields,
                    })

                async def confirm(uid):
                    await command(uid, 'accept', value=True, consent_version='live-trial-v1',
                                  display_name=f'实时用户{uid}', introduction='本人授权公开的介绍')
                    return await command(uid, 'check_in', device_checked=False)

                for uid in range(2001, 2013):
                    prepared = await confirm(uid)

                async def open_socket(uid, query=''):
                    connection = await connect(ws_url + query,
                        additional_headers={'Authorization': 'Bearer ' + tokens[uid]},
                        proxy=None, open_timeout=3, close_timeout=1)
                    sockets[uid] = connection
                    all_sockets.append(connection)
                    return connection

                async def expect_handshake_denied(uid=None, query=''):
                    headers = {'Authorization': 'Bearer ' + tokens[uid]} if uid is not None else None
                    with pytest.raises(InvalidStatus) as error:
                        async with connect(ws_url + query, additional_headers=headers,
                                           proxy=None, open_timeout=3, close_timeout=1):
                            pytest.fail('Unauthorized WebSocket handshake unexpectedly succeeded')
                    # ASGI close-before-accept rejects the HTTP upgrade; close codes apply after acceptance.
                    assert error.value.response.status_code == 403

                await expect_handshake_denied(query='?role=host&user_id=2001')
                await expect_handshake_denied(2021)
                await expect_handshake_denied(2017, '?role=operator&user_id=2020')

                async def snapshot_at(uid, revision):
                    async with asyncio.timeout(5):
                        while True:
                            envelope = json.loads(await sockets[uid].recv())
                            if envelope['type'] == 'heartbeat':
                                assert set(envelope) == {'type', 'server_time'}
                                continue
                            assert set(envelope) == {'type', 'snapshot'}
                            view = envelope['snapshot']
                            assert view['me']['user_id'] == uid
                            assert view['media_mode'] == 'disabled'
                            assert not {'selections', 'credentials', 'user_sig', 'sdk_secret'} & set(view)
                            assert all('selection' not in member and 'selections' not in member for member in view['members'])
                            assert view['revision'] >= last_revision.get(uid, -1)
                            last_revision[uid] = view['revision']
                            if view['revision'] < revision:
                                continue
                            assert view['revision'] == revision
                            return view

                async def synchronized(revision, private=None):
                    ids = list(sockets)
                    views = await asyncio.gather(*(snapshot_at(uid, revision) for uid in ids))
                    result = dict(zip(ids, views, strict=True))
                    assert {view['revision'] for view in views} == {revision}
                    if private is not None:
                        for uid, view in result.items():
                            assert view['me']['selection'] == private.get(uid, [])
                    return result

                for uid in [2001, 2002, 2003, 2004, 2008, 2012, 2020]:
                    await open_socket(uid, '?role=operator&user_id=2020&mode=demo' if uid == 2012 else '')
                initial = await synchronized(prepared['revision'], private={})
                assert initial[2001]['me']['role'] == 'host'
                assert initial[2002]['me']['role'] == 'matchmaker'
                assert initial[2004]['me']['role'] == 'guest'
                assert initial[2012]['me']['role'] == 'spectator'
                assert not {'advance', 'take_control', 'choose', 'stage'} & set(initial[2012]['allowed_actions'])

                # Updating the roster re-evaluates the same authenticated sockets; no client role cache wins.
                original_host_socket = sockets[2001]
                original_matchmaker_socket = sockets[2002]
                create_body.update(host_id=2002, matchmaker_ids=[2001, 2003])
                edited = await req(2020, 'PUT', root,
                    json={**create_body, 'expected_revision': prepared['revision']})
                changed = await synchronized(edited['revision'], private={})
                assert sockets[2001] is original_host_socket and sockets[2002] is original_matchmaker_socket
                assert changed[2001]['me']['role'] == 'matchmaker'
                assert changed[2002]['me']['role'] == 'host'
                assert all(view['controller_id'] == 2002 for view in changed.values())
                assert changed[2001]['me']['invitation'] == changed[2002]['me']['invitation'] == 'pending'
                await confirm(2001)
                checked = await confirm(2002)
                await synchronized(checked['revision'], private={})
                started = await command(2002, 'start')
                live_views = await synchronized(started['revision'], private={})
                assert 'advance' in live_views[2002]['allowed_actions']
                assert 'advance' not in live_views[2001]['allowed_actions']

                taken = await command(2020, 'take_control', reason='测试运营明确接管主持流程')
                takeover = await synchronized(taken['revision'], private={})
                assert all(view['controller_id'] == 2020 for view in takeover.values())
                assert 'advance' in takeover[2020]['allowed_actions']
                assert 'advance' not in takeover[2002]['allowed_actions']
                assert takeover[2002]['me']['role'] == 'host'
                assert not next(member for member in takeover[2020]['members'] if member['user_id'] == 2020)['on_stage']
                await command(2002, 'advance', 403)
                returned = await command(2020, 'return_control', reason='测试交还主持流程权限')
                restored = await synchronized(returned['revision'], private={})
                assert all(view['controller_id'] == 2002 for view in restored.values())
                assert 'advance' in restored[2002]['allowed_actions']
                assert 'advance' not in restored[2020]['allowed_actions']

                for _ in range(3):
                    choice = await command(2002, 'advance')
                assert choice['phase'] == 'choice'
                await synchronized(choice['revision'], private={})
                selected = await command(2004, 'choose', targets=[2008])
                await synchronized(selected['revision'], private={2004: [2008]})
                willing = await command(2008, 'choose', value=True)
                private_views = await synchronized(willing['revision'], private={2004: [2008], 2008: [2004]})
                assert all(view['exchanges'] == [] for view in private_views.values())

                # Dropping a socket is not leaving; reconnect receives latest state without replaying any command.
                disconnected = sockets.pop(2004)
                await disconnected.close()
                changed_choice = await command(2004, 'choose', targets=[2009])
                await synchronized(changed_choice['revision'], private={2008: [2004]})
                before_reconnect = await req(2004, 'GET', root)
                async with session_factory() as db:
                    actions_before = (await db.execute(text('SELECT COUNT(*) FROM live_v2_action WHERE session_id=:sid'), {'sid': sid})).scalar_one()
                assert before_reconnect['me']['checked_in']
                assert next(member for member in before_reconnect['members'] if member['user_id'] == 2004)['attendance'] != 'left'
                await open_socket(2004)
                reconnected = await snapshot_at(2004, changed_choice['revision'])
                assert reconnected['me']['selection'] == [2009]
                assert (await req(2004, 'GET', root))['revision'] == changed_choice['revision']
                async with session_factory() as db:
                    assert (await db.execute(text('SELECT COUNT(*) FROM live_v2_action WHERE session_id=:sid'), {'sid': sid})).scalar_one() == actions_before

                async def expect_closed(connection, code):
                    with pytest.raises(ConnectionClosed) as error:
                        async with asyncio.timeout(5):
                            while True:
                                await connection.recv()
                    assert error.value.rcvd is not None and error.value.rcvd.code == code

                viewer = sockets.pop(2012)
                removed = await command(2020, 'remove', target_id=2012, reason='测试场内移出观众')
                await expect_closed(viewer, 4403)
                await synchronized(removed['revision'], private={2004: [2009], 2008: [2004]})
                await expect_handshake_denied(2012)

                matchmaker = sockets.pop(2003)
                await req(2003, 'POST', '/auth/logout', 204)
                await req(2003, 'GET', '/auth/me', 401)
                awakened = await command(2002, 'extend', seconds=30)
                await expect_closed(matchmaker, 4401)
                await synchronized(awakened['revision'], private={2004: [2009], 2008: [2004]})
                await expect_handshake_denied(2003)

                # Close clients, then a genuine room mutation wakes existing subscriptions for clean disposal.
                await asyncio.gather(*(connection.close() for connection in all_sockets))
                ended = await command(2002, 'end')
                assert ended['status'] == 'ended'
                sockets.clear()
        finally:
            await asyncio.gather(*(connection.close() for connection in all_sockets), return_exceptions=True)
            if server is not None:
                server.should_exit = True
            if server_task is not None:
                await asyncio.wait_for(server_task, timeout=15)
            if listener is not None:
                listener.close()
            await redis_client.aclose()
            await engine.dispose()

    asyncio.run(run())
