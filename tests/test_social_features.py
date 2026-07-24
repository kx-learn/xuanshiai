import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.social import ChatMessageCreate


client = TestClient(app)


def test_chat_message_validates_message_content() -> None:
    with pytest.raises(ValidationError):
        ChatMessageCreate()
    assert ChatMessageCreate(content="你好").content == "你好"
    assert ChatMessageCreate(type=2, media_url="/storage/chat/a.jpg").type == 2


def test_social_routes_are_registered_and_require_authentication() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/users/{target_id}/like" in paths
    assert "/api/v1/relations/matches" in paths
    assert "/api/v1/chat/sessions/{session_id}/messages" in paths
    assert "/api/v1/chat/sessions" in paths
    assert "/api/v1/notifications" in paths
    assert "/api/v1/security/reports/{target_id}" in paths
    assert "/api/v1/admin/media/{media_id}/review" in paths
    assert "/api/v1/admin/reports/{report_id}/review" in paths
    assert "/api/v1/admin/users/{user_id}/certifications/{kind}/review" in paths

    response = client.get("/api/v1/relations/matches")
    assert response.status_code == 401


def test_social_actions_require_authentication() -> None:
    response = client.put("/api/v1/users/1/like")
    assert response.status_code == 401
