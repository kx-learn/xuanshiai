"""Regression boundaries when the local parent/message modules join upstream.

No configured database, Redis, cloud API, or application lifespan is used.
Media writes are limited to pytest's per-test temporary directory.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import wave

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_message_application_reply_requires_realname_like_discovery(
    action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routes import message as routes

    async def no_database():
        yield object()

    async def reply_without_database(db, user_id, application_id, action, command_id):
        return {
            "application": {
                "id": application_id,
                "userId": 22,
                "avatar": None,
                "name": "Synthetic applicant",
                "message": "Synthetic invitation",
                "time": 0,
                "status": "accepted" if action == "accept" else "rejected",
                "statusText": "已同意" if action == "accept" else "已拒绝",
                "direction": "in",
            },
            "canChat": action == "accept",
        }

    # Stub only the mutation boundary. The real phone/realname dependencies run.
    monkeypatch.setattr(routes, "handle_application", reply_without_database)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = no_database
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=11, session_id=1, phone="13800000000", status=1, realname_status=0
    )

    response = TestClient(app).post(
        "/api/v1/message/application/handle",
        json={
            "applicationId": 5,
            "action": action,
            "clientCommandId": f"unverified-{action}",
        },
    )

    assert response.status_code == 403
    assert "实名" in response.json()["detail"]


@pytest.mark.parametrize(
    ("stored_level", "label"),
    [(1, "高中及以下"), (2, "大专"), (3, "本科"), (4, "硕士"), (5, "博士")],
)
def test_parent_candidate_education_uses_upstream_storage_direction(
    stored_level: int, label: str
) -> None:
    from app.services.parent import _candidate

    card = SimpleNamespace(
        user_id=22,
        nickname="Synthetic candidate",
        city_code=None,
        height=None,
        education_level=stored_level,
        occupation=None,
        certification_tags=[],
    )
    result = _candidate(card, {"gender": 1, "birthday": date(1995, 1, 1)})

    assert result.education == label


class MediaRows:
    def __init__(
        self, rows: list[dict[str, Any]] | None = None, *, lastrowid: int | None = None
    ) -> None:
        self.rows = rows or []
        self.lastrowid = lastrowid

    def mappings(self) -> MediaRows:
        return self

    def one(self) -> dict[str, Any]:
        assert len(self.rows) == 1
        return self.rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class ChatMediaStore:
    """Small fake of the upload/read SQL boundary, including the real DB default."""

    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None
        self.review_tasks: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any]) -> MediaRows:
        sql = " ".join(str(statement).split())
        if "INSERT INTO community_media " in sql:
            self.row = {
                "id": 41,
                "user_id": params["user_id"],
                "purpose": params["purpose"],
                "media_type": "voice",
                "file_url": params["url"],
                "storage_key": params["storage_key"],
                "file_size": params["file_size"],
                "status": "ready",
                # Both upstream bootstrap and additive column default to pending.
                "moderation_status": params.get("moderation_status", "pending"),
                "deleted_at": None,
            }
            return MediaRows(lastrowid=41)
        if "INSERT INTO community_moderation_task" in sql:
            self.review_tasks.append(dict(params))
            return MediaRows(lastrowid=len(self.review_tasks))
        if "SELECT * FROM community_media WHERE id = :id" in sql:
            assert self.row is not None
            return MediaRows([dict(self.row)])
        if "FROM community_media WHERE id IN" in sql:
            assert self.row is not None
            row = self.row
            usable = (
                row["user_id"] == params["user_id"]
                and row["id"] == params["id0"]
                and row["purpose"] == params["purpose"]
                and row["media_type"] == params.get("media_type", row["media_type"])
                and row["status"] == "ready"
                and row["moderation_status"] == "approved"
                and row["deleted_at"] is None
            )
            return MediaRows([dict(row)] if usable else [])
        raise AssertionError(f"Unexpected SQL in isolated media test: {sql}")

    async def commit(self) -> None:
        pass


def _voice_upload() -> UploadFile:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 80)
    buffer.seek(0)
    return UploadFile(
        file=buffer, filename="synthetic.wav", headers={"content-type": "audio/wav"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "expected_status", "expected_tasks"),
    [("development", "approved", 0), ("testing", "approved", 0), ("staging", "pending", 1)],
)
async def test_chat_voice_upload_uses_the_shared_moderation_policy(
    environment: str,
    expected_status: str,
    expected_tasks: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import community_media

    monkeypatch.setattr(community_media.settings, "environment", environment)
    monkeypatch.setattr(community_media.settings, "upload_dir", str(tmp_path))
    store = ChatMediaStore()
    upload = _voice_upload()
    try:
        response = await community_media.upload_community_media(store, 7, upload, "chat")
    finally:
        await upload.close()

    assert response.media_type == "voice"
    assert response.moderation_status == expected_status
    assert len(store.review_tasks) == expected_tasks
    if expected_tasks:
        assert store.review_tasks[0]["target_id"] == response.id
        assert store.review_tasks[0]["user_id"] == 7
    else:
        ready = await community_media.resolve_owned_ready_media(
            store, 7, [response.id], purpose="chat", media_type="voice"
        )
        assert [row["id"] for row in ready] == [response.id]


@pytest.mark.asyncio
async def test_chat_voice_remains_unsendable_until_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import community_media

    monkeypatch.setattr(community_media.settings, "environment", "staging")
    monkeypatch.setattr(community_media.settings, "upload_dir", str(tmp_path))
    store = ChatMediaStore()
    upload = _voice_upload()
    try:
        response = await community_media.upload_community_media(store, 7, upload, "chat")
    finally:
        await upload.close()

    assert store.row is not None
    for moderation_status in ("pending", "rejected", "hidden"):
        store.row["moderation_status"] = moderation_status
        with pytest.raises(HTTPException) as error:
            await community_media.resolve_owned_ready_media(
                store, 7, [response.id], purpose="chat", media_type="voice"
            )
        assert error.value.status_code == 422

    store.row["moderation_status"] = "approved"
    ready = await community_media.resolve_owned_ready_media(
        store, 7, [response.id], purpose="chat", media_type="voice"
    )
    assert [row["id"] for row in ready] == [response.id]
