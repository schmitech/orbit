"""
Tests for AdminRateLimitMiddleware.

Tests cover:
- Enabled by default, independent of security.rate_limiting.enabled
- 429 + X-RateLimit-* headers once the configured limit is exceeded
- Non-allowlisted routes are never throttled
- No activation below the configured threshold
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from middleware.rate_limit_middleware import AdminRateLimitMiddleware


def _app_with_admin_routes(config: dict) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AdminRateLimitMiddleware, config=config)

    @app.post("/admin/api-keys")
    def create_key():
        return {"ok": True}

    @app.get("/admin/audit/events")
    def audit_events():
        return {"ok": True}

    @app.get("/admin/other")
    def unrelated():
        return {"ok": True}

    return app


class TestAdminRateLimitMiddlewareDefaults:
    def test_enabled_by_default_with_no_config(self):
        """No security block at all — still active (unlike the general limiter)."""
        app = _app_with_admin_routes({})
        client = TestClient(app)

        response = client.post("/admin/api-keys")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers

    def test_independent_of_general_rate_limiting_toggle(self):
        """Stays active even when security.rate_limiting.enabled is false."""
        config = {
            'security': {
                'rate_limiting': {'enabled': False},
                'admin_rate_limiting': {
                    'route_limits': {'POST /admin/api-keys': 1},
                },
            }
        }
        app = _app_with_admin_routes(config)
        client = TestClient(app)

        assert client.post("/admin/api-keys").status_code == 200
        response = client.post("/admin/api-keys")
        assert response.status_code == 429
        assert "X-RateLimit-Remaining" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_explicitly_disabled(self):
        config = {'security': {'admin_rate_limiting': {'enabled': False}}}
        app = _app_with_admin_routes(config)
        client = TestClient(app)

        for _ in range(50):
            response = client.post("/admin/api-keys")
            assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers


class TestAdminRateLimitMiddlewareScoping:
    def test_non_allowlisted_route_is_never_throttled(self):
        config = {
            'security': {
                'admin_rate_limiting': {
                    'route_limits': {'GET /admin/other': 1},
                }
            }
        }
        # /admin/other is intentionally not in DEFAULT_ROUTE_LIMITS, so the
        # override above has no effect — the route must stay unthrottled.
        app = _app_with_admin_routes(config)
        client = TestClient(app)

        for _ in range(10):
            response = client.get("/admin/other")
            assert response.status_code == 200
            assert "X-RateLimit-Limit" not in response.headers

    def test_bearer_scheme_casing_does_not_bypass_per_credential_limit(self):
        """Same credential, different Authorization scheme casing, must
        share one rate-limit bucket (not get a fresh allowance per casing)."""
        config = {
            'security': {
                'admin_rate_limiting': {
                    'route_limits': {'GET /admin/audit/events': 2},
                }
            }
        }
        app = _app_with_admin_routes(config)
        client = TestClient(app)

        schemes = ["Bearer", "bearer", "BEARER", "BeArEr"]
        statuses = [
            client.get(
                "/admin/audit/events",
                headers={"Authorization": f"{scheme} sometoken"},
            ).status_code
            for scheme in schemes
        ]
        assert statuses == [200, 200, 429, 429]

    def test_does_not_activate_below_threshold(self):
        config = {
            'security': {
                'admin_rate_limiting': {
                    'route_limits': {'GET /admin/audit/events': 5},
                }
            }
        }
        app = _app_with_admin_routes(config)
        client = TestClient(app)

        for _ in range(5):
            response = client.get("/admin/audit/events")
            assert response.status_code == 200

    def test_burst_past_limit_returns_429_with_headers(self):
        config = {
            'security': {
                'admin_rate_limiting': {
                    'route_limits': {'GET /admin/audit/events': 3},
                }
            }
        }
        app = _app_with_admin_routes(config)
        client = TestClient(app)

        statuses = [client.get("/admin/audit/events").status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]

        response = client.get("/admin/audit/events")
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Limit"] == "3"
        assert "Retry-After" in response.headers


class TestAdminRateLimitMiddlewareCacheBackend:
    def test_uses_cache_service_when_available(self):
        app = FastAPI()
        config = {
            'security': {
                'admin_rate_limiting': {
                    'route_limits': {'POST /admin/api-keys': 2},
                }
            }
        }
        app.add_middleware(AdminRateLimitMiddleware, config=config)

        @app.post("/admin/api-keys")
        def create_key():
            return {"ok": True}

        cache_service = Mock()
        cache_service.enabled = True
        cache_service.initialized = True
        counts = iter([1, 2, 3])
        cache_service.increment_with_ttl = AsyncMock(side_effect=lambda *a, **k: next(counts))

        with TestClient(app) as client:
            client.app.state.cache_service = cache_service
            assert client.post("/admin/api-keys").status_code == 200
            assert client.post("/admin/api-keys").status_code == 200
            response = client.post("/admin/api-keys")
            assert response.status_code == 429

        assert cache_service.increment_with_ttl.await_count == 3
