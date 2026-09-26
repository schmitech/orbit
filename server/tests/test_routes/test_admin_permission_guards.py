"""Guard tests: each seed role is allowed/denied on representative admin routes.

Verifies the guards in routes/admin/_shared.py (apikeys_auth, adapters_auth,
prompts_auth, config_auth, system_auth, logs_auth, audit_auth, conversations_auth)
actually enforces per-permission access instead of the old binary admin check -
in particular that "operator" (ops/config permissions, no conversation access)
is denied chat-history, "analyst" (conversation access only) is denied config,
and "operator" (runs day-to-day operations, including logs.read) is denied
audit-trail visibility, which is scoped to "auditor" instead.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import admin as admin_routes
from routes import auth_dependencies
from auth.rbac import permissions_for_roles


class FakeChatHistoryService:
    async def get_conversation_history(self, session_id, limit=50, include_metadata=True):
        return []


class FakeApiKeyDatabase:
    async def find_one(self, collection_name, query):
        return {
            "_id": query["_id"],
            "api_key": "orbit_super-secret-value-1234",
            "client_name": "regression-test",
            "active": True,
        }


class FakeApiKeyDetailService:
    _initialized = True
    collection_name = "api_keys"

    def __init__(self):
        self.database = FakeApiKeyDatabase()
        self.config = {"api_keys": {}}

    def _serialize_expiration(self, key_doc):
        return {"expires_at": None}


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
        assert resp.status_code == 403


def test_analyst_cannot_reach_apikeys_routes():
    app = _build_app(["analyst"])
    with TestClient(app) as client:
        resp = client.get("/admin/api-keys")
    assert resp.status_code == 403


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
        (["operator"], True),  # troubleshoots the system it runs; has logs.read
    ],
)
def test_logs_tail_requires_logs_read(roles, passes_auth):
    app = _build_app(roles)
    with TestClient(app) as client:
        resp = client.get("/admin/logs/tail")
    if passes_auth:
        assert resp.status_code not in (401, 403)
    else:
        assert resp.status_code == 403


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
        assert resp.status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/admin/api-keys",
        "/admin/adapters/config",
        "/admin/prompts",
        "/admin/config",
        "/admin/info",
        "/admin/logs/files",
        "/admin/audit/events",
        "/admin/chat-history/session-1",
    ],
)
def test_valid_inference_api_key_cannot_reach_management_routes(path):
    """Inference API keys never grant access to the administrative control plane."""
    app = _build_app(["user"])

    async def no_user():
        return None

    class FakeApiKeyService:
        calls = 0

        async def validate_api_key(self, key, adapter_manager, current_user_id=None, current_user_email=None):
            self.calls += 1
            return (key == "valid-key", "some-adapter", None)

    app.dependency_overrides[auth_dependencies.get_current_user] = no_user
    api_key_service = FakeApiKeyService()
    app.state.api_key_service = api_key_service

    with TestClient(app) as client:
        response = client.get(path, headers={"X-API-Key": "valid-key"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert api_key_service.calls == 0


def test_api_key_detail_never_returns_stored_key_plaintext():
    """Even authorized managers only receive a masked stored credential."""
    app = _build_app(["admin"])
    app.state.api_key_service = FakeApiKeyDetailService()

    with TestClient(app) as client:
        response = client.get("/admin/api-keys/key-record-id/detail")

    assert response.status_code == 200
    assert response.json()["api_key"] == "***1234"
    assert "super-secret" not in response.text


def test_valid_api_key_cannot_elevate_authenticated_user_without_permission():
    app = _build_app(["user"])

    class FakeApiKeyService:
        calls = 0

        async def validate_api_key(self, key, adapter_manager, current_user_id=None, current_user_email=None):
            self.calls += 1
            return (True, "some-adapter", None)

    api_key_service = FakeApiKeyService()
    app.state.api_key_service = api_key_service

    with TestClient(app) as client:
        response = client.get("/admin/config", headers={"X-API-Key": "valid-key"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing required permission(s): config.manage"
    assert api_key_service.calls == 0
