"""Actual MySQL + ASGI auth/routes/transactions; only Tencent and Redis are test doubles."""
import asyncio
from datetime import UTC, datetime, timedelta
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.getenv('RUN_LIVE_MYSQL') != '1', reason='Use isolated MySQL runner --tests tests/test_live_mysql.py')


def test_real_four_round_trial_and_free_application_atomicity(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from app.core.security import create_token
    from app.core import redis as quota
    from app.db.session import engine, session_factory
    from app.main import app
    from app.schemas.live_v2 import LiveResources
    from app.services import discovery, live_v2 as live, live_media

    clock = [int(datetime.now(UTC).timestamp())]
    monkeypatch.setattr(live, 'time', type('Clock', (), {'time': staticmethod(lambda: clock[0])}))
    async def no_network(*_):
        return None
    monkeypatch.setattr(live, 'publish_revision', no_network)

    async def run():
        async with session_factory() as db:
            for uid in range(1, 22):
                await db.execute(text("INSERT INTO users (id,phone,nickname,gender,birthday,is_married,data_complete_rate) VALUES (:id,:phone,:name,:gender,'1996-05-01',1,100)"),
                    {'id': uid, 'phone': f'live-test-{uid}', 'name': f'合成用户{uid}', 'gender': 1 if uid in [4,5,6,7] else 2})
                await db.execute(text('INSERT INTO user_auth (user_id,realname_status) VALUES (:id,2)'), {'id': uid})
                await db.execute(text('INSERT INTO user_profile_completion (user_id,score) VALUES (:id,100)'), {'id': uid})
                await db.execute(text("INSERT INTO user_session (id,user_id,refresh_token_hash,access_expire_at,refresh_expire_at) VALUES (:id,:id,:hash,UTC_TIMESTAMP()+INTERVAL 1 DAY,UTC_TIMESTAMP()+INTERVAL 2 DAY)"), {'id': uid, 'hash': str(uid).zfill(64)})
            await db.execute(text("INSERT INTO user_role (user_id,role_code,status) VALUES (20,'admin',1)"))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            async def req(uid, method, path, expected=200, **kwargs):
                response = await client.request(method, '/api/v1' + path, headers={'Authorization': 'Bearer ' + create_token(uid, uid, 'access', timedelta(days=1))}, **kwargs)
                assert response.status_code == expected, (method, path, response.status_code, response.text)
                return response.json()

            create_body = {'title':'四轮数据库演练', 'scheduled_at':clock[0]+3600, 'host_id':1,
                'matchmaker_ids':[2,3], 'male_ids':[4,5,6,7], 'female_ids':[8,9,10,11],
                'main_order':[4,8,5,9], 'spectator_ids':[12], 'notice':'合成测试：本场仅向受邀者展示现场音视频，不提供公开回放。'}
            await req(4, 'POST', '/live/v2/sessions', 403, json=create_body)
            state = await req(20, 'POST', '/live/v2/sessions', 201, json=create_body)
            sid, root = state['id'], f"/live/v2/sessions/{state['id']}"
            assert not (await req(21, 'GET', '/live/v2/sessions'))['items']
            await req(21, 'GET', root, 404)

            async def command(uid, action, expected=200, **extra):
                fresh = await req(uid, 'GET', root)
                return await req(uid, 'POST', root+'/commands', expected, json={'command_id': uuid.uuid4().hex,
                    'expected_revision': fresh['revision'], 'action': action, **extra})

            for uid in range(1,13):
                await command(uid, 'accept', value=True, consent_version='live-trial-v1', display_name=f'测试嘉宾{uid}', introduction='本人授权公开的介绍')
                await command(uid, 'check_in', device_checked=True)
            await command(1, 'start', 503)
            monkeypatch.setattr(live_media, 'resources', lambda **_: LiveResources(ready=True, missing=[]))
            await command(1, 'start')
            await command(12, 'light', 403, value=True, target_id=4)
            await command(2, 'choose', 403, targets=[8])
            for round_index in range(4):
                for _ in range(3):
                    await command(1, 'advance')
                fresh = await req(4, 'GET', root)
                main = fresh['main_id']
                if round_index == 0:
                    # Three mutual pairs, no public lights needed, seat order wins.
                    await command(main, 'choose', targets=[10,8,9])
                    for uid in [8,9,10]:
                        await command(uid, 'choose', value=True)
                    for uid in [1,2,3,12,20]:
                        private = await req(uid, 'GET', root)
                        assert private['me']['selection'] == [] and private['exchanges'] == []
                elif round_index == 1:
                    # Pair already completed is not reissued in reverse direction.
                    await command(8, 'choose', targets=[4])
                    await command(4, 'choose', value=True)
                await command(1, 'advance', 409)
                clock[0] += 60
                advanced = await command(1, 'advance')
                if round_index == 0:
                    assert [p['candidate_id'] for p in advanced['exchanges']] == [8,9,10]
                    for _ in range(3):
                        clock[0] += 120
                        await command(1, 'advance')
                else:
                    assert advanced['exchanges'] == []
                clock[0] += 60
                await command(1, 'advance')
            await command(1, 'end')
            outcomes = await req(4, 'GET', root+'/results')
            assert len(outcomes['items']) == 3 and outcomes['session_ended']
            grants = {item['peer_id']: item['id'] for item in outcomes['items']}
            # Exhaust daily quota. Opposite-direction requests still create one free apply.
            key4 = await discovery._quota_key('apply',4)
            key8 = await discovery._quota_key('apply',8)
            quota._local_quota_counts.update({key4:3, key8:3})
            async def free_apply(uid, peer, grant, expected=201):
                return await req(uid, 'POST', f'/discovery/applications/{peer}', expected,
                    json={'message':'愿意在场后继续认识', 'live_opportunity_id':grant})
            applications = await asyncio.gather(free_apply(4,8,grants[8]), free_apply(8,4,grants[8]))
            assert applications[0]['id'] == applications[1]['id']
            assert quota._local_quota_counts[key4] == quota._local_quota_counts[key8] == 3
            application = applications[0]
            await req(application['to_user_id'], 'POST', f"/discovery/applications/{application['id']}/reject", json={'reason':'暂不进一步认识'})
            assert quota._local_quota_counts[key4] == quota._local_quota_counts[key8] == 3
            replay = await free_apply(4,8,grants[8])
            assert replay['id'] == application['id'] and replay['status'] == 2
            await free_apply(4,11,grants[8],403)
            async with session_factory() as db:
                await db.execute(text('UPDATE live_v2_opportunity SET expires_at=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE id=:id'), {'id':grants[9]})
                await db.commit()
            await free_apply(4,9,grants[9],410)
            pending = await free_apply(4,10,grants[10])
            permission = await req(4, 'GET', '/message/chat/permission?userId=10')
            assert not permission['canChat']
            await req(10, 'POST', f"/discovery/applications/{pending['id']}/accept")
            assert (await req(4, 'GET', '/message/chat/permission?userId=10'))['canChat']
            source = await req(4, 'GET', '/message/applications?direction=outgoing')
            assert any(item['sourceText'] == '直播场后专属免费申请' for item in source['list'])
            async with session_factory() as db:
                count = (await db.execute(text('SELECT COUNT(*) FROM live_v2_opportunity WHERE session_id=:sid'), {'sid':sid})).scalar()
                assert count == 3
                count = (await db.execute(text('SELECT COUNT(*) FROM match_apply WHERE (from_user_id=4 AND to_user_id=8) OR (from_user_id=8 AND to_user_id=4)'))).scalar()
                assert count == 1
        await engine.dispose()
    asyncio.run(run())
