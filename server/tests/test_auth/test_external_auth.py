"""
Tests for external identity provider (Entra ID / Auth0) token validation.
=========================================================================

These tests exercise the OIDC validation path added to AuthService.validate_token
without hitting a real identity provider: a local RSA keypair signs the JWTs and
each provider's PyJWKClient is monkeypatched to return the matching public key.

Backend is parameterized via TEST_BACKEND_TYPE (defaults to sqlite), mirroring
test_auth_service.py.
"""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.auth_service import AuthService
from services.database_service import create_database_service

# --- Test signing material and provider fixtures -------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

ENTRA_TENANT = "11111111-1111-1111-1111-111111111111"
ENTRA_CLIENT = "22222222-2222-2222-2222-222222222222"
ENTRA_ISS = f"https://login.microsoftonline.com/{ENTRA_TENANT}/v2.0"

AUTH0_DOMAIN = "orbit-test.us.auth0.com"
AUTH0_AUD = "https://api.orbit.test"
AUTH0_ISS = f"https://{AUTH0_DOMAIN}/"

BACKEND_TYPE = os.getenv("TEST_BACKEND_TYPE", "sqlite")

TEST_CONFIG = {
    'general': {},
    'internal_services': {
        'backend': {
            'type': BACKEND_TYPE,
            'sqlite': {'database_path': 'orbit_ext_test.db'},
        },
        'mongodb': {
            'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
            'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
            'database': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test"),
            'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
            'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD"),
            'users_collection': 'test_users',
            'sessions_collection': 'test_sessions',
        },
    },
    'auth': {
        'session_duration_hours': 1,
        'default_admin_username': 'admin',
        'default_admin_password': 'admin123',
        'pbkdf2_iterations': 1000,  # fast for tests
        'providers': {
            'enabled': True,
            'default_role': 'user',
            'entra': {'enabled': True, 'tenant_id': ENTRA_TENANT, 'client_id': ENTRA_CLIENT},
            'auth0': {'enabled': True, 'domain': AUTH0_DOMAIN, 'audience': AUTH0_AUD},
        },
    },
}


def make_token(iss, aud, sub, *, exp_delta=3600, email=None, key=None, extra=None):
    """Sign a JWT with the shared test private key (RS256)."""
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_delta}
    if email:
        payload["email"] = email
    if extra:
        payload.update(extra)
    return jwt.encode(payload, key or _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test"})


class _FakeJWKS:
    """Stand-in for PyJWKClient that returns a fixed public key, no network."""

    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self._key)


@pytest_asyncio.fixture(scope="function")
async def database_service():
    config = TEST_CONFIG
    backend_type = config['internal_services']['backend']['type']

    if backend_type == 'sqlite':
        from services.sqlite_service import SQLiteService
        SQLiteService.clear_cache()
        db_path = config['internal_services']['backend']['sqlite']['database_path']
        if os.path.exists(db_path):
            os.remove(db_path)

    database = create_database_service(config)
    await database.initialize()
    yield database

    database.close()
    if backend_type == 'sqlite':
        db_path = config['internal_services']['backend']['sqlite']['database_path']
        if os.path.exists(db_path):
            os.remove(db_path)
        from services.sqlite_service import SQLiteService
        SQLiteService.clear_cache()


@pytest_asyncio.fixture(scope="function")
async def auth_service(database_service):
    """AuthService with external providers enabled and JWKS clients faked."""
    service = AuthService(TEST_CONFIG, database_service=database_service)
    await service.initialize()

    # Replace each provider's JWKS client so verification uses the local key.
    assert service._oidc_enabled, "External providers should be enabled in test config"
    for entry in service._oidc._providers.values():
        entry["jwks_client"] = _FakeJWKS(_PUBLIC_KEY)

    yield service
    await service.close()


# --- Tests ---------------------------------------------------------------------

async def test_entra_token_provisions_user(auth_service: AuthService):
    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-1", email="alice@example.com")
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    assert user["username"] == "entra:entra-sub-1"
    assert user["role"] == "user"

    # The user is persisted with provider metadata.
    record = await auth_service.get_user_by_username("entra:entra-sub-1")
    assert record["provider"] == "entra"
    assert record["email"] == "alice@example.com"


async def test_entra_accepts_api_audience(auth_service: AuthService):
    token = make_token(ENTRA_ISS, f"api://{ENTRA_CLIENT}", "entra-sub-api")
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    assert user["username"] == "entra:entra-sub-api"


async def test_entra_accepts_legacy_v1_issuer(auth_service: AuthService):
    """Entra can mint v1.0-format access tokens (iss=https://sts.windows.net/{tenant}/)
    for the same resource/audience as v2.0 tokens, depending on the app registration's
    accessTokenAcceptedVersion manifest setting — not something callers control per-request.
    Both issuer shapes must validate."""
    v1_iss = f"https://sts.windows.net/{ENTRA_TENANT}/"
    token = make_token(v1_iss, ENTRA_CLIENT, "entra-sub-v1", email="dave@example.com")
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    assert user["username"] == "entra:entra-sub-v1"


async def test_entra_v1_token_falls_back_to_upn_for_email(auth_service: AuthService):
    """Entra v1-format access tokens minted for a custom API scope carry `upn`/
    `unique_name` instead of `email`/`preferred_username` — email must still be
    captured via that fallback."""
    v1_iss = f"https://sts.windows.net/{ENTRA_TENANT}/"
    token = make_token(
        v1_iss, ENTRA_CLIENT, "entra-sub-upn",
        extra={"upn": "erin@example.com", "unique_name": "erin@example.com"},
    )
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    record = await auth_service.get_user_by_username("entra:entra-sub-upn")
    assert record["email"] == "erin@example.com"


async def test_concurrent_first_login_does_not_error(auth_service: AuthService):
    """Two near-simultaneous requests carrying the same brand-new user's token
    (e.g. orbitchat firing several API calls right after login) must not surface
    a raw duplicate-key error. Whichever call loses the insert race falls back
    to fetching the row the winner created, per _find_or_create_external_user's
    `except DatabaseDuplicateKeyError` handling — which only works if the backend
    actually raises that abstraction-layer exception (regression coverage for a
    bug where all three backends raised/swallowed the raw driver exception instead)."""
    import asyncio

    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-concurrent", email="frank@example.com")
    results = await asyncio.gather(
        auth_service.validate_token(token),
        auth_service.validate_token(token),
    )
    for is_valid, user in results:
        assert is_valid
        assert user is not None
        assert user["username"] == "entra:entra-sub-concurrent"

    # Exactly one user row exists despite the race.
    users = await auth_service.list_users({"username": "entra:entra-sub-concurrent"})
    assert len(users) == 1


async def test_auth0_token_provisions_user(auth_service: AuthService):
    token = make_token(AUTH0_ISS, AUTH0_AUD, "auth0|abc", email="bob@example.com")
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    assert user["username"] == "auth0:auth0|abc"


async def test_auth0_token_without_email_claim_provisions_with_no_email(auth_service: AuthService):
    """Auth0 access tokens for a custom API audience carry no bare 'email' claim
    by default — provisioning must still succeed, just without an email captured."""
    token = make_token(AUTH0_ISS, AUTH0_AUD, "auth0|no-email")
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    record = await auth_service.get_user_by_username("auth0:auth0|no-email")
    assert record["email"] is None


async def test_auth0_configurable_email_claim_namespaced(auth_service: AuthService):
    """A namespaced custom claim (from an Auth0 Action) is read when configured
    via auth.providers.auth0.email_claim, taking priority over a bare 'email' claim."""
    auth_service._oidc._providers["auth0"]["email_claim"] = "https://your-api/email"
    token = make_token(
        AUTH0_ISS, AUTH0_AUD, "auth0|namespaced",
        extra={"https://your-api/email": "carol@example.com"},
    )
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid
    record = await auth_service.get_user_by_username("auth0:auth0|namespaced")
    assert record["email"] == "carol@example.com"


async def test_existing_external_user_reused(auth_service: AuthService):
    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-dup")
    v1, u1 = await auth_service.validate_token(token)
    v2, u2 = await auth_service.validate_token(token)
    assert v1 and v2
    assert u1["id"] == u2["id"]

    users = await auth_service.list_users()
    matches = [u for u in users if u["username"] == "entra:entra-sub-dup"]
    assert len(matches) == 1


async def test_wrong_audience_rejected(auth_service: AuthService):
    token = make_token(ENTRA_ISS, "some-other-audience", "entra-sub-aud")
    is_valid, user = await auth_service.validate_token(token)
    assert not is_valid
    assert user is None


async def test_bad_signature_rejected(auth_service: AuthService):
    # Signed with a key that does not match the JWKS public key.
    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-badsig", key=_WRONG_KEY)
    is_valid, user = await auth_service.validate_token(token)
    assert not is_valid


async def test_expired_token_rejected(auth_service: AuthService):
    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-exp", exp_delta=-3600)
    is_valid, user = await auth_service.validate_token(token)
    assert not is_valid


async def test_missing_sub_rejected(auth_service: AuthService):
    now = int(time.time())
    payload = {"iss": ENTRA_ISS, "aud": ENTRA_CLIENT, "iat": now, "exp": now + 3600}
    token = jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test"})
    is_valid, user = await auth_service.validate_token(token)
    assert not is_valid


async def test_unknown_issuer_rejected(auth_service: AuthService):
    token = make_token("https://evil.example.com/", ENTRA_CLIENT, "entra-sub-iss")
    is_valid, user = await auth_service.validate_token(token)
    assert not is_valid


async def test_deactivated_external_user_cannot_relogin(auth_service: AuthService):
    token = make_token(AUTH0_ISS, AUTH0_AUD, "auth0|deactivate")
    is_valid, user = await auth_service.validate_token(token)
    assert is_valid

    ok = await auth_service.update_user_status(user["id"], active=False)
    assert ok

    # Re-login must not silently reactivate the user.
    is_valid2, user2 = await auth_service.validate_token(token)
    assert not is_valid2
    assert user2 is None


async def test_logout_external_token_is_noop(auth_service: AuthService):
    # A stateless provider JWT has no local session row; logout must succeed
    # (no-op) rather than fail because delete_one matched nothing.
    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-logout")
    is_valid, _ = await auth_service.validate_token(token)
    assert is_valid
    assert await auth_service.logout(token) is True


async def test_external_user_cannot_password_login(auth_service: AuthService):
    token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-pw")
    is_valid, _ = await auth_service.validate_token(token)
    assert is_valid
    # No password login for an external identity.
    success, tok, _ = await auth_service.authenticate_user("entra:entra-sub-pw", "anything")
    assert not success
    assert tok is None


async def test_jwt_rejected_when_providers_disabled(database_service):
    """A JWT-shaped token falls through to the (failing) session path when disabled."""
    config = {**TEST_CONFIG, 'auth': {**TEST_CONFIG['auth'], 'providers': {'enabled': False}}}
    service = AuthService(config, database_service=database_service)
    await service.initialize()
    try:
        assert service._oidc_enabled is False
        token = make_token(ENTRA_ISS, ENTRA_CLIENT, "entra-sub-off")
        is_valid, user = await service.validate_token(token)
        assert not is_valid
        assert user is None
    finally:
        await service.close()
