"""
Tests for GET /admin/observability/usage: permission gating (reuses the
existing audit.read dependency), param validation, response shape, and the
graceful-zeros path when aggregation is unavailable.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import admin as admin_routes
from routes import auth_dependencies
from auth.rbac import permissions_for_roles


def _user_info(roles):
    return {
        "id": "u1",
        "username": "u1",
        "email": None,
        "role": roles[0],
        "roles": roles,
        "permissions": sorted(permissions_for_roles(roles)),
        "active": True,
    }


class FakeAuditService:
    def __init__(self, inference_events_enabled=True, aggregate_result=None):
        self.inference_events_enabled = inference_events_enabled
        self._aggregate_result = aggregate_result or {
            "totals": {
                "requests": 5, "prompt_tokens": 500, "completion_tokens": 100,
                "total_tokens": 600, "cost_usd": 0.05,
                "unpriced_requests": 1, "unreported_requests": 0,
            },
            "series": [{"bucket": "2026-01-01", "requests": 5, "prompt_tokens": 500,
                        "completion_tokens": 100, "total_tokens": 600, "cost_usd": 0.05}],
            "groups": [{"key": "gpt-4o-mini", "requests": 5, "total_tokens": 600,
                        "cost_usd": 0.05, "unpriced": False}],
        }
        self.last_call_kwargs = None

    async def aggregate_usage(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self._aggregate_result


class FakePricingService:
    updated = "2026-01-01"
    _stale_after_days = 120


def _build_app(roles, audit_service=None, pricing_service=None):
    app = FastAPI()
    app.include_router(admin_routes.admin_router)
    app.state.audit_service = audit_service
    app.state.pricing_service = pricing_service

    async def fake_user():
        return _user_info(roles)

    async def fake_optional_user():
        return _user_info(roles)

    app.dependency_overrides[auth_dependencies.get_current_user] = fake_user
    app.dependency_overrides[auth_dependencies.get_optional_user] = fake_optional_user
    return app


@pytest.mark.parametrize(
    "roles,expected_status",
    [
        (["admin"], 200),
        (["auditor"], 200),
        (["operator"], 401),
        (["analyst"], 401),
        (["user"], 401),
    ],
)
def test_observability_usage_requires_audit_read(roles, expected_status):
    app = _build_app(roles, audit_service=FakeAuditService())
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage")
    assert resp.status_code == expected_status


def test_observability_usage_denies_unauthenticated():
    app = _build_app(["admin"], audit_service=FakeAuditService())

    async def no_user():
        return None

    app.dependency_overrides[auth_dependencies.get_current_user] = no_user
    app.dependency_overrides[auth_dependencies.get_optional_user] = no_user
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage")
    assert resp.status_code == 401


def test_observability_usage_response_shape():
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service, pricing_service=FakePricingService())
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?days=7&bucket=day&group_by=model")

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"window", "totals", "series", "groups", "pricing"}
    assert data["window"]["days"] == 7
    assert data["window"]["bucket"] == "day"
    assert data["totals"]["requests"] == 5
    assert data["totals"]["cost_usd"] == pytest.approx(0.05)
    assert data["totals"]["unpriced_requests"] == 1
    assert data["groups"][0]["key"] == "gpt-4o-mini"
    assert data["pricing"]["updated"] == "2026-01-01"

    # Verify the filters/params were forwarded to the aggregation call.
    assert audit_service.last_call_kwargs["bucket"] == "day"
    assert audit_service.last_call_kwargs["group_by"] == "model"


def test_observability_usage_filters_and_groups_by_call_type():
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service)
    with TestClient(app) as client:
        resp = client.get(
            "/admin/observability/usage?group_by=call_type&call_type=embedding"
        )

    assert resp.status_code == 200
    assert audit_service.last_call_kwargs["group_by"] == "call_type"
    assert audit_service.last_call_kwargs["filters"] == {"call_type": "embedding"}


def test_observability_usage_groups_by_api_key():
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    assert audit_service.last_call_kwargs["group_by"] == "api_key"


def test_observability_usage_rejects_invalid_group_by():
    app = _build_app(["admin"], audit_service=FakeAuditService())
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key_value")
    assert resp.status_code == 422


def test_observability_usage_rejects_invalid_bucket():
    app = _build_app(["admin"], audit_service=FakeAuditService())
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?bucket=week")
    assert resp.status_code == 422


def test_observability_usage_rejects_days_out_of_range():
    app = _build_app(["admin"], audit_service=FakeAuditService())
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?days=0")
    assert resp.status_code == 422

    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?days=9999")
    assert resp.status_code == 422


def test_observability_usage_503_when_inference_audit_disabled():
    app = _build_app(["admin"], audit_service=FakeAuditService(inference_events_enabled=False))
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage")
    assert resp.status_code == 503


def test_observability_usage_503_when_no_audit_service():
    app = _build_app(["admin"], audit_service=None)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage")
    assert resp.status_code == 503


def test_observability_usage_graceful_zeros_when_aggregation_unimplemented():
    """AuditService.aggregate_usage already swallows NotImplementedError into a
    zeroed skeleton (tested in test_audit_service.py); this confirms the route
    just passes that skeleton through as a 200, not a 500."""
    empty_skeleton = {
        "totals": {
            "requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "cost_usd": 0.0, "unpriced_requests": 0, "unreported_requests": 0,
        },
        "series": [],
        "groups": [],
    }
    audit_service = FakeAuditService(aggregate_result=empty_skeleton)
    app = _build_app(["admin"], audit_service=audit_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["requests"] == 0
    assert data["series"] == []
