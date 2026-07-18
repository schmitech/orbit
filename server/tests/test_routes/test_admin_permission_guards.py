"""Guard tests: each seed role is allowed/denied on representative admin routes.

Verifies the split introduced in admin_routes.py (apikeys_auth, adapters_auth,
prompts_auth, config_auth, system_auth, logs_auth, audit_auth, conversations_auth)
actually enforces per-permission access instead of the old binary admin check -
in particular that "operator" (ops/config permissions, no conversation access)
is denied chat-history, "analyst" (conversation access only) is denied config,
and "operator" (runs day-to-day operations) is denied logs/audit visibility,
which is scoped to "auditor" instead.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import admin_routes
from routes import auth_dependencies
from auth.rbac import permissions_for_roles


class FakeChatHistoryService:
    async def get_conversation_history(self, session_id, limit=50, include_metadata=True):
        return []


def _user_info(roles):
    return {
        "id": "u1",
        "username": "u1",
        "email": None,
        "role": roles[0],
        "roles": roles,
        "permissions": sorted(permissions_for_roles(roles)),
        "active": True,
    }


def _build_app(roles):
    app = FastAPI()
    app.include_router(admin_routes.admin_router)
    app.state.chat_history_service = FakeChatHistoryService()
    app.state.config = {}

    async def fake_user():
        return _user_info(roles)

    async def fake_optional_user():
        return _user_info(roles)

    app.dependency_overrides[auth_dependencies.get_current_user] = fake_user
    app.dependency_overrides[auth_dependencies.get_optional_user] = fake_optional_user
    return app


@pytest.mark.parametrize(
    "roles,expected_status",
    [
        (["admin"], 200),
        (["analyst"], 200),
        (["operator"], 403),
        (["auditor"], 403),
        (["user"], 403),
    ],
)
def test_chat_history_requires_conversations_read(roles, expected_status):
    app = _build_app(roles)
    with TestClient(app) as client:
        resp = client.get("/admin/chat-history/session-1")
    assert resp.status_code == expected_status


def test_chat_history_denies_unauthenticated():
    app = _build_app(["user"])

    async def no_user():
        return None

    app.dependency_overrides[auth_dependencies.get_current_user] = no_user
    with TestClient(app) as client:
        resp = client.get("/admin/chat-history/session-1")
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "roles,passes_auth",
    [
        (["admin"], True),
        (["operator"], True),
        (["analyst"], False),  # no bearer/api-key admin permission for config.manage
    ],
)
def test_config_sections_requires_config_manage(roles, passes_auth):
    app = _build_app(roles)
    with TestClient(app) as client:
        resp = client.get("/admin/config/sections")
    if passes_auth:
        assert resp.status_code not in (401, 403)
    else:
        assert resp.status_code == 401


def test_analyst_cannot_reach_apikeys_routes():
    app = _build_app(["analyst"])
    with TestClient(app) as client:
        resp = client.get("/admin/api-keys")
    assert resp.status_code == 401


def test_operator_can_reach_apikeys_routes():
    app = _build_app(["operator"])
    with TestClient(app) as client:
        resp = client.get("/admin/api-keys")
    assert resp.status_code != 401 and resp.status_code != 403


@pytest.mark.parametrize(
    "roles,passes_auth",
    [
        (["admin"], True),
        (["auditor"], True),
        (["operator"], False),  # runs operations, but has no logs.read
    ],
)
def test_logs_tail_requires_logs_read(roles, passes_auth):
    app = _build_app(roles)
    with TestClient(app) as client:
        resp = client.get("/admin/logs/tail")
    if passes_auth:
        assert resp.status_code not in (401, 403)
    else:
        assert resp.status_code == 401


@pytest.mark.parametrize(
    "roles,passes_auth",
    [
        (["admin"], True),
        (["auditor"], True),
        (["operator"], False),  # runs operations, but has no audit.read
    ],
)
def test_audit_events_requires_audit_read(roles, passes_auth):
    app = _build_app(roles)
    with TestClient(app) as client:
        resp = client.get("/admin/audit/events")
    if passes_auth:
        assert resp.status_code not in (401, 403)
    else:
        assert resp.status_code == 401


def test_api_key_bypasses_permission_or_api_key_routes_but_not_conversations():
    """A valid X-API-Key should reach permission_or_api_key-guarded routes but
    never reach the bearer-only conversations.read route."""
    app = _build_app(["user"])  # bearer user has no admin permissions at all

    async def no_user():
        return None

    class FakeApiKeyService:
        async def validate_api_key(self, key, adapter_manager):
            return (key == "valid-key", "some-adapter", None)

    app.dependency_overrides[auth_dependencies.get_optional_user] = no_user
    app.dependency_overrides[auth_dependencies.get_current_user] = no_user
    app.state.api_key_service = FakeApiKeyService()

    with TestClient(app) as client:
        resp_config = client.get("/admin/config/sections", headers={"X-API-Key": "valid-key"})
        resp_conversations = client.get("/admin/chat-history/session-1", headers={"X-API-Key": "valid-key"})

    assert resp_config.status_code != 401 and resp_config.status_code != 403
    assert resp_conversations.status_code == 401
