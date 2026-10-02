"""Keep upstream live contracts separate from the invited four-round live v2.

These tests use in-memory ASGI requests and service-boundary stubs only.  They
must not start the application lifespan, connect to MySQL/Redis, or call Tencent.
"""

from __future__ import annotations

import ast
from collections import Counter
from importlib import import_module
from pathlib import Path
import re
from types import ModuleType

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.api.dependencies import CurrentUser, get_current_user
from app.core.config import Settings
from app.db.session import get_db


ROOT = Path(__file__).resolve().parents[1]
V1_LIST = "/api/v1/live/sessions"
V2_LIST = "/api/v1/live/v2/sessions"


def _v2_module(name: str) -> ModuleType:
    module_path = ROOT.joinpath(*name.split(".")).with_suffix(".py")
    assert module_path.is_file(), f"Missing isolated live v2 module: {name}"
    return import_module(name)


def _isolated_app(router_module: ModuleType) -> FastAPI:
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1")

    async def no_database():
        # A real service query against this sentinel fails rather than touching
        # whichever connection happens to be configured on a developer machine.
        yield object()

    app.dependency_overrides[get_db] = no_database
    return app


def _http_routes(routes, prefix: str = ""):
    """Follow the same eager/lazy router shapes as existing route contracts."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield f"{prefix}{route.path}", route
        elif hasattr(route, "original_router"):
            context = route.include_context
            yield from _http_routes(
                route.original_router.routes, f"{prefix}{context.prefix}"
            )
        elif hasattr(route, "routes"):
            yield from _http_routes(route.routes, prefix)


def test_application_registers_both_live_contracts_once() -> None:
    from app.main import app
    from app.schemas.live import LiveSessionPage

    v2_schemas = _v2_module("app.schemas.live_v2")
    routes = [
        (path, route)
        for path, route in _http_routes(app.routes)
        if path.startswith("/api/v1/live/")
    ]
    counts = Counter(
        (re.sub(r"\{[^}]+\}", "{}", path), method)
        for path, route in routes
        for method in route.methods
    )
    duplicates = {key: count for key, count in counts.items() if count != 1}
    assert not duplicates, f"Shadowed live endpoints: {duplicates}"
    assert counts[(V1_LIST, "GET")] == 1
    assert counts[(V2_LIST, "GET")] == 1

    list_models = {
        path: route.response_model
        for path, route in routes
        if path in {V1_LIST, V2_LIST} and "GET" in route.methods
    }
    assert list_models[V1_LIST] is LiveSessionPage
    assert list_models[V2_LIST] is v2_schemas.LiveList


def test_upstream_list_remains_public_and_preserves_its_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import live as old_routes
    from app.services import live as old_service

    async def public_sessions(db, status):
        return {"items": [], "total": 0}

    monkeypatch.setattr(old_service, "list_sessions", public_sessions)
    app = _isolated_app(old_routes)
    response = TestClient(app).get(V1_LIST, params={"status": "SCHEDULED"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_invited_v2_list_requires_login_before_listing_any_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v2_routes = _v2_module("app.api.routes.live_v2")
    v2_service = _v2_module("app.services.live_v2")

    async def must_not_list_anonymous_sessions(*args, **kwargs):
        raise AssertionError("Unauthenticated live v2 request reached its service")

    monkeypatch.setattr(v2_service, "list_sessions", must_not_list_anonymous_sessions)
    app = _isolated_app(v2_routes)
    response = TestClient(app).get(V2_LIST)

    assert response.status_code == 401
    assert "items" not in response.json()


def test_invited_v2_list_uses_authenticated_identity_and_its_own_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import live as old_service

    v2_routes = _v2_module("app.api.routes.live_v2")
    v2_service = _v2_module("app.services.live_v2")
    current = CurrentUser(
        id=77, session_id=3, phone=None, status=1, realname_status=2
    )

    async def invited_sessions(db, user_id):
        return {
            "items": [
                {
                    "id": 17,
                    "title": f"Invitation for account {user_id}",
                    "scheduled_at": 1_800_000_000,
                    "status": "scheduled",
                    "role": "spectator",
                    "media_mode": "disabled",
                }
            ],
            "can_manage": False,
        }

    async def must_not_use_upstream_service(*args, **kwargs):
        raise AssertionError("Live v2 dispatched into the upstream live service")

    monkeypatch.setattr(v2_service, "list_sessions", invited_sessions)
    monkeypatch.setattr(old_service, "list_sessions", must_not_use_upstream_service)
    app = _isolated_app(v2_routes)
    app.dependency_overrides[get_current_user] = lambda: current
    # The client-supplied identity/role must not replace the authenticated user.
    response = TestClient(app).get(V2_LIST, params={"user_id": 999, "role": "admin"})

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [
            {
                "id": 17,
                "title": "Invitation for account 77",
                "scheduled_at": 1_800_000_000,
                "status": "scheduled",
                "role": "spectator",
                "media_mode": "disabled",
            }
        ],
        "can_manage": False,
    }


def test_live_list_schemas_do_not_silently_accept_the_other_contract() -> None:
    from app.schemas.live import LiveSessionPage

    v2_schemas = _v2_module("app.schemas.live_v2")
    with pytest.raises(ValidationError):
        LiveSessionPage.model_validate({"items": [], "can_manage": False})
    with pytest.raises(ValidationError):
        v2_schemas.LiveList.model_validate({"items": [], "total": 0})


def test_v2_migrations_only_create_isolated_live_tables() -> None:
    required = {
        "live_v2_session",
        "live_v2_member",
        "live_v2_action",
        "live_v2_opportunity",
        "live_v2_report",
        "live_v2_media_cleanup",
    }
    created = set()
    v2_migrations = []
    for migration in (ROOT / "migrations").rglob("*.sql"):
        sql = re.sub(r"--[^\n]*", "", migration.read_text(encoding="utf-8"))
        tables = set(
            re.findall(
                r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(live_\w+)",
                sql,
                flags=re.IGNORECASE,
            )
        )
        if not any(table.startswith("live_v2_") for table in tables):
            continue
        v2_migrations.append(migration.relative_to(ROOT).as_posix())
        created.update(tables)
        # Includes foreign references and DML as well as CREATE/ALTER targets.
        old_names = {
            name
            for name in re.findall(r"\b(live_\w+)\b", sql)
            if not name.startswith("live_v2_")
        }
        assert not old_names, f"{migration.name} touches upstream tables: {old_names}"

    assert v2_migrations, "Missing additive live v2 migration"
    assert required.issubset(created), f"Missing live v2 tables: {required - created}"


def test_v2_sql_does_not_query_or_modify_upstream_live_tables() -> None:
    paths = [
        ROOT / "app/api/routes/live_v2.py",
        ROOT / "app/services/live_v2.py",
        ROOT / "app/services/live_media.py",
    ]
    for path in paths:
        assert path.is_file(), f"Missing live v2 module: {path.relative_to(ROOT)}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            tables = re.findall(
                r"\b(?:FROM|JOIN|UPDATE|INTO)\s+`?(live_\w+)",
                node.value,
                flags=re.IGNORECASE,
            )
            old_tables = {name for name in tables if not name.startswith("live_v2_")}
            assert not old_tables, (
                f"{path.relative_to(ROOT)}:{node.lineno} uses upstream tables: {old_tables}"
            )


def test_v2_media_configuration_keeps_upstream_provider_and_keys_independent() -> None:
    configured = Settings(
        _env_file=None,
        environment="testing",
        debug=True,
        live_enabled=True,
        live_provider="tencent",
        tencent_live_sdk_app_id=10001,
        tencent_live_sdk_secret_key="unit-test-upstream-sdk-key",
        tencent_live_secret_id="unit-test-upstream-cam-id",
        tencent_live_secret_key="unit-test-upstream-cam-key",
        tencent_live_callback_secret="unit-test-upstream-callback-key",
        tencent_live_callback_event_types_raw="ROOM_CLOSE",
        live_media_mode="disabled",
        live_trial_enabled=False,
        live_sdk_app_id=20002,
        live_sdk_secret="unit-test-v2-sdk-key",
    )

    assert configured.live_enabled is True
    assert configured.live_provider == "tencent"
    assert configured.tencent_live_sdk_app_id == 10001
    assert configured.tencent_live_sdk_secret_key.get_secret_value() == (
        "unit-test-upstream-sdk-key"
    )
    assert configured.live_media_mode == "disabled"
    assert configured.live_trial_enabled is False
    assert configured.live_sdk_app_id == 20002
    assert configured.live_sdk_secret == "unit-test-v2-sdk-key"


def test_v2_media_mode_defaults_to_trtc_without_changing_upstream_defaults() -> None:
    fields = Settings.model_fields
    assert "live_media_mode" in fields, "Missing explicit live v2 media mode"
    assert fields["live_media_mode"].default == "trtc"
    assert fields["live_enabled"].default is False
    assert fields["live_provider"].default == "mock"
