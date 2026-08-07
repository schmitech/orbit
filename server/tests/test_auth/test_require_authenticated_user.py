"""
Tests for auth.require_authenticated_user (the "strict mode" flag).

Covers:
- The precedence rule between the global flag and an adapter's
  capabilities.requires_authenticated_user override (is_authenticated_user_required).
- Enforcement inside the real get_api_key/get_user_id dependencies built by
  RouteConfigurator, wired to a real (SQLite-backed) AuthService so that
  the user blacklist is genuinely exercised.
- The specific bug this flag exists to close: a blacklisted user reaching
  inference by presenting an API key with no bearer token.
- Bearer-as-API-key suppression, X-User-ID suppression, single-resolution
  caching, and fail-closed bypass lanes.
"""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from routes.auth_helpers import is_authenticated_user_required  # noqa: E402
from routes.routes_configurator import RouteConfigurator  # noqa: E402
from services.auth_service import AuthService  # noqa: E402
from services.sqlite_service import SQLiteService  # noqa: E402

TEMP_DIR = None
VALID_KEY = "orbit_validkey0000000000000000000"


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# Pure precedence function
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("global_flag,adapter_override,expected", [
    (False, None, False),
    (False, True, True),
    (False, False, False),
    (True, None, True),
    (True, True, True),
    (True, False, False),
])
def test_is_authenticated_user_required_precedence(global_flag, adapter_override, expected):
    config = {"auth": {"require_authenticated_user": global_flag}}
    adapter_config = None
    if adapter_override is not None:
        adapter_config = {"capabilities": {"requires_authenticated_user": adapter_override}}
    assert is_authenticated_user_required(config, adapter_config) is expected


@pytest.mark.unit
def test_is_authenticated_user_required_no_adapter_config():
    assert is_authenticated_user_required({"auth": {"require_authenticated_user": True}}, None) is True
    assert is_authenticated_user_required({"auth": {"require_authenticated_user": False}}, None) is False


@pytest.mark.unit
@pytest.mark.parametrize("global_flag,adapter_override_string,expected", [
    (False, "true", True),
    (False, "false", False),
    (True, "false", False),
    (True, "true", True),
])
def test_is_authenticated_user_required_env_substituted_string_override(
    global_flag, adapter_override_string, expected
):
    """capabilities.requires_authenticated_user: ${SOME_VAR} always arrives as
    a string after env substitution - a bare bool() cast would get "false"
    wrong (bool("false") is True in Python)."""
    config = {"auth": {"require_authenticated_user": global_flag}}
    adapter_config = {"capabilities": {"requires_authenticated_user": adapter_override_string}}
    assert is_authenticated_user_required(config, adapter_config) is expected


# ---------------------------------------------------------------------------
# Fixtures: real AuthService (SQLite) + a minimal FastAPI app wired to the
# actual get_api_key/get_user_id dependencies produced by RouteConfigurator.
# ---------------------------------------------------------------------------

class CountingAuthService:
    """Wraps a real AuthService, counting validate_token calls."""

    def __init__(self, inner):
        self._inner = inner
        self.validate_token_calls = 0

    async def validate_token(self, token):
        self.validate_token_calls += 1
        return await self._inner.validate_token(token)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class FakeApiKeyService:
    """Mirrors just enough of ApiKeyService.get_adapter_for_api_key for these tests."""

    def __init__(self, allowed_user_ids=None, allowed_emails=None):
        self.allowed_user_ids = allowed_user_ids or []
        self.allowed_emails = allowed_emails or []

    async def get_adapter_for_api_key(self, api_key, adapter_manager=None,
                                       current_user_id=None, current_user_email=None):
        if api_key != VALID_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if self.allowed_user_ids or self.allowed_emails:
            if current_user_id not in self.allowed_user_ids and current_user_email not in self.allowed_emails:
                raise HTTPException(status_code=401, detail="Caller not permitted to use this API key")
        return "test-adapter", None


def _get_test_config(name, strict=False):
    return {
        'general': {},
        'auth': {
            'default_admin_username': 'admin',
            'default_admin_password': 'admin12345',
            'blacklist': {'cache_ttl': 0},
            'require_authenticated_user': strict,
        },
        'api_keys': {
            'header_name': 'X-API-Key',
        },
        'chat_history': {
            'enabled': True,
            'user': {'header_name': 'X-User-ID', 'required': False},
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(TEMP_DIR, f"strict_{name}_{os.getpid()}.db")
                }
            }
        },
    }


@pytest_asyncio.fixture
async def auth_service(request):
    config = _get_test_config(request.node.name)
    database = SQLiteService(config)
    await database.initialize()
    service = AuthService(config, database)
    await service.initialize()
    yield service
    await service.close()


def _build_app(config, auth_service_instance, api_key_service=None, adapter_config=None):
    app = FastAPI()
    configurator = RouteConfigurator({}, logging.getLogger(__name__))
    get_api_key = configurator._create_api_key_validator()
    get_user_id = configurator._create_user_id_extractor()

    app.state.config = config
    app.state.auth_service = auth_service_instance
    app.state.api_key_service = api_key_service

    class FakeAdapterManager:
        def get_adapter_config(self, name):
            return adapter_config

    app.state.adapter_manager = FakeAdapterManager()

    @app.get("/v1/probe")
    async def probe(request: Request, key_info=None):
        adapter_name, system_prompt_id = await get_api_key(request)
        user_id = await get_user_id(request)
        return {"adapter": adapter_name, "user_id": user_id}

    return app


# ---------------------------------------------------------------------------
# The primary security assertion: strict mode is what makes the blacklist
# hold against a caller that omits the bearer token.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blacklisted_user_blocked_only_when_strict_mode_on(auth_service):
    await auth_service.create_user("victim", "password123", role="user")
    ok, token, info = await auth_service.authenticate_user("victim", "password123")
    assert ok is True
    await auth_service.blacklist.add_rule("victim", "username")

    api_key_service = FakeApiKeyService()

    # Off: the blacklisted user's key-only request (no bearer token) still succeeds.
    app_off = _build_app(_get_test_config("off", strict=False), auth_service, api_key_service)
    client_off = TestClient(app_off)
    resp_off = client_off.get("/v1/probe", headers={"X-API-Key": VALID_KEY})
    assert resp_off.status_code == 200

    # On: the same request is rejected.
    app_on = _build_app(_get_test_config("on", strict=True), auth_service, api_key_service)
    client_on = TestClient(app_on, raise_server_exceptions=False)
    resp_on = client_on.get("/v1/probe", headers={"X-API-Key": VALID_KEY})
    assert resp_on.status_code == 401
    assert resp_on.headers.get("www-authenticate") == 'Bearer realm="orbit"'


@pytest.mark.asyncio
async def test_blacklisted_user_with_bearer_token_gets_generic_401(auth_service):
    """Even presenting the (now-invalid) bearer token yields 401 - and the body
    must be indistinguishable from an outright invalid token (no blacklist oracle)."""
    await auth_service.create_user("victim", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is True
    await auth_service.blacklist.add_rule("victim", "username")

    config = _get_test_config("bearer401", strict=True)
    app = _build_app(config, auth_service, FakeApiKeyService())
    client = TestClient(app, raise_server_exceptions=False)

    resp_blacklisted = client.get(
        "/v1/probe",
        headers={"X-API-Key": VALID_KEY, "Authorization": f"Bearer {token}"},
    )
    resp_bad_token = client.get(
        "/v1/probe",
        headers={"X-API-Key": VALID_KEY, "Authorization": "Bearer not-a-real-token"},
    )
    assert resp_blacklisted.status_code == 401
    assert resp_bad_token.status_code == 401
    assert resp_blacklisted.json() == resp_bad_token.json()


@pytest.mark.asyncio
async def test_valid_authenticated_user_passes_strict_mode(auth_service):
    await auth_service.create_user("gooduser", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("gooduser", "password123")
    assert ok is True

    config = _get_test_config("valid", strict=True)
    app = _build_app(config, auth_service, FakeApiKeyService())
    client = TestClient(app)

    resp = client.get(
        "/v1/probe",
        headers={"X-API-Key": VALID_KEY, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["adapter"] == "test-adapter"


# ---------------------------------------------------------------------------
# Bearer clash: in strict mode, Authorization: Bearer is never an API key.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strict_mode_rejects_key_sent_only_as_bearer(auth_service):
    config = _get_test_config("bearerclash", strict=True)
    app = _build_app(config, auth_service, FakeApiKeyService())
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/v1/probe", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_non_strict_mode_still_accepts_key_as_bearer(auth_service):
    config = _get_test_config("bearercompat", strict=False)
    app = _build_app(config, auth_service, FakeApiKeyService())
    client = TestClient(app)

    resp = client.get("/v1/probe", headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# X-User-ID is ignored once strict mode is on.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strict_mode_ignores_x_user_id_header(auth_service):
    await auth_service.create_user("realuser", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("realuser", "password123")
    assert ok is True

    config = _get_test_config("xuserid", strict=True)
    app = _build_app(config, auth_service, FakeApiKeyService())
    client = TestClient(app)

    resp = client.get(
        "/v1/probe",
        headers={
            "X-API-Key": VALID_KEY,
            "Authorization": f"Bearer {token}",
            "X-User-ID": "someone-else",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] != "someone-else"


@pytest.mark.asyncio
async def test_non_strict_mode_still_honors_x_user_id_header(auth_service):
    config = _get_test_config("xuseridoff", strict=False)
    app = _build_app(config, auth_service, FakeApiKeyService())
    client = TestClient(app)

    resp = client.get(
        "/v1/probe",
        headers={"X-API-Key": VALID_KEY, "X-User-ID": "anonymous-caller"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "anonymous-caller"


# ---------------------------------------------------------------------------
# Caching: validate_token should run once per request, not once per dependency.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_token_called_once_per_request(auth_service):
    await auth_service.create_user("cacheduser", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("cacheduser", "password123")
    assert ok is True

    counting = CountingAuthService(auth_service)
    config = _get_test_config("caching", strict=True)
    app = _build_app(config, counting, FakeApiKeyService())
    client = TestClient(app)

    resp = client.get(
        "/v1/probe",
        headers={"X-API-Key": VALID_KEY, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert counting.validate_token_calls == 1


@pytest.mark.asyncio
async def test_validate_token_not_called_when_anonymous_and_not_strict(auth_service):
    counting = CountingAuthService(auth_service)
    config = _get_test_config("anon", strict=False)
    app = _build_app(config, counting, FakeApiKeyService())
    client = TestClient(app)

    resp = client.get("/v1/probe", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    # No Authorization header at all, so validate_token is never invoked.
    assert counting.validate_token_calls == 0


# ---------------------------------------------------------------------------
# Per-adapter override.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adapter_override_can_require_auth_when_global_off(auth_service):
    config = _get_test_config("adapteron", strict=False)
    adapter_config = {"capabilities": {"requires_authenticated_user": True}}
    app = _build_app(config, auth_service, FakeApiKeyService(), adapter_config=adapter_config)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/v1/probe", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_adapter_override_can_exempt_from_global_on(auth_service):
    config = _get_test_config("adapteroff", strict=True)
    adapter_config = {"capabilities": {"requires_authenticated_user": False}}
    app = _build_app(config, auth_service, FakeApiKeyService(), adapter_config=adapter_config)
    client = TestClient(app)

    resp = client.get("/v1/probe", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Fail-closed bypass lanes.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_api_key_service_fails_closed_under_strict_mode(auth_service):
    config = _get_test_config("noservice", strict=True)
    config['api_keys']['enabled'] = False
    app = _build_app(config, auth_service, api_key_service=None)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/v1/probe")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_api_key_service_still_bypasses_when_not_strict(auth_service):
    config = _get_test_config("noservicecompat", strict=False)
    config['api_keys']['enabled'] = False
    app = _build_app(config, auth_service, api_key_service=None)
    client = TestClient(app)

    resp = client.get("/v1/probe")
    assert resp.status_code == 200
    assert resp.json()["adapter"] == "default"


@pytest.mark.asyncio
async def test_health_reachable_without_credentials_under_strict_mode(auth_service):
    config = _get_test_config("health", strict=True)
    app = FastAPI()
    configurator = RouteConfigurator({}, logging.getLogger(__name__))
    get_api_key = configurator._create_api_key_validator()
    app.state.config = config
    app.state.auth_service = auth_service
    app.state.api_key_service = FakeApiKeyService()

    @app.get("/health")
    async def health(request: Request):
        adapter_name, _ = await get_api_key(request)
        return {"adapter": adapter_name}

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
