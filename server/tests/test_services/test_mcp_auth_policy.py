"""
Tests for services.mcp_auth_policy.apply_mcp_auth_policy.

The /mcp mount is decided once at InferenceServer construction time (see
inference_server.py) and cannot be re-evaluated automatically. If an admin
hot-reloads an adapter to add capabilities.requires_authenticated_user: true
(or flips auth.require_authenticated_user) after that, apply_mcp_auth_policy
is the mechanism that pulls the mount so it isn't left reachable with no
identity check.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from services.mcp_auth_policy import apply_mcp_auth_policy  # noqa: E402


def _mounted_app(path="/mcp"):
    """A tiny FastAPI app standing in for InferenceServer's real /mcp mount."""
    app = FastAPI()

    sub_app = FastAPI()

    @sub_app.get("/ping")
    async def ping():
        return {"ok": True}

    app.mount(path, sub_app)
    mount_route = next(r for r in app.router.routes if isinstance(r, Mount) and r.path == path)

    app.state._fastapi_app = app
    app.state.mcp_mount_route = mount_route
    return app


@pytest.mark.unit
def test_removes_mount_when_global_flag_now_true():
    app = _mounted_app()
    client = TestClient(app)
    assert client.get("/mcp/ping").status_code == 200

    apply_mcp_auth_policy(app.state, {"auth": {"require_authenticated_user": True}})

    assert app.state.mcp_mount_route is None
    assert client.get("/mcp/ping").status_code == 404


@pytest.mark.unit
def test_removes_mount_when_adapter_now_requires_auth():
    app = _mounted_app()
    client = TestClient(app)
    assert client.get("/mcp/ping").status_code == 200

    apply_mcp_auth_policy(app.state, {
        "auth": {"require_authenticated_user": False},
        "adapters": [
            {"name": "public-adapter", "capabilities": {}},
            {"name": "sensitive-adapter", "capabilities": {"requires_authenticated_user": True}},
        ],
    })

    assert app.state.mcp_mount_route is None
    assert client.get("/mcp/ping").status_code == 404


@pytest.mark.unit
def test_removes_mount_for_string_valued_adapter_override():
    """capabilities.requires_authenticated_user: ${REQUIRE_USER} arrives as a
    string after env substitution - must be recognized the same as a real bool."""
    app = _mounted_app()
    client = TestClient(app)

    apply_mcp_auth_policy(app.state, {
        "auth": {"require_authenticated_user": False},
        "adapters": [{"name": "sensitive-adapter", "capabilities": {"requires_authenticated_user": "true"}}],
    })

    assert app.state.mcp_mount_route is None
    assert client.get("/mcp/ping").status_code == 404


@pytest.mark.unit
def test_leaves_mount_alone_for_string_false_adapter_override():
    """The env-substituted "false" string must not be mistaken for a truthy
    override (a bare bool("false") cast would be True and wrongly disable MCP)."""
    app = _mounted_app()
    client = TestClient(app)

    apply_mcp_auth_policy(app.state, {
        "auth": {"require_authenticated_user": False},
        "adapters": [{"name": "adapter", "capabilities": {"requires_authenticated_user": "false"}}],
    })

    assert app.state.mcp_mount_route is not None
    assert client.get("/mcp/ping").status_code == 200


@pytest.mark.unit
def test_leaves_mount_alone_when_nothing_requires_auth():
    app = _mounted_app()
    client = TestClient(app)

    apply_mcp_auth_policy(app.state, {
        "auth": {"require_authenticated_user": False},
        "adapters": [{"name": "public-adapter", "capabilities": {}}],
    })

    assert app.state.mcp_mount_route is not None
    assert client.get("/mcp/ping").status_code == 200


@pytest.mark.unit
def test_noop_when_already_disabled():
    """mcp_mount_route is None from the start (never mounted, or a prior call
    already disabled it) - nothing to remove, and no error either way."""
    app_state = SimpleNamespace(mcp_mount_route=None, _fastapi_app=None)
    apply_mcp_auth_policy(app_state, {"auth": {"require_authenticated_user": True}})
    assert app_state.mcp_mount_route is None


@pytest.mark.unit
def test_warns_but_does_not_crash_without_app_reference():
    """If _fastapi_app wasn't stashed for some reason, there is no route list
    to mutate - log and move on rather than raising into a reload endpoint."""
    mount_route = object()
    app_state = SimpleNamespace(mcp_mount_route=mount_route, _fastapi_app=None)
    apply_mcp_auth_policy(app_state, {"auth": {"require_authenticated_user": True}})
    assert app_state.mcp_mount_route is mount_route


@pytest.mark.unit
def test_noop_when_config_is_none_or_empty():
    app = _mounted_app()
    apply_mcp_auth_policy(app.state, None)
    assert app.state.mcp_mount_route is not None
    apply_mcp_auth_policy(app.state, {})
    assert app.state.mcp_mount_route is not None
