"""Business-only mode is explicit, isolated and never manufactures media success."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services import live_media
from tests.test_live_domain import session


def test_media_mode_defaults_to_trtc_and_rejects_production_bypass():
    assert Settings(_env_file=None).live_media_mode == 'trtc'
    for environment in ('staging', 'production'):
        with pytest.raises(ValidationError, match='LIVE_MEDIA_MODE'):
            Settings(_env_file=None, environment=environment, auto_init_db=False,
                     live_media_mode='disabled')


def test_business_readiness_is_independent_of_cloud_keys(monkeypatch):
    monkeypatch.setattr(settings, 'live_media_mode', 'disabled')
    monkeypatch.setattr(settings, 'live_sdk_secret', '')
    status = live_media.resources()
    assert status.business_ready and not status.media_ready and status.ready
    assert status.media_mode == 'disabled'
    assert 'LIVE_SDK_SECRET' in status.media_missing


def test_disabled_session_cannot_receive_a_signature_or_fake_url():
    state = session()
    state.media_mode = 'disabled'
    with pytest.raises(HTTPException, match='当前环境未启用音视频') as error:
        live_media.credentials_for(state, 4)
    assert error.value.status_code == 409
