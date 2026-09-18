"""
`_create_lazy_service_dependency` backs the health/thread/feedback/autocomplete
service dependencies: build once, cache on app.state, call initialize() when the
service exposes one, and never rebuild once cached.
"""

import logging

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from routes.routes_configurator import RouteConfigurator


def _configurator():
    return RouteConfigurator({}, logging.getLogger(__name__))


class FakeServiceWithInit:
    def __init__(self):
        self.initialized = False

    async def initialize(self):
        self.initialized = True


class FakeServiceWithoutInit:
    pass


def _build_app(build, attr_name="probe_service"):
    app = FastAPI()
    configurator = _configurator()
    get_service = configurator._create_lazy_service_dependency(attr_name, build)

    @app.get("/probe")
    async def probe(service=Depends(get_service)):
        return {"id": id(service)}

    return app, get_service


def test_builds_and_caches_on_app_state():
    build_calls = []

    async def build(request: Request):
        build_calls.append(1)
        return FakeServiceWithoutInit()

    app, _ = _build_app(build)
    client = TestClient(app)

    r1 = client.get("/probe")
    r2 = client.get("/probe")

    assert r1.status_code == 200
    assert r1.json() == r2.json(), "same cached instance must be returned across requests"
    assert len(build_calls) == 1, "build() must only run once, not per-request"


def test_calls_initialize_when_present():
    async def build(request: Request):
        return FakeServiceWithInit()

    app, _ = _build_app(build, attr_name="init_service")
    client = TestClient(app)
    client.get("/probe")

    assert app.state.init_service.initialized is True


def test_does_not_call_initialize_when_absent():
    async def build(request: Request):
        return FakeServiceWithoutInit()

    app, _ = _build_app(build, attr_name="no_init_service")
    client = TestClient(app)
    r = client.get("/probe")

    assert r.status_code == 200
    assert not hasattr(app.state.no_init_service, "initialize")


def test_preexisting_service_on_app_state_is_reused_without_rebuilding():
    build_calls = []

    async def build(request: Request):
        build_calls.append(1)
        return FakeServiceWithoutInit()

    app, _ = _build_app(build, attr_name="preset_service")
    preset = FakeServiceWithoutInit()
    app.state.preset_service = preset

    client = TestClient(app)
    r = client.get("/probe")

    assert r.status_code == 200
    assert r.json()["id"] == id(preset)
    assert build_calls == [], "build() must not run when the service is already on app.state"


@pytest.mark.parametrize("attr_name", ["health_service", "thread_service", "feedback_service", "autocomplete_service"])
def test_real_factories_are_wired_through_the_lazy_helper(attr_name):
    """Each concrete `_create_*_service_dependency` must delegate to
    `_create_lazy_service_dependency` with its own attr_name — not merely
    return a same-named closure of its own."""
    configurator = _configurator()

    calls = []
    sentinel_dependency = object()

    def fake_lazy_dependency(recorded_attr_name, build):
        calls.append(recorded_attr_name)
        return sentinel_dependency

    configurator._create_lazy_service_dependency = fake_lazy_dependency

    factory_method = getattr(configurator, f"_create_{attr_name}_dependency")
    dependency = factory_method()

    assert calls == [attr_name]
    assert dependency is sentinel_dependency
