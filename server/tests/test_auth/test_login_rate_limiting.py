"""Integration tests for login-specific rate limiting."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from routes.auth_routes import auth_router  # noqa: E402
from middleware.admin_audit_middleware import AdminAuditMiddleware  # noqa: E402
from routes.admin_panel_routes import create_admin_panel_router  # noqa: E402


class FakeAuthService:
    async def authenticate_user(self, username, password, failure_context=None):
        if password == "correct-password":
            return True, "token", {"id": "2", "username": username, "role": "user"}
        if failure_context is not None:
            failure_context["reason"] = "invalid_credentials"
            failure_context["locked_out"] = password == "locked-password"
        return False, None, None


def build_app(*, username_limit=2, ip_limit=20, cache_service=None):
    config = {
        "auth": {
            "login_rate_limit": {
                "enabled": True,
                "window_seconds": 60,
                "max_attempts_per_ip": ip_limit,
                "max_attempts_per_username": username_limit,
                "lockout_after_username_limit": False,
            }
        }
    }
    app = FastAPI()
    app.state.config = config
    app.state.auth_service = FakeAuthService()
    if cache_service is not None:
        app.state.cache_service = cache_service
    app.include_router(auth_router)
    return app


def login(client, username, password="wrong-password"):
    return client.post(
        "/auth/login", json={"username": username, "password": password}
    )


def test_n_plus_one_failure_for_username_is_rate_limited():
    client = TestClient(build_app(username_limit=2))

    assert login(client, "victim").status_code == 401
    assert login(client, "VICTIM").status_code == 401
    response = login(client, "Victim")

    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert int(response.headers["Retry-After"]) > 0


def test_different_username_can_still_log_in():
    client = TestClient(build_app(username_limit=1))

    assert login(client, "victim").status_code == 401
    assert login(client, "victim").status_code == 429
    response = login(client, "other", "correct-password")

    assert response.status_code == 200
    assert response.json()["token"] == "token"


def test_correct_password_is_rejected_after_username_limit_is_exhausted():
    client = TestClient(build_app(username_limit=2))

    assert login(client, "victim").status_code == 401
    assert login(client, "VICTIM").status_code == 401
    response = login(client, "Victim", "correct-password")

    assert response.status_code == 429
    assert "token" not in response.json()


def test_ip_bucket_is_independent_of_username_bucket():
    client = TestClient(build_app(username_limit=20, ip_limit=2))

    assert login(client, "one").status_code == 401
    assert login(client, "two").status_code == 401
    response = login(client, "three")

    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "2"


def test_cache_failure_uses_in_memory_fallback():
    cache_service = Mock()
    cache_service.enabled = True
    cache_service.initialized = True
    cache_service.get = AsyncMock(side_effect=RuntimeError("cache unavailable"))
    cache_service.increment_with_ttl = AsyncMock(
        side_effect=RuntimeError("cache unavailable")
    )
    client = TestClient(
        build_app(username_limit=1, ip_limit=20, cache_service=cache_service)
    )

    assert login(client, "victim").status_code == 401
    assert login(client, "victim").status_code == 429
    assert cache_service.increment_with_ttl.await_count >= 2


def test_configured_cache_holds_both_independent_buckets():
    counters = {}

    async def increment(key, ttl):
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    cache_service = Mock()
    cache_service.enabled = True
    cache_service.initialized = True
    cache_service.get = AsyncMock(
        side_effect=lambda key: counters.get(key)
    )
    cache_service.increment_with_ttl = AsyncMock(side_effect=increment)
    client = TestClient(
        build_app(username_limit=1, ip_limit=20, cache_service=cache_service)
    )

    assert login(client, "Victim").status_code == 401
    assert login(client, "victim").status_code == 429
    assert any(key.startswith("login:ip:") for key in counters)
    assert any(key.endswith(":victim") for key in counters)


def test_rate_limit_trigger_is_written_to_admin_audit_path():
    app = build_app(username_limit=1)
    audit_service = Mock()
    audit_service.admin_events_enabled = True
    audit_service.log_admin_event = AsyncMock()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware, config=app.state.config)
    client = TestClient(app)

    assert login(client, "victim").status_code == 401
    assert login(client, "victim").status_code == 429

    record = audit_service.log_admin_event.await_args_list[-1].args[0]
    assert record.event_type == "auth.login.rate_limited"
    assert record.status_code == 429
    assert record.request_summary == {"username": "victim"}


def test_failed_login_is_written_with_a_redacted_reason():
    app = build_app(username_limit=20)
    audit_service = Mock()
    audit_service.admin_events_enabled = True
    audit_service.log_admin_event = AsyncMock()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware, config=app.state.config)
    client = TestClient(app)

    response = login(client, "victim")

    assert response.status_code == 401
    record = audit_service.log_admin_event.await_args.args[0]
    assert record.event_type == "auth.login.failed"
    assert record.success is False
    assert record.request_summary == {
        "username": "victim",
        "reason": "invalid_credentials",
    }
    assert "password" not in record.request_summary


def test_client_cannot_supply_a_reason_for_a_successful_login():
    app = build_app(username_limit=20)
    audit_service = Mock()
    audit_service.admin_events_enabled = True
    audit_service.log_admin_event = AsyncMock()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware, config=app.state.config)
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={
            "username": "victim",
            "password": "correct-password",
            "reason": "forged-audit-reason",
        },
    )

    assert response.status_code == 200
    record = audit_service.log_admin_event.await_args.args[0]
    assert record.event_type == "auth.login"
    assert record.request_summary == {"username": "victim"}


def test_durable_lockout_is_written_as_a_distinct_event():
    app = build_app(username_limit=20)
    audit_service = Mock()
    audit_service.admin_events_enabled = True
    audit_service.log_admin_event = AsyncMock()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware, config=app.state.config)
    client = TestClient(app)

    response = login(client, "victim", "locked-password")

    assert response.status_code == 401
    record = audit_service.log_admin_event.await_args.args[0]
    assert record.event_type == "auth.login.locked_out"
    assert record.request_summary == {
        "username": "victim",
        "reason": "invalid_credentials",
    }


def test_dashboard_login_bounds_context_only_audit_username():
    config = {
        "auth": {
            "login_rate_limit": {
                "enabled": True,
                "window_seconds": 60,
                "max_attempts_per_ip": 20,
                "max_attempts_per_username": 20,
            }
        }
    }
    app = FastAPI()
    app.state.config = config
    app.state.auth_service = FakeAuthService()
    app.include_router(create_admin_panel_router())
    audit_service = Mock()
    audit_service.admin_events_enabled = True
    audit_service.log_admin_event = AsyncMock()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware, config=config)

    with TestClient(app) as client:
        response = client.post(
            "/admin/login", data={"username": "x" * 500, "password": "wrong"}
        )

    assert response.status_code == 401
    record = audit_service.log_admin_event.await_args.args[0]
    assert record.request_summary == {
        "username": "x" * 50,
        "reason": "invalid_credentials",
    }


def test_dashboard_authorization_denial_is_not_a_credential_failure():
    config = {
        "auth": {
            "login_rate_limit": {
                "enabled": True,
                "window_seconds": 60,
                "max_attempts_per_ip": 20,
                "max_attempts_per_username": 20,
            }
        }
    }
    app = FastAPI()
    app.state.config = config
    app.state.auth_service = FakeAuthService()
    app.include_router(create_admin_panel_router())
    audit_service = Mock()
    audit_service.admin_events_enabled = True
    audit_service.log_admin_event = AsyncMock()
    app.state.audit_service = audit_service
    app.add_middleware(AdminAuditMiddleware, config=config)

    with TestClient(app) as client:
        response = client.post(
            "/admin/login", data={"username": "user", "password": "correct-password"}
        )

    assert response.status_code == 401
    record = audit_service.log_admin_event.await_args.args[0]
    assert record.event_type == "auth.dashboard.login.denied"
    assert record.request_summary == {
        "username": "user",
        "reason": "insufficient_permissions",
    }
