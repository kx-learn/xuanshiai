import base64
import json
import struct
import zlib

import pytest
from fastapi import HTTPException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from app.core.config import settings
from app.services.live_media import credentials_for, private_ticket, resources
from tests.test_live_domain import act, session


def test_resource_gate_reports_missing_without_exposing_secrets():
    assert not resources().ready
    assert 'LIVE_SDK_SECRET' in resources().missing


def test_private_ticket_has_room_bound_permission_bits(monkeypatch):
    monkeypatch.setattr(settings, 'live_sdk_app_id', 123456)
    monkeypatch.setattr(settings, 'live_sdk_secret', 'synthetic-test-secret')
    token = private_ticket('u4', 123, False, 60)
    doc = json.loads(zlib.decompress(base64.b64decode(token.translate(str.maketrans('*-_', '+/=')))))
    buf = base64.b64decode(doc['TLS.userbuf'])
    version, length = struct.unpack('!BH', buf[:3])
    app, room, expiry, permissions, account_type = struct.unpack('!IIIII', buf[3 + length:])
    assert version == 0 and buf[3:3+length] == b'u4'
    assert (app, room, permissions, account_type) == (123456, 123, 42, 0)
    assert permissions & 4 == 0 and permissions & 16 == 0


@pytest.mark.parametrize('uid', [12, 20])
def test_spectators_and_operator_never_receive_rtc_publishing_credentials(monkeypatch, uid):
    monkeypatch.setattr(settings, 'live_cdn_play_domain', 'play.example.test')
    monkeypatch.setattr(settings, 'live_cdn_play_key', 'synthetic')
    state = session()
    act(state, 1, 'start')
    credentials = credentials_for(state, uid)
    assert credentials.mode == 'cdn' and not credentials.user_sig and not credentials.private_map_key
    assert credentials.playback_url.startswith('https://play.example.test/')


@pytest.mark.asyncio
async def test_operator_watches_without_joining_interactive_checkin(monkeypatch):
    from app.services import live_v2 as live, live_media
    from app.schemas.live_v2 import LiveResources
    state = session()
    act(state, 1, 'start')
    next(m for m in state.members if m.role == 'operator').checked_in = False
    state.media_task_id = 'existing-test-task'
    async def loaded(*args, **kwargs):
        return state
    class Database:
        async def commit(self):
            pass
    monkeypatch.setattr(live, 'load_session', loaded)
    monkeypatch.setattr(live_media, 'resources', lambda **kw: LiveResources(ready=True, missing=[]))
    monkeypatch.setattr(settings, 'live_cdn_play_domain', 'play.example.test')
    monkeypatch.setattr(settings, 'live_cdn_play_key', 'synthetic')
    credential = await live_media.get_credentials(Database(), 1, 20)
    assert credential.mode == 'cdn' and not credential.publish and not credential.user_sig


def test_stage_revocation_rotates_room_so_old_ticket_cannot_enter_new_stage():
    state = session()
    act(state, 1, 'start')
    room, epoch = state.media_room_id, state.media_epoch
    act(state, 1, 'stage', target_id=8, value=False)
    assert 8 not in state.stage_ids
    assert state.media_room_id != room and state.media_epoch == epoch + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(('action', 'code'), [
    ('DismissRoom', 'FailedOperation.RoomNotExist'),
    ('StopPublishCdnStream', 'ResourceNotFound'),
])
async def test_cleanup_already_completed_is_success(monkeypatch, action, code):
    from app.services import live_media
    monkeypatch.setattr(settings, 'live_cloud_secret_id', 'synthetic-id')
    monkeypatch.setattr(settings, 'live_cloud_secret_key', 'synthetic-key')

    def completed(self, request):
        raise TencentCloudSDKException(code, 'synthetic provider response')

    monkeypatch.setattr(live_media.trtc_client.TrtcClient, action, completed)
    assert await live_media.cloud_call(action, {'SdkAppId': 123}) == {}


@pytest.mark.asyncio
async def test_cloud_authorization_error_is_not_treated_as_cleanup_success(monkeypatch):
    from app.services import live_media
    monkeypatch.setattr(settings, 'live_cloud_secret_id', 'synthetic-id')
    monkeypatch.setattr(settings, 'live_cloud_secret_key', 'synthetic-key')

    def forbidden(self, request):
        raise TencentCloudSDKException('AuthFailure', 'synthetic-secret-must-not-leak')

    monkeypatch.setattr(live_media.trtc_client.TrtcClient, 'DismissRoom', forbidden)
    with pytest.raises(HTTPException) as error:
        await live_media.cloud_call('DismissRoom', {'SdkAppId': 123})
    assert error.value.status_code == 503
    assert 'synthetic-secret' not in error.value.detail
