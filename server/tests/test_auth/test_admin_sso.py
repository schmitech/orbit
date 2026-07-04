"""
Tests for admin-panel SSO (Entra ID / Auth0).
==============================================

Covers AdminSSOService (authorize-URL building, id_token validation, allowlist)
and the AuthService helpers the SSO callback relies on (create_session, set_role,
provision_sso_user). No network: a local RSA keypair signs id_tokens and each
provider's PyJWKClient is monkeypatched to return the matching public key.
"""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import jwt
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.admin_sso_service import AdminSSOService
from services.auth_service import AuthService
from services.database_service import create_database_service

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

ENTRA_TENANT = "11111111-1111-1111-1111-111111111111"
ENTRA_CLIENT = "22222222-2222-2222-2222-222222222222"
ENTRA_ISS = f"https://login.microsoftonline.com/{ENTRA_TENANT}/v2.0"

AUTH0_DOMAIN = "orbit-test.us.auth0.com"
AUTH0_CLIENT = "auth0-client-id"
AUTH0_ISS = f"https://{AUTH0_DOMAIN}/"

PROVIDERS_CONFIG = {
    "admin_sso": {
        "enabled": True,
        "admin_users": ["Admin@Example.com", "entra:allowlisted-sub"],
    },
    "entra": {"enabled": True, "tenant_id": ENTRA_TENANT, "client_id": ENTRA_CLIENT},
    "auth0": {
        "enabled": True, "domain": AUTH0_DOMAIN,
        "audience": "https://api.orbit.test", "client_id": AUTH0_CLIENT,
    },
}

BACKEND_TYPE = os.getenv("TEST_BACKEND_TYPE", "sqlite")

AUTH_CONFIG = {
    "general": {},
    "internal_services": {
        "backend": {"type": BACKEND_TYPE, "sqlite": {"database_path": "orbit_sso_test.db"}},
        "mongodb": {
            "host": os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
            "port": int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
            "database": os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test"),
            "username": os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
            "password": os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD"),
            "users_collection": "test_users",
            "sessions_collection": "test_sessions",
        },
    },
    "auth": {
        "session_duration_hours": 1,
        "default_admin_username": "admin",
        "default_admin_password": "admin123",
        "pbkdf2_iterations": 1000,
    },
}


class _FakeJWKS:
    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self._key)


def make_id_token(iss, aud, sub, *, nonce="n0", exp_delta=3600, email=None, key=None):
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_delta, "nonce": nonce}
    if email:
        payload["email"] = email
    return jwt.encode(payload, key or _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test"})


def make_sso_service():
    svc = AdminSSOService(PROVIDERS_CONFIG)
    for entry in svc._providers.values():
        entry["jwks_client"] = _FakeJWKS(_PUBLIC_KEY)
    return svc


# --- AdminSSOService: authorize URL --------------------------------------------

def test_build_authorize_url_entra():
    svc = make_sso_service()
    url, state, verifier, nonce = svc.build_authorize_url(
        "entra", "https://host/admin/auth/entra/callback")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == f"/{ENTRA_TENANT}/oauth2/v2.0/authorize"
    assert q["client_id"] == [ENTRA_CLIENT]
    assert q["response_type"] == ["code"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == [state]
    assert q["nonce"] == [nonce]
    assert "openid" in q["scope"][0]
    assert verifier  # PKCE verifier returned to caller


def test_build_authorize_url_auth0():
    svc = make_sso_service()
    url, _, _, _ = svc.build_authorize_url("auth0", "https://host/admin/auth/auth0/callback")
    parsed = urlparse(url)
    assert parsed.netloc == AUTH0_DOMAIN
    assert parsed.path == "/authorize"


def test_redirect_uri_uses_base_url_override():
    cfg = {**PROVIDERS_CONFIG, "admin_sso": {**PROVIDERS_CONFIG["admin_sso"], "base_url": "https://orbit.example.com/"}}
    svc = AdminSSOService(cfg)
    assert svc.redirect_uri("entra", "http://ignored/") == "https://orbit.example.com/admin/auth/entra/callback"


def test_redirect_uri_auto_detected():
    svc = make_sso_service()
    assert svc.redirect_uri("auth0", "http://localhost:3000/") == "http://localhost:3000/admin/auth/auth0/callback"


# --- AdminSSOService: id_token validation --------------------------------------

async def test_validate_id_token_ok():
    svc = make_sso_service()
    token = make_id_token(ENTRA_ISS, ENTRA_CLIENT, "sub-1", nonce="abc", email="user@example.com")
    claims = await svc.validate_id_token("entra", token, "abc")
    assert claims is not None
    assert claims["sub"] == "sub-1"
    assert claims["email"] == "user@example.com"


async def test_validate_id_token_wrong_audience():
    svc = make_sso_service()
    token = make_id_token(ENTRA_ISS, "some-other-client", "sub-2", nonce="abc")
    assert await svc.validate_id_token("entra", token, "abc") is None


async def test_validate_id_token_nonce_mismatch():
    svc = make_sso_service()
    token = make_id_token(ENTRA_ISS, ENTRA_CLIENT, "sub-3", nonce="expected")
    assert await svc.validate_id_token("entra", token, "different") is None


async def test_validate_id_token_bad_signature():
    svc = make_sso_service()
    token = make_id_token(ENTRA_ISS, ENTRA_CLIENT, "sub-4", nonce="abc", key=_WRONG_KEY)
    assert await svc.validate_id_token("entra", token, "abc") is None


async def test_validate_id_token_expired():
    svc = make_sso_service()
    token = make_id_token(ENTRA_ISS, ENTRA_CLIENT, "sub-5", nonce="abc", exp_delta=-3600)
    assert await svc.validate_id_token("entra", token, "abc") is None


# --- AdminSSOService: allowlist ------------------------------------------------

def test_is_admin_email_case_insensitive():
    svc = make_sso_service()
    assert svc.is_admin("admin@example.com", "auth0", "whatever")
    assert svc.is_admin("ADMIN@EXAMPLE.COM", "auth0", "whatever")


def test_is_admin_by_provider_subject():
    svc = make_sso_service()
    assert svc.is_admin(None, "entra", "allowlisted-sub")


def test_is_admin_rejects_unknown():
    svc = make_sso_service()
    assert not svc.is_admin("nobody@example.com", "entra", "random-sub")


def test_is_admin_subject_is_case_sensitive():
    # Allowlist has "entra:allowlisted-sub"; OIDC subjects are case-sensitive,
    # so a case-variant subject must NOT be granted admin.
    svc = make_sso_service()
    assert svc.is_admin(None, "entra", "allowlisted-sub")
    assert not svc.is_admin(None, "entra", "ALLOWLISTED-SUB")


# --- AuthService helpers -------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def auth_service():
    backend_type = AUTH_CONFIG["internal_services"]["backend"]["type"]
    if backend_type == "sqlite":
        from services.sqlite_service import SQLiteService
        SQLiteService.clear_cache()
        db_path = AUTH_CONFIG["internal_services"]["backend"]["sqlite"]["database_path"]
        if os.path.exists(db_path):
            os.remove(db_path)

    database = create_database_service(AUTH_CONFIG)
    await database.initialize()
    service = AuthService(AUTH_CONFIG, database_service=database)
    await service.initialize()

    yield service

    await service.close()
    database.close()
    if backend_type == "sqlite":
        db_path = AUTH_CONFIG["internal_services"]["backend"]["sqlite"]["database_path"]
        if os.path.exists(db_path):
            os.remove(db_path)
        from services.sqlite_service import SQLiteService
        SQLiteService.clear_cache()


async def test_create_session_roundtrips(auth_service: AuthService):
    user = await auth_service.provision_sso_user("entra", "sess-sub", "s@example.com", is_admin=True)
    assert user is not None
    token = await auth_service.create_session(user)
    assert token and "." not in token  # opaque session token, not a JWT
    valid, info = await auth_service.validate_token(token)
    assert valid
    assert info["username"] == "entra:sess-sub"
    assert info["role"] == "admin"


async def test_provision_sso_user_creates_admin(auth_service: AuthService):
    user = await auth_service.provision_sso_user("auth0", "new-admin", "a@example.com", is_admin=True)
    assert user["role"] == "admin"
    record = await auth_service.get_user_by_username("auth0:new-admin")
    assert record["role"] == "admin"
    assert record["provider"] == "auth0"


async def test_provision_sso_user_promotes_existing(auth_service: AuthService):
    # First seen as a non-admin (not on allowlist).
    first = await auth_service.provision_sso_user("entra", "promote-me", "p@example.com", is_admin=False)
    assert first["role"] == "user"
    # Later added to the allowlist -> promoted on next login.
    promoted = await auth_service.provision_sso_user("entra", "promote-me", "p@example.com", is_admin=True)
    assert promoted["role"] == "admin"
    record = await auth_service.get_user_by_username("entra:promote-me")
    assert record["role"] == "admin"


async def test_set_role_rejects_invalid(auth_service: AuthService):
    user = await auth_service.provision_sso_user("entra", "role-test", None, is_admin=False)
    assert await auth_service.set_role(str(user["_id"]), "superuser") is False
