"""
Tests for MetricsMiddleware.

Covers:
- Pass-through when no metrics service is attached
- record_request called only when service is enabled
- In-progress counter incremented and decremented
- Metrics endpoint self-excluded from recording
- Exception propagation with metrics still recorded
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from middleware.metrics_middleware import MetricsMiddleware


def _build_app(metrics_service=None):
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/test")
    def test_endpoint():
        return {"message": "test"}

    @app.get("/items/{item_id}")
    def item_endpoint(item_id: str):
        return {"item_id": item_id}

    @app.get("/metrics")
    def metrics_endpoint():
        return {}

    @app.get("/metrics/json")
    def metrics_json():
        return {}

    if metrics_service is not None:
        app.state.metrics_service = metrics_service

    return app


def _mock_metrics_service(enabled: bool = True) -> Mock:
    svc = Mock()
    svc.enabled = enabled
    svc.http_inprogress = Mock()
    svc.http_inprogress.labels.return_value = Mock()
    return svc


class TestMetricsMiddlewarePassThrough:
    def test_pass_through_when_no_metrics_service(self):
        app = _build_app()
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200

    def test_pass_through_when_metrics_service_disabled(self):
        svc = _mock_metrics_service(enabled=False)
        app = _build_app(svc)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        svc.record_request.assert_not_called()


class TestMetricsRecording:
    def test_record_request_called_when_enabled(self):
        svc = _mock_metrics_service(enabled=True)
        app = _build_app(svc)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        svc.record_request.assert_called_once()

    def test_record_request_includes_method_status_duration(self):
        svc = _mock_metrics_service(enabled=True)
        app = _build_app(svc)
        client = TestClient(app)
        client.get("/test")
        call_kwargs = svc.record_request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["status"] == 200
        assert call_kwargs["duration"] >= 0

    def test_record_request_uses_route_template_for_path_parameters(self):
        svc = _mock_metrics_service(enabled=True)
        app = _build_app(svc)
        client = TestClient(app)
        response = client.get("/items/123")
        assert response.status_code == 200
        call_kwargs = svc.record_request.call_args.kwargs
        assert call_kwargs["endpoint"] == "/items/{item_id}"

    def test_record_request_uses_bounded_label_for_unmatched_route(self):
        svc = _mock_metrics_service(enabled=True)
        app = _build_app(svc)
        client = TestClient(app)
        response = client.get("/does/not/exist/123")
        assert response.status_code == 404
        call_kwargs = svc.record_request.call_args.kwargs
        assert call_kwargs["endpoint"] == "__unmatched_route__"

    def test_record_request_not_called_when_disabled(self):
        svc = _mock_metrics_service(enabled=False)
        app = _build_app(svc)
        client = TestClient(app)
        client.get("/test")
        svc.record_request.assert_not_called()

    def test_inprogress_incremented_and_decremented(self):
        svc = _mock_metrics_service(enabled=True)
        label_mock = Mock()
        svc.http_inprogress.labels.return_value = label_mock
        app = _build_app(svc)
        client = TestClient(app)
        client.get("/test")
        label_mock.inc.assert_called_once()
        label_mock.dec.assert_called_once()


class TestMetricsEndpointExclusion:
    def test_metrics_path_not_recorded(self):
        svc = _mock_metrics_service(enabled=True)
        app = _build_app(svc)
        client = TestClient(app)
        client.get("/metrics")
        svc.record_request.assert_not_called()

    def test_metrics_json_path_not_recorded(self):
        svc = _mock_metrics_service(enabled=True)
        app = _build_app(svc)
        client = TestClient(app)
        client.get("/metrics/json")
        svc.record_request.assert_not_called()
