"""Authentication-route response contracts."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from routes.auth_dependencies import get_current_user  # noqa: E402
from routes.auth_routes import auth_router  # noqa: E402


def test_auth_me_without_bearer_token_is_401_not_500():
    """/auth/me requires identity even though the shared dependency is optional."""
    app = FastAPI()
    app.state.auth_service = object()
    app.include_router(auth_router)

    response = TestClient(app, raise_server_exceptions=False).get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Authentication required"


def test_list_my_sessions_without_bearer_token_is_401_not_500():
    """/auth/sessions requires identity even though the shared dependency is optional."""
    app = FastAPI()
    app.state.auth_service = object()
    app.include_router(auth_router)

    response = TestClient(app, raise_server_exceptions=False).get("/auth/sessions")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Authentication required"


def test_revoke_my_session_without_bearer_token_is_401_not_500():
    """DELETE /auth/sessions/{id} requires identity even though the shared dependency is optional."""
    app = FastAPI()
    app.state.auth_service = object()
    app.include_router(auth_router)

    response = TestClient(app, raise_server_exceptions=False).delete("/auth/sessions/some-id")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Authentication required"


def test_delete_admin_ip_rule_guard_uses_trusted_proxy_client_ip():
    """The self-lockout guard on DELETE /auth/admin-ip-rules/{id} must resolve
    the requester's IP the same way AdminIpAllowlistMiddleware does. Behind a
    configured trusted reverse proxy, using extract_ip's defaults instead
    would see the proxy's own (loopback) address, read it as "localhost", and
    skip the guard entirely - letting an admin delete their only forwarded-IP
    rule without ?force=true and lock themselves out."""
    app = FastAPI()

    admin_ip_service = Mock()
    admin_ip_service.enforcing = True
    admin_ip_service.get_rule = AsyncMock(return_value={"_id": "rule1", "cidr": "203.0.113.9/32"})
    admin_ip_service.rules_excluding = AsyncMock(return_value=[])
    admin_ip_service.allowed_under = Mock(return_value=False)

    auth_service_stub = Mock(
        admin_ip_allowlist=admin_ip_service,
        config={
            "security": {
                "rate_limiting": {
                    "trust_proxy_headers": True,
                    "trusted_proxies": ["127.0.0.1"],
                }
            }
        },
    )
    app.state.auth_service = auth_service_stub
    app.include_router(auth_router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "admin1", "username": "admin", "permissions": ["*"],
    }

    client = TestClient(app, client=("127.0.0.1", 12345))
    response = client.delete(
        "/auth/admin-ip-rules/rule1",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )

    assert response.status_code == 400
    assert "203.0.113.9" in response.json()["detail"]
    admin_ip_service.allowed_under.assert_called_once_with([], "203.0.113.9")
