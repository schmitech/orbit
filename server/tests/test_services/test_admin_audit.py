"""
Unit tests for admin/auth audit storage and the AdminAuditMiddleware.

Covers:
- AdminAuditRecord round-trips through the SQLite admin strategy.
- AuditService.log_admin_event / query_admin_events plumbing and
  failure-swallowing behavior.
- AdminAuditMiddleware integration: actor resolution, secret scrubbing,
  route-map matching, and GET skip.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pytest_asyncio import fixture

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from services.audit import (
    AdminAuditRecord,
    AuditService,
    SQLiteAdminAuditStrategy,
)
from services.sqlite_service import SQLiteService
from middleware.admin_audit_middleware import (
    AdminAuditMiddleware,
    _match_route,
    _build_request_summary,
    _CHANGED_KEYS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@fixture(scope="function")
async def sqlite_admin_config(tmp_path):
    db_path = os.path.join(tmp_path, "test_admin_audit.db")
    return {
        "general": {"inference_provider": "test_provider"},
        "internal_services": {
            "backend": {
                "type": "sqlite",
                "sqlite": {"database_path": db_path},
            },
            "audit": {
                "enabled": True,
                "storage_backend": "sqlite",
                "collection_name": "audit_logs",
                "admin_events": {
                    "enabled": True,
                    "collection_name": "audit_admin_logs",
                },
            },
        },
    }


@fixture(scope="function")
async def audit_service_with_admin(sqlite_admin_config):
    sqlite_service = SQLiteService(sqlite_admin_config)
    await sqlite_service.initialize()

    audit_service = AuditService(sqlite_admin_config, sqlite_service)
    await audit_service.initialize()

    yield audit_service, sqlite_service, sqlite_admin_config

    await audit_service.close()
    sqlite_service.close()
    SQLiteService.clear_cache()


@pytest.fixture
def sample_admin_record():
    return AdminAuditRecord(
        timestamp=datetime.now(),
        event_type="admin.api_key.create",
        action="CREATE",
        resource_type="api_key",
        resource_id="abc123",
        actor_type="user",
        actor_id="user-42",
        actor_username="admin",
        method="POST",
        path="/admin/api-keys",
        status_code=201,
        success=True,
        ip="127.0.0.1",
        ip_metadata={
            "type": "local",
            "isLocal": True,
            "source": "direct",
            "originalValue": "127.0.0.1",
        },
        user_agent="pytest/1.0",
        error_message=None,
        request_summary={"client_name": "acme"},
    )


# ---------------------------------------------------------------------------
# AdminAuditRecord
# ---------------------------------------------------------------------------

class TestAdminAuditRecord:
    def test_to_dict_includes_core_fields(self, sample_admin_record):
        d = sample_admin_record.to_dict()
        assert d["event_type"] == "admin.api_key.create"
        assert d["action"] == "CREATE"
        assert d["success"] is True
        assert d["actor_id"] == "user-42"
        assert d["request_summary"] == {"client_name": "acme"}

    def test_to_flat_dict_converts_booleans(self, sample_admin_record):
        d = sample_admin_record.to_flat_dict()
        assert d["success"] == 1
        assert d["ip_is_local"] == 1
        # request_summary is JSON-encoded for SQLite storage
        assert isinstance(d["request_summary"], str)
        assert "acme" in d["request_summary"]


# ---------------------------------------------------------------------------
# SQLite strategy round-trip
# ---------------------------------------------------------------------------

class TestSQLiteAdminAuditStrategy:
    async def test_store_and_query(self, audit_service_with_admin, sample_admin_record):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        strategy = audit_service._admin_strategy

        ok = await strategy.store(sample_admin_record)
        assert ok is True

        results = await strategy.query({"actor_id": "user-42"})
        assert len(results) == 1
        assert results[0]["event_type"] == "admin.api_key.create"
        assert results[0]["success"] is True
        assert results[0]["ip_metadata"]["type"] == "local"
        assert results[0]["request_summary"] == {"client_name": "acme"}

    async def test_filter_by_success_boolean(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        strategy = audit_service._admin_strategy

        failed = AdminAuditRecord(
            timestamp=datetime.now(),
            event_type="auth.login",
            action="LOGIN",
            resource_type="session",
            method="POST",
            path="/auth/login",
            status_code=401,
            success=False,
            ip="127.0.0.1",
            actor_type="anonymous",
            request_summary={"username": "bad-user"},
        )
        ok = AdminAuditRecord(
            timestamp=datetime.now(),
            event_type="auth.login",
            action="LOGIN",
            resource_type="session",
            method="POST",
            path="/auth/login",
            status_code=200,
            success=True,
            ip="127.0.0.1",
            actor_type="user",
            actor_id="u1",
            actor_username="alice",
        )
        await strategy.store(failed)
        await strategy.store(ok)

        failures = await strategy.query({"success": False})
        successes = await strategy.query({"success": True})
        assert len(failures) == 1
        assert failures[0]["actor_type"] == "anonymous"
        assert len(successes) == 1
        assert successes[0]["actor_username"] == "alice"


# ---------------------------------------------------------------------------
# AuditService admin plumbing
# ---------------------------------------------------------------------------

class TestAuditServiceAdminAPI:
    async def test_admin_events_enabled_flag(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        assert audit_service.admin_events_enabled is True

    async def test_admin_disabled_when_flag_off(self, sqlite_admin_config):
        sqlite_admin_config["internal_services"]["audit"]["admin_events"]["enabled"] = False
        sqlite_service = SQLiteService(sqlite_admin_config)
        await sqlite_service.initialize()
        service = AuditService(sqlite_admin_config, sqlite_service)
        await service.initialize()
        try:
            assert service.admin_events_enabled is False
            assert service._admin_strategy is None
        finally:
            await service.close()
            sqlite_service.close()
            SQLiteService.clear_cache()

    async def test_log_admin_event_swallows_errors(self, audit_service_with_admin, sample_admin_record):
        audit_service, _sqlite, _cfg = audit_service_with_admin

        failing_strategy = AsyncMock()
        failing_strategy.is_initialized = MagicMock(return_value=True)
        failing_strategy.store = AsyncMock(side_effect=RuntimeError("disk on fire"))
        audit_service._admin_strategy = failing_strategy

        # Must not raise.
        await audit_service.log_admin_event(sample_admin_record)
        failing_strategy.store.assert_awaited_once()


# ---------------------------------------------------------------------------
# Route map & summary builder
# ---------------------------------------------------------------------------

class TestRouteMap:
    def test_match_concrete_admin_path(self):
        result = _match_route("DELETE", "/admin/api-keys/abc123")
        assert result is not None
        entry, params = result
        assert entry[2] == "admin.api_key.delete"
        assert params == {"api_key_id": "abc123"}

    def test_match_login(self):
        result = _match_route("POST", "/auth/login")
        assert result is not None
        entry, params = result
        assert entry[2] == "auth.login"
        assert params == {}

    def test_no_match_on_get(self):
        assert _match_route("GET", "/admin/api-keys") is None

    def test_no_match_on_unknown_path(self):
        assert _match_route("POST", "/admin/does-not-exist") is None

    def test_dashboard_login_is_mapped(self):
        result = _match_route("POST", "/admin/login")
        assert result is not None
        entry, _ = result
        assert entry[2] == "auth.dashboard.login"
        assert entry[3] == "LOGIN"

    def test_dashboard_logout_is_mapped(self):
        result = _match_route("POST", "/admin/logout")
        assert result is not None
        entry, _ = result
        assert entry[2] == "auth.dashboard.logout"


class TestRequestSummaryBuilder:
    def test_password_never_leaks_on_login(self):
        body = {"username": "alice", "password": "hunter2"}
        # /auth/login allowlist: ("username",)
        summary = _build_request_summary(body, ("username",))
        assert summary == {"username": "alice"}
        assert "password" not in summary

    def test_no_allowlist_means_no_summary(self):
        body = {"anything": 1}
        assert _build_request_summary(body, ()) is None

    def test_changed_keys_sentinel_records_key_list_only(self):
        body = {"timeout_seconds": 99, "secret": "do not leak"}
        summary = _build_request_summary(body, _CHANGED_KEYS)
        assert summary == {"changed_keys": ["timeout_seconds", "secret"]}
        assert "secret" not in summary.values()  # value not stored
        assert 99 not in summary.values()


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------

def _build_test_app(audit_service) -> FastAPI:
    """Small FastAPI app that mimics the pieces the middleware depends on."""
    app = FastAPI()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware)

    @app.post("/auth/login")
    async def login(request: Request):
        body = await request.json()
        if body.get("username") == "alice":
            request.state.current_user = {"id": "u1", "username": "alice", "role": "admin"}
            return {"token": "t"}
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="bad creds")

    @app.post("/admin/api-keys")
    async def create_key(request: Request):
        request.state.current_user = {"id": "u1", "username": "alice", "role": "admin"}
        return {"id": "key-1"}

    @app.get("/admin/api-keys")
    async def list_keys(request: Request):
        request.state.current_user = {"id": "u1", "username": "alice", "role": "admin"}
        return []

    @app.post("/admin/render-markdown")
    async def render_markdown(request: Request):
        request.state.current_user = {"id": "u1", "username": "alice", "role": "admin"}
        return {"html": "<p>hi</p>"}

    return app


class TestAdminAuditMiddleware:
    async def test_login_success_is_audited_without_password(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        app = _build_test_app(audit_service)

        with TestClient(app) as client:
            resp = client.post("/auth/login", json={"username": "alice", "password": "hunter2"})
        assert resp.status_code == 200

        events = await audit_service.query_admin_events({"event_type": "auth.login"})
        assert len(events) == 1
        evt = events[0]
        assert evt["success"] is True
        assert evt["actor_username"] == "alice"
        summary = evt.get("request_summary") or {}
        assert summary.get("username") == "alice"
        assert "password" not in summary

    async def test_login_failure_records_anonymous_attempt(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        app = _build_test_app(audit_service)

        with TestClient(app) as client:
            resp = client.post("/auth/login", json={"username": "mallory", "password": "x"})
        assert resp.status_code == 401

        events = await audit_service.query_admin_events({"event_type": "auth.login"})
        assert len(events) == 1
        evt = events[0]
        assert evt["success"] is False
        assert evt["actor_type"] == "anonymous"
        assert (evt.get("request_summary") or {}).get("username") == "mallory"

    async def test_get_requests_are_not_audited(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        app = _build_test_app(audit_service)

        with TestClient(app) as client:
            resp = client.get("/admin/api-keys")
        assert resp.status_code == 200

        events = await audit_service.query_admin_events({})
        assert events == []

    async def test_skip_list_prevents_render_markdown_audit(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        app = _build_test_app(audit_service)

        with TestClient(app) as client:
            resp = client.post("/admin/render-markdown", json={"markdown": "# hi"})
        assert resp.status_code == 200

        events = await audit_service.query_admin_events({})
        assert events == []

    async def test_admin_mutation_records_user_actor(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        app = _build_test_app(audit_service)

        with TestClient(app) as client:
            resp = client.post(
                "/admin/api-keys",
                json={"client_name": "acme", "adapter_name": "intent-sql", "secret": "no"},
            )
        assert resp.status_code == 200

        events = await audit_service.query_admin_events({"event_type": "admin.api_key.create"})
        assert len(events) == 1
        evt = events[0]
        assert evt["actor_type"] == "user"
        assert evt["actor_username"] == "alice"
        summary = evt.get("request_summary") or {}
        assert summary.get("client_name") == "acme"
        assert "secret" not in summary  # not on allowlist


# ---------------------------------------------------------------------------
# GET /admin/audit/events endpoint
# ---------------------------------------------------------------------------

def _build_endpoint_app(audit_service):
    """FastAPI app mounting the real admin_router with auth bypassed."""
    from routes.admin_routes import admin_router, admin_auth_check
    app = FastAPI()
    app.state.audit_service = audit_service
    app.include_router(admin_router)
    app.dependency_overrides[admin_auth_check] = lambda: True
    return app


async def _seed_events(audit_service, count_ok=3, count_fail=2, event_type="admin.api_key.create"):
    for i in range(count_ok):
        await audit_service.log_admin_event(AdminAuditRecord(
            timestamp=datetime.now(),
            event_type=event_type,
            action="CREATE",
            resource_type="api_key",
            resource_id=f"key-{i}",
            actor_type="user", actor_id="u1", actor_username="alice",
            method="POST", path="/admin/api-keys",
            status_code=201, success=True,
            ip="127.0.0.1",
            ip_metadata={"type": "local", "isLocal": True, "source": "direct", "originalValue": "127.0.0.1"},
        ))
    for i in range(count_fail):
        await audit_service.log_admin_event(AdminAuditRecord(
            timestamp=datetime.now(),
            event_type="auth.login",
            action="LOGIN",
            resource_type="session",
            actor_type="anonymous",
            method="POST", path="/auth/login",
            status_code=401, success=False,
            ip="10.0.0.1",
            ip_metadata={"type": "ipv4", "isLocal": True, "source": "direct", "originalValue": "10.0.0.1"},
            request_summary={"username": f"attacker-{i}"},
        ))


class TestAuditEventsEndpoint:
    async def test_returns_503_when_admin_audit_disabled(self, sqlite_admin_config):
        # disable admin events
        sqlite_admin_config["internal_services"]["audit"]["admin_events"]["enabled"] = False
        sqlite_service = SQLiteService(sqlite_admin_config)
        await sqlite_service.initialize()
        audit_service = AuditService(sqlite_admin_config, sqlite_service)
        await audit_service.initialize()
        try:
            app = _build_endpoint_app(audit_service)
            with TestClient(app) as client:
                resp = client.get("/admin/audit/events")
            assert resp.status_code == 503
            assert "not enabled" in resp.json()["detail"].lower()
        finally:
            await audit_service.close()
            sqlite_service.close()
            SQLiteService.clear_cache()

    async def test_returns_empty_list_when_no_events(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        app = _build_endpoint_app(audit_service)
        with TestClient(app) as client:
            resp = client.get("/admin/audit/events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert body["returned"] == 0

    async def test_returns_seeded_events_newest_first(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        await _seed_events(audit_service)
        app = _build_endpoint_app(audit_service)
        with TestClient(app) as client:
            resp = client.get("/admin/audit/events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["returned"] == 5
        # Newest first means timestamps are non-increasing
        timestamps = [e["timestamp"] for e in body["events"]]
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_filter_by_success_false(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        await _seed_events(audit_service)
        app = _build_endpoint_app(audit_service)
        with TestClient(app) as client:
            resp = client.get("/admin/audit/events?success=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["returned"] == 2
        assert all(not e["success"] for e in body["events"])

    async def test_filter_by_event_prefix(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        await _seed_events(audit_service)
        app = _build_endpoint_app(audit_service)
        with TestClient(app) as client:
            resp = client.get("/admin/audit/events?event_prefix=auth.")
        assert resp.status_code == 200
        body = resp.json()
        assert body["returned"] == 2
        assert all(e["event_type"].startswith("auth.") for e in body["events"])

    async def test_free_text_search(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        await _seed_events(audit_service)
        app = _build_endpoint_app(audit_service)
        with TestClient(app) as client:
            resp = client.get("/admin/audit/events?q=alice")
        assert resp.status_code == 200
        body = resp.json()
        assert body["returned"] == 3  # the three seeded admin.api_key.create rows by alice
        for e in body["events"]:
            assert e["actor_username"] == "alice"

    async def test_pagination(self, audit_service_with_admin):
        audit_service, _sqlite, _cfg = audit_service_with_admin
        await _seed_events(audit_service, count_ok=10, count_fail=0)
        app = _build_endpoint_app(audit_service)
        with TestClient(app) as client:
            page1 = client.get("/admin/audit/events?limit=3&offset=0").json()
            page2 = client.get("/admin/audit/events?limit=3&offset=3").json()
        assert page1["returned"] == 3
        assert page2["returned"] == 3
        # Seeded rows have unique resource_ids (key-0 … key-9) — pages must not overlap.
        rids1 = [e["resource_id"] for e in page1["events"]]
        rids2 = [e["resource_id"] for e in page2["events"]]
        assert set(rids1).isdisjoint(set(rids2))
