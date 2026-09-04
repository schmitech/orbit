"""
Admin IP Allowlist Tests
========================

Covers CIDR matching/CRUD on AdminIpAllowlistService (against a real SQLite
backend) and request gating in AdminIpAllowlistMiddleware.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from middleware.admin_ip_allowlist_middleware import AdminIpAllowlistMiddleware
from services.admin_ip_allowlist_service import AdminIpRuleError, normalize_cidr
from services.auth_service import AuthService
from services.sqlite_service import SQLiteService

TEMP_DIR = None


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def get_test_config(name, **admin_ip_overrides):
    return {
        'general': {},
        'auth': {
            'default_admin_username': 'admin',
            'default_admin_password': 'admin12345',
            'admin_ip_allowlist': {
                'enabled': True,
                'mode': 'allowlist',
                'default_ranges': [],
                'cache_ttl': 0,
                **admin_ip_overrides,
            },
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(TEMP_DIR, f"admin_ip_{name}_{os.getpid()}.db")
                }
            }
        },
    }


@pytest_asyncio.fixture
async def auth_service(request):
    config = get_test_config(request.node.name)
    database = SQLiteService(config)
    await database.initialize()
    service = AuthService(config, database)
    await service.initialize()
    yield service
    await service.close()


# ---------------------------------------------------------------------------
# CIDR normalization
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalize_cidr_accepts_bare_ip_and_range():
    assert normalize_cidr("10.0.0.1") == "10.0.0.1/32"
    assert normalize_cidr("10.0.0.0/8") == "10.0.0.0/8"


@pytest.mark.unit
def test_normalize_cidr_rejects_garbage():
    with pytest.raises(AdminIpRuleError):
        normalize_cidr("not-an-ip")
    with pytest.raises(AdminIpRuleError):
        normalize_cidr("")


# ---------------------------------------------------------------------------
# Service evaluation
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_disabled_allows_everything(auth_service):
    auth_service.admin_ip_allowlist.enabled = False
    assert await auth_service.admin_ip_allowlist.is_allowed("8.8.8.8") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_mode_allows_everything(auth_service):
    auth_service.admin_ip_allowlist.mode = "open"
    assert await auth_service.admin_ip_allowlist.is_allowed("8.8.8.8") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforcing_denies_ip_outside_ranges(auth_service):
    service = auth_service.admin_ip_allowlist
    assert service.enforcing is True
    assert await service.is_allowed("8.8.8.8") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforcing_allows_ip_in_default_ranges(auth_service):
    service = auth_service.admin_ip_allowlist
    service.default_networks = [__import__("ipaddress").ip_network("10.0.0.0/8")]
    assert await service.is_allowed("10.1.2.3") is True
    assert await service.is_allowed("11.1.2.3") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enforcing_allows_ip_covered_by_db_rule(auth_service):
    service = auth_service.admin_ip_allowlist
    await service.add_rule(cidr="203.0.113.4/32", reason="office", created_by="admin")
    assert await service.is_allowed("203.0.113.4") is True
    assert await service.is_allowed("203.0.113.5") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_rule_rejected(auth_service):
    service = auth_service.admin_ip_allowlist
    await service.add_rule(cidr="203.0.113.4/32", created_by="admin")
    with pytest.raises(AdminIpRuleError):
        await service.add_rule(cidr="203.0.113.4/32", created_by="admin")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_rule_removes_coverage(auth_service):
    service = auth_service.admin_ip_allowlist
    rule = await service.add_rule(cidr="203.0.113.4/32", created_by="admin")
    assert await service.is_allowed("203.0.113.4") is True

    assert await service.delete_rule(str(rule["_id"])) is True
    assert await service.is_allowed("203.0.113.4") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_allowed_under_simulates_pending_rule_set(auth_service):
    service = auth_service.admin_ip_allowlist
    # Simulates removing the only rule covering this IP, without writing anything.
    assert service.allowed_under([], "203.0.113.4") is False
    assert service.allowed_under(["203.0.113.4/32"], "203.0.113.4") is True


# ---------------------------------------------------------------------------
# Middleware gating
# ---------------------------------------------------------------------------

def _make_app(auth_service_stub):
    app = FastAPI()
    app.state.auth_service = auth_service_stub
    app.state.audit_service = None
    app.add_middleware(AdminIpAllowlistMiddleware, config={})

    @app.get("/admin")
    def admin_root():
        return {"ok": True}

    @app.get("/auth/users")
    def list_users():
        return {"ok": True}

    @app.get("/v1/chat")
    def chat():
        return {"ok": True}

    return app


@pytest.mark.unit
def test_middleware_denies_gated_path_from_disallowed_ip():
    stub_service = Mock()
    stub_service.enforcing = True
    stub_service.is_allowed = AsyncMock(return_value=False)
    auth_service_stub = Mock(admin_ip_allowlist=stub_service)

    app = _make_app(auth_service_stub)
    client = TestClient(app, client=("8.8.8.8", 12345))

    response = client.get("/admin")
    assert response.status_code == 403

    response = client.get("/auth/users")
    assert response.status_code == 403


@pytest.mark.unit
def test_middleware_gates_reset_password_route():
    """POST /auth/reset-password is admin-scoped (checks users.manage
    internally) and must not bypass the IP gate the way an ungated route
    would - it can take over another user's account."""
    stub_service = Mock()
    stub_service.enforcing = True
    stub_service.is_allowed = AsyncMock(return_value=False)
    auth_service_stub = Mock(admin_ip_allowlist=stub_service)

    app = _make_app(auth_service_stub)

    @app.post("/auth/reset-password")
    def reset_password():
        return {"ok": True}

    client = TestClient(app, client=("8.8.8.8", 12345))
    response = client.post("/auth/reset-password")
    assert response.status_code == 403
    stub_service.is_allowed.assert_called_once()


@pytest.mark.unit
def test_middleware_allows_gated_path_from_allowed_ip():
    stub_service = Mock()
    stub_service.enforcing = True
    stub_service.is_allowed = AsyncMock(return_value=True)
    auth_service_stub = Mock(admin_ip_allowlist=stub_service)

    app = _make_app(auth_service_stub)
    client = TestClient(app, client=("203.0.113.4", 12345))

    response = client.get("/admin")
    assert response.status_code == 200


@pytest.mark.unit
def test_middleware_never_gates_unrelated_routes():
    stub_service = Mock()
    stub_service.enforcing = True
    stub_service.is_allowed = AsyncMock(return_value=False)
    auth_service_stub = Mock(admin_ip_allowlist=stub_service)

    app = _make_app(auth_service_stub)
    client = TestClient(app, client=("8.8.8.8", 12345))

    response = client.get("/v1/chat")
    assert response.status_code == 200
    stub_service.is_allowed.assert_not_called()


@pytest.mark.unit
def test_middleware_exempts_loopback_regardless_of_ranges():
    stub_service = Mock()
    stub_service.enforcing = True
    stub_service.is_allowed = AsyncMock(return_value=False)
    auth_service_stub = Mock(admin_ip_allowlist=stub_service)

    app = _make_app(auth_service_stub)
    client = TestClient(app, client=("127.0.0.1", 12345))

    response = client.get("/admin")
    assert response.status_code == 200
    stub_service.is_allowed.assert_not_called()


@pytest.mark.unit
def test_middleware_pass_through_when_not_enforcing():
    """mode: open (or enabled: false) preserves current behavior exactly."""
    stub_service = Mock()
    stub_service.enforcing = False
    stub_service.is_allowed = AsyncMock(return_value=False)
    auth_service_stub = Mock(admin_ip_allowlist=stub_service)

    app = _make_app(auth_service_stub)
    client = TestClient(app, client=("8.8.8.8", 12345))

    response = client.get("/admin")
    assert response.status_code == 200
