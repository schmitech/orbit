"""
`_include_admin_routes` always includes the core routers (admin, discovery,
auth, health) and best-effort includes the optional ones (metrics, admin
panel, file, voice, A2A) via a declarative table — a failure to import or
construct any one optional router must not crash app startup or block the
others.

Route presence is asserted via real requests rather than introspecting
`app.routes`/`app.openapi()`, since FastAPI's included-router wrapper type
does not expose a stable `.path` attribute across versions.
"""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.routes_configurator import RouteConfigurator


def _configurator():
    return RouteConfigurator({}, logging.getLogger(__name__))


def _registered(client, method, path):
    """True if the route exists at all (any status other than 404)."""
    return client.request(method, path).status_code != 404


def test_all_optional_routers_register_when_healthy():
    app = FastAPI()
    app.state.config = {}  # required by auth/file/voice dependencies to run at all
    _configurator()._include_admin_routes(app)
    client = TestClient(app)

    assert _registered(client, "GET", "/.well-known/agent.json"), "a2a router"
    assert _registered(client, "GET", "/metrics"), "metrics router"
    assert _registered(client, "GET", "/admin/login"), "admin panel router"
    assert _registered(client, "GET", "/api/files"), "file router"
    assert _registered(client, "GET", "/voice/status"), "voice router"


def test_failing_optional_router_does_not_crash_or_block_others(monkeypatch, caplog):
    def boom():
        raise RuntimeError("simulated construction failure")

    monkeypatch.setattr("routes.metrics_routes.create_metrics_router", boom)

    app = FastAPI()
    with caplog.at_level(logging.WARNING):
        _configurator()._include_admin_routes(app)  # must not raise

    client = TestClient(app)
    # The broken router's routes are absent...
    assert not _registered(client, "GET", "/metrics")
    # ...but a later table entry still registered.
    assert _registered(client, "GET", "/.well-known/agent.json")
    assert any("metrics" in record.message.lower() for record in caplog.records)


def test_failing_import_does_not_crash_or_block_others(monkeypatch, caplog):
    real_import = __import__

    def blocked_import(name, *args, **kwargs):
        if name == "routes.voice_routes":
            raise ImportError("simulated missing dependency for routes.voice_routes")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked_import)

    app = FastAPI()
    with caplog.at_level(logging.WARNING):
        _configurator()._include_admin_routes(app)

    client = TestClient(app)
    assert _registered(client, "GET", "/.well-known/agent.json")
    assert any("voice" in record.message.lower() for record in caplog.records)


def test_required_routers_always_present_even_if_optional_ones_fail(monkeypatch):
    monkeypatch.setattr(
        "routes.metrics_routes.create_metrics_router",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "routes.a2a_routes.create_a2a_router",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    app = FastAPI()
    _configurator()._include_admin_routes(app)

    client = TestClient(app)
    # /health is a required, always-registered core router.
    assert _registered(client, "GET", "/health")
    # The two broken optional routers must not be reachable.
    assert not _registered(client, "GET", "/metrics")
    assert not _registered(client, "GET", "/.well-known/agent.json")


def test_module_level_router_instance_is_included_directly():
    """`voice_routes.router` is a module-level APIRouter, not a factory — the
    loop must include it as-is rather than calling it."""
    from fastapi import APIRouter
    from routes import voice_routes

    assert isinstance(voice_routes.router, APIRouter)

    app = FastAPI()
    app.state.config = {}
    _configurator()._include_admin_routes(app)

    client = TestClient(app)
    assert _registered(client, "GET", "/voice/status"), "voice router must actually be mounted"
