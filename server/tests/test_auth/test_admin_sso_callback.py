"""
Admin SSO callback route tests.
===============================

test_admin_sso.py covers AdminSSOService and AuthService in isolation. This
file drives the actual ``GET /admin/auth/{provider}/callback`` route, which is
where the three denial paths are distinguished and where the ``dashboard_token``
cookie is minted — the wiring none of the service-level tests exercise.

The provider is faked at the service boundary (``exchange_code`` /
``validate_id_token``), so no network and no JWT signing is involved here;
token validation itself is covered by test_admin_sso.py.
"""

import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from routes.admin_panel_routes import create_admin_panel_router  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from services.sqlite_service import SQLiteService  # noqa: E402

TEMP_DIR = None

ADMIN_EMAIL = "boss@example.com"


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


class FakeSSOService:
    """Stands in for AdminSSOService: a fixed id_token, a real allowlist check."""

    def __init__(self, admin_users, claims):
        self._admin_emails = {str(e).strip().lower() for e in admin_users}
        self._claims = claims

    def provider_enabled(self, provider):
        return provider in ("entra", "auth0")

    def redirect_uri(self, provider, base_url):
        return f"{base_url.rstrip('/')}/admin/auth/{provider}/callback"

    async def exchange_code(self, provider, code, verifier, redirect_uri):
        return {"id_token": "fake-id-token"}

    async def validate_id_token(self, provider, id_token, nonce):
        return self._claims

    def requires_verified_email(self, provider):
        return True

    def is_admin(self, email, provider, subject, email_verified=None):
        if email and email.strip().lower() in self._admin_emails:
            return email_verified is True
        return False


def get_test_config(name, *, access_control="allowlist", admin_users=None):
    return {
        'general': {},
        'auth': {
            'default_admin_username': 'admin',
            'default_admin_password': 'admin12345',
            'session_duration_hours': 1,
            'pbkdf2_iterations': 1000,
            'allowlist': {'cache_ttl': 0},
            'blacklist': {'cache_ttl': 0},
            'providers': {
                'enabled': True,
                'default_role': 'user',
                'access_control': access_control,
                'admin_sso': {'enabled': True, 'admin_users': admin_users or []},
            },
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(
                        TEMP_DIR, f"ssocb_{name}_{os.getpid()}.db"
                    )
                }
            }
        },
    }


async def build_app(name, *, claims, access_control="allowlist", admin_users=None):
    config = get_test_config(
        name, access_control=access_control, admin_users=admin_users
    )
    database = SQLiteService(config)
    await database.initialize()
    auth_service = AuthService(config, database)
    await auth_service.initialize()

    app = FastAPI()
    app.include_router(create_admin_panel_router())
    app.state.auth_service = auth_service
    app.state.config = config
    # get_sso_service reads this cached attribute before trying to build one.
    app.state.admin_sso_service = FakeSSOService(admin_users or [], claims)
    return app, auth_service


def flow_cookie(provider, state="the-state"):
    payload = {
        "provider": provider, "state": state,
        "verifier": "the-verifier", "nonce": "the-nonce", "next": "/admin",
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode("ascii")


def callback(app, provider="auth0", state="the-state"):
    with TestClient(app) as client:
        client.cookies.set("admin_sso_flow", flow_cookie(provider, state))
        return client.get(
            f"/admin/auth/{provider}/callback",
            params={"code": "the-code", "state": state},
            follow_redirects=False,
        )


def redirect_error(response):
    """The `error` query param on the login redirect, or None."""
    assert response.status_code in (302, 303, 307), response.status_code
    query = parse_qs(urlparse(response.headers["location"]).query)
    return (query.get("error") or [None])[0]


@pytest_asyncio.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Denial paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_not_cleared_identity_is_rejected_with_its_own_error(request):
    """A stranger under deny-by-default gets `not_cleared`, not `not_authorized`,
    and leaves no row behind."""
    app, auth_service = await build_app(
        request.node.name,
        claims={"sub": "stranger-sub", "email": "stranger@example.com",
                "email_verified": True},
    )
    try:
        response = callback(app)
        assert redirect_error(response) == "not_cleared"
        assert "dashboard_token" not in response.cookies
        assert await auth_service.database.find_one(
            "users", {"username": "auth0:stranger-sub"}
        ) is None
    finally:
        await auth_service.close()


@pytest.mark.asyncio
async def test_cleared_but_roleless_identity_gets_not_authorized(request):
    """Pre-clearing grants an account, not the panel: a cleared identity with
    only the default `user` role is still denied, but for a different reason."""
    app, auth_service = await build_app(
        request.node.name,
        claims={"sub": "employee-sub", "email": "employee@corp.example.com",
                "email_verified": True},
    )
    try:
        await auth_service.allowlist.add_rule("*@corp.example.com", "email")

        response = callback(app)
        assert redirect_error(response) == "not_authorized"
        assert "dashboard_token" not in response.cookies
        # Cleared, so the account exists - it just has no panel permissions.
        user = await auth_service.database.find_one(
            "users", {"username": "auth0:employee-sub"}
        )
        assert user is not None
        assert user["role"] == "user"
    finally:
        await auth_service.close()


@pytest.mark.asyncio
async def test_unverified_email_does_not_reach_admin(request):
    """The bypass this work closes: an allowlisted address that the IdP has not
    verified must not be promoted to admin."""
    app, auth_service = await build_app(
        request.node.name,
        admin_users=[ADMIN_EMAIL],
        claims={"sub": "attacker-sub", "email": ADMIN_EMAIL,
                "email_verified": False},
    )
    try:
        response = callback(app)
        assert redirect_error(response) == "not_authorized"
        assert "dashboard_token" not in response.cookies
        user = await auth_service.database.find_one(
            "users", {"username": "auth0:attacker-sub"}
        )
        # Implicitly cleared (the email is in admin_users) but NOT made admin.
        assert user is not None
        assert user["role"] != "admin"
    finally:
        await auth_service.close()


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allowlisted_admin_gets_a_session(request):
    """admin_users clears the identity implicitly, so enabling deny-by-default
    with zero rules doesn't lock the operator out of their own panel."""
    app, auth_service = await build_app(
        request.node.name,
        admin_users=[ADMIN_EMAIL],
        claims={"sub": "boss-sub", "email": ADMIN_EMAIL, "email_verified": True},
    )
    try:
        response = callback(app)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"
        token = response.cookies.get("dashboard_token")
        assert token

        valid, user_info = await auth_service.validate_token(token)
        assert valid is True
        assert user_info["role"] == "admin"
    finally:
        await auth_service.close()


@pytest.mark.asyncio
async def test_allowlist_rule_admits_a_user_with_a_panel_role(request):
    """A non-allowlisted identity still signs in when it is both cleared and
    holds a manually assigned panel role."""
    app, auth_service = await build_app(
        request.node.name,
        claims={"sub": "ops-sub", "email": "ops@corp.example.com",
                "email_verified": True},
    )
    try:
        await auth_service.allowlist.add_rule("*@corp.example.com", "email")
        user = await auth_service._find_or_create_external_user(
            "auth0", "ops-sub", "ops@corp.example.com"
        )
        assert await auth_service.set_role(str(user["_id"]), "operator")

        response = callback(app)
        assert response.status_code == 303
        assert response.cookies.get("dashboard_token")
    finally:
        await auth_service.close()


@pytest.mark.asyncio
async def test_open_mode_preserves_previous_behaviour(request):
    """With access_control: open, a first-time identity is provisioned as before
    and denied only for lacking a panel role."""
    app, auth_service = await build_app(
        request.node.name,
        access_control="open",
        claims={"sub": "stranger-sub", "email": "stranger@example.com",
                "email_verified": True},
    )
    try:
        response = callback(app)
        assert redirect_error(response) == "not_authorized"
        assert await auth_service.database.find_one(
            "users", {"username": "auth0:stranger-sub"}
        ) is not None
    finally:
        await auth_service.close()
