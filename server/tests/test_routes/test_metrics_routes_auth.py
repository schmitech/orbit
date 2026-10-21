"""Metrics endpoints require authentication with the metrics.read permission."""

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.metrics_routes import create_metrics_router


def _build_app():
    app = FastAPI()
    app.include_router(create_metrics_router())

    metrics_service = MagicMock()
    metrics_service.is_enabled.return_value = True
    metrics_service.is_prometheus_enabled.return_value = True
    metrics_service.get_prometheus_metrics.return_value = "# metrics"
    metrics_service.get_dashboard_metrics.return_value = {"ok": True}
    app.state.metrics_service = metrics_service

    auth_service = MagicMock()
    auth_service._initialized = True
    auth_service.validate_token = AsyncMock(return_value=(False, None))
    auth_service.verify_credentials = AsyncMock(return_value=(False, None))
    app.state.auth_service = auth_service

    return app, auth_service


@pytest.mark.parametrize("path", ["/metrics", "/metrics/json"])
def test_metrics_requires_auth(path):
    app, _ = _build_app()
    response = TestClient(app).get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/metrics", "/metrics/json"])
def test_metrics_allows_valid_cookie_session(path):
    app, auth_service = _build_app()
    auth_service.validate_token = AsyncMock(
        return_value=(True, {"permissions": ["metrics.read"]})
    )
    response = TestClient(app, cookies={"dashboard_token": "tok"}).get(path)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/metrics", "/metrics/json"])
def test_metrics_allows_basic_admin_credentials(path):
    app, auth_service = _build_app()
    auth_service.verify_credentials = AsyncMock(
        return_value=(True, {"permissions": ["metrics.read"]})
    )
    creds = base64.b64encode(b"admin:password").decode()
    response = TestClient(app).get(path, headers={"Authorization": f"Basic {creds}"})
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/metrics", "/metrics/json"])
def test_metrics_rejects_cookie_without_permission(path):
    app, auth_service = _build_app()
    auth_service.validate_token = AsyncMock(return_value=(True, {"permissions": []}))
    response = TestClient(app, cookies={"dashboard_token": "tok"}).get(path)
    assert response.status_code == 401
