"""Tencent SDK boundary. No browser-created signatures or pretend media URLs."""
import asyncio
import hashlib
import json
import logging
import struct
import time

from fastapi import HTTPException
from sqlalchemy import text
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.trtc.v20190722 import models, trtc_client
from TLSSigAPIv2 import TLSSigAPIv2

from app.core.config import settings
from app.schemas.live_v2 import LiveCredentials, LiveResources, LiveState
from app.services.live_domain import member_for

logger = logging.getLogger(__name__)


def resources(*, rehearsal=False, media_mode=None) -> LiveResources:
    required = ['live_wechat_av_verified', 'live_private_map_key_enabled', 'live_sdk_app_id',
        'live_sdk_secret', 'live_cloud_secret_id', 'live_cloud_secret_key', 'live_cdn_push_domain',
        'live_cdn_play_domain', 'live_cdn_push_key', 'live_cdn_play_key', 'live_retention_notice']
    if not rehearsal:
        required += ['live_trial_enabled', 'live_device_pilot_verified']
    missing = [name.upper() for name in required if not getattr(settings, name)]
    mode = media_mode or settings.live_media_mode
    business_missing = ['LIVE_MEDIA_MODE_DISABLED_REQUIRES_TEST_ENVIRONMENT'] if mode == 'disabled' and not settings.is_test_mode else []
    active_missing = business_missing if mode == 'disabled' else missing
    return LiveResources(ready=not active_missing, missing=active_missing, media_mode=mode,
        business_ready=not business_missing, business_missing=business_missing,
        media_ready=mode == 'trtc' and not missing, media_missing=missing)


def signer():
    return TLSSigAPIv2(settings.live_sdk_app_id, settings.live_sdk_secret)


def private_ticket(user: str, room: int, publish: bool, ttl: int = 300) -> str:
    # Official numeric-room UserBuf wire format; the official Python signer
    # supports gen_sig_with_userbuf but does not expose the Node genPrivateMapKey helper.
    account = user.encode('ascii')
    permissions = 63 if publish else 42  # enter + receive audio/video, no publish bits for backstage
    buf = struct.pack('!BH', 0, len(account)) + account + struct.pack('!IIIII',
        settings.live_sdk_app_id, room, int(time.time()) + ttl, permissions, 0)
    return signer().gen_sig_with_userbuf(user, ttl, buf)


def signed_cdn_url(state: LiveState, *, push=False, ttl=60):
    stream = f'xsa_{state.id}_{state.media_room_id}'
    domain = settings.live_cdn_push_domain if push else settings.live_cdn_play_domain
    key = settings.live_cdn_push_key if push else settings.live_cdn_play_key
    deadline = format(int(time.time()) + ttl, 'X')
    # Tencent CSS's documented URL signing protocol mandates MD5 (not password storage).
    signature = hashlib.md5((key + stream + deadline).encode()).hexdigest()
    suffix = '' if push else '.flv'
    return f'{"rtmp" if push else "https"}://{domain}/live/{stream}{suffix}?txSecret={signature}&txTime={deadline}'


def credentials_for(state: LiveState, uid: int) -> LiveCredentials:
    if state.media_mode == 'disabled' or settings.live_media_mode == 'disabled':
        raise HTTPException(409, '当前环境未启用音视频')
    member = member_for(state, uid)
    now = int(time.time())
    if member.role in ('spectator', 'operator'):
        return LiveCredentials(mode='cdn', playback_url=signed_cdn_url(state), expires_at=now + 60, media_epoch=state.media_epoch)
    user = f'u{uid}'
    publish = uid in state.stage_ids
    return LiveCredentials(mode='rtc', sdk_app_id=settings.live_sdk_app_id, room_id=state.media_room_id,
        user_id=user, user_sig=signer().gen_sig(user, 300),
        private_map_key=private_ticket(user, state.media_room_id, publish), publish=publish,
        expires_at=now + 300, media_epoch=state.media_epoch)


async def cloud_call(action: str, params: dict) -> dict:
    def run():
        http = HttpProfile(endpoint='trtc.tencentcloudapi.com', reqTimeout=8)
        profile = ClientProfile(httpProfile=http)
        client = trtc_client.TrtcClient(credential.Credential(settings.live_cloud_secret_id,
            settings.live_cloud_secret_key), settings.live_cloud_region, profile)
        request = getattr(models, action + 'Request')()
        request.from_json_string(json.dumps(params))
        return json.loads(getattr(client, action)(request).to_json_string())
    try:
        return await asyncio.to_thread(run)
    except TencentCloudSDKException as exc:
        completed = {('DismissRoom', 'FailedOperation.RoomNotExist'),
                     ('StopPublishCdnStream', 'ResourceNotFound')}
        if (action, exc.get_code()) in completed:
            return {}
        # Never return provider payloads (may contain stream credentials) to clients/logs.
        logger.warning('TRTC action %s failed, code=%s', action, exc.get_code())
        raise HTTPException(503, '腾讯云音视频操作未成功，请由工作人员检查资源状态') from exc


def mix_parameters(state: LiveState):
    bot = f'mix_{state.id}_{state.media_epoch}'
    return {'SdkAppId': settings.live_sdk_app_id, 'RoomId': str(state.media_room_id), 'RoomIdType': 0,
        'AgentParams': {'UserId': bot, 'UserSig': signer().gen_sig(bot, 7200), 'MaxIdleTime': 120},
        'WithTranscoding': 1,
        'AudioParams': {'AudioEncode': {'Codec': 0, 'SampleRate': 48000, 'Channel': 2, 'BitRate': 64}},
        'VideoParams': {'VideoEncode': {'Width': 720, 'Height': 1280, 'Fps': 15, 'BitRate': 1400,
                                      'Gop': 3}, 'LayoutParams': {'MixLayoutMode': 3}},
        'PublishCdnParams': [{'PublishCdnUrl': signed_cdn_url(state, push=True, ttl=7200), 'IsTencentCdn': 1}]}


async def get_credentials(db, sid: int, uid: int):
    from app.services.live_v2 import load_session, save_session
    state = await load_session(db, sid, uid, lock=True)
    if state.media_mode == 'disabled' or settings.live_media_mode == 'disabled':
        raise HTTPException(409, '当前环境未启用音视频')
    gate = resources(rehearsal=state.status in ('draft', 'scheduled'), media_mode=state.media_mode)
    if not gate.ready:
        raise HTTPException(503, '尚未具备音视频条件：' + '、'.join(gate.missing))
    member = member_for(state, uid)
    if (not member.checked_in and member.role != 'operator') or member.attendance == 'left' or state.status in ('ended', 'cancelled') or not state.media_room_id:
        raise HTTPException(403, '请先签到，并等待主持开启设备演练或场次')
    if state.media_task_id is None:
        response = await cloud_call('StartPublishCdnStream', mix_parameters(state))
        state.media_task_id = response['TaskId']
        await save_session(db, state)
    await db.commit()
    return credentials_for(state, uid)


async def cleanup_once():
    from app.db.session import session_factory
    if session_factory is None or settings.live_media_mode == 'disabled':
        return
    async with session_factory() as db:
        job = (await db.execute(text('SELECT id,room_id,task_id FROM live_v2_media_cleanup WHERE done=FALSE ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED'))).mappings().first()
        if job is None:
            return
        if job['task_id']:
            await cloud_call('StopPublishCdnStream', {'SdkAppId': settings.live_sdk_app_id, 'TaskId': job['task_id']})
        await cloud_call('DismissRoom', {'SdkAppId': settings.live_sdk_app_id, 'RoomId': job['room_id']})
        await db.execute(text('UPDATE live_v2_media_cleanup SET done=TRUE WHERE id=:id'), {'id': job['id']})
        await db.commit()


async def cleanup_worker():
    while True:
        if settings.live_media_mode == 'trtc' and resources(rehearsal=True).ready:
            try:
                await cleanup_once()
            except Exception:
                logger.warning('Retired live media cleanup pending; will retry')
        await asyncio.sleep(3)
