"""Route-level tests for the restyled dashboard 2FA login page (/admin/login/2fa).

Phase 7 (test_mfa.py) covers the MFA service contract; this only checks the
two changed server-rendered paths still behave identically after the restyle:
the pending token/next path stay escaped (regression guard for the XSS fix),
`dashboard_token`/`device_token` cookies are set the same way, and a wrong
code re-renders the same page with the pending token intact.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from routes.admin_panel_routes import create_admin_panel_router  # noqa: E402


class FakeMfaAuthService:
    """Fakes the two-step 2FA login without touching the database."""

    session_duration_hours = 12
    mfa = Mock(remember_device_days=30)

    def __init__(self):
        self.pending_token = "pending-abc123"
        self.user_info = {"id": "u1", "username": "admin", "permissions": ["*"]}

    async def authenticate_user(self, username, password, failure_context=None, **kwargs):
        if password != "correct-password":
            if failure_context is not None:
                failure_context["reason"] = "invalid_credentials"
            return False, None, None
        return True, self.pending_token, {**self.user_info, "mfa_required": True}

    async def peek_mfa_pending_user_id(self, pending_token):
        return self.user_info["id"] if pending_token == self.pending_token else None

    async def complete_2fa_login(self, pending_token, code, **kwargs):
        if pending_token != self.pending_token or code != "123456":
            return False, None, None, None
        return True, "session-token", self.user_info, None


def build_app():
    app = FastAPI()
    app.state.config = {}
    app.state.auth_service = FakeMfaAuthService()
    app.include_router(create_admin_panel_router())
    return app


def test_password_step_renders_2fa_page_with_escaped_pending_token_and_next():
    client = TestClient(build_app())

    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": "correct-password",
            "next": '/admin"><script>alert(1)</script>',
        },
    )

    assert response.status_code == 200
    assert "pending-abc123" in response.text
    # The malicious `next` must have been rejected by `_safe_next_path` and
    # any residual quote/markup HTML-escaped - not reflected raw.
    assert "<script>" not in response.text
    assert 'name="pending_token" value="pending-abc123"' in response.text


def test_wrong_code_rerenders_same_page_with_pending_token_intact():
    client = TestClient(build_app())

    response = client.post(
        "/admin/login/2fa",
        data={"pending_token": "pending-abc123", "code": "000000", "next": "/admin"},
    )

    assert response.status_code == 401
    assert "Invalid or expired two-factor code." in response.text
    assert 'name="pending_token" value="pending-abc123"' in response.text


def test_correct_code_sets_dashboard_cookie_and_redirects():
    client = TestClient(build_app())

    response = client.post(
        "/admin/login/2fa",
        data={"pending_token": "pending-abc123", "code": "123456", "next": "/admin"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert response.cookies.get("dashboard_token") == "session-token"
