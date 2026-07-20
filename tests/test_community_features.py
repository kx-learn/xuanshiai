import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.community import CommunityPostCreate, PaperPlaneCreate


client = TestClient(app)


def test_community_content_limits() -> None:
    with pytest.raises(ValidationError):
        CommunityPostCreate(content="x" * 2001)
    with pytest.raises(ValidationError):
        PaperPlaneCreate(content="")


def test_community_routes_are_registered_and_require_authentication() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/community/posts" in paths
    assert "/api/v1/community/posts/{post_id}/comments" in paths
    assert "/api/v1/paper-planes" in paths
    assert "/api/v1/paper-planes/{plane_id}/replies" in paths

    response = client.get("/api/v1/community/posts")
    assert response.status_code == 401
