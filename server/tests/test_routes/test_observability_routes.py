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


class FakeDatabase:
    """Mimics the real backends' skip/limit paging so pagination bugs in the
    caller show up here rather than only against a live server."""

    def __init__(self, docs=None, raise_on_query=False):
        self._docs = docs or []
        self._raise_on_query = raise_on_query
        self.calls = []

    async def find_many(self, collection_name, query, limit=100, sort=None, skip=0):
        if self._raise_on_query:
            raise RuntimeError("database unavailable")
        self.calls.append({"limit": limit, "skip": skip})
        return self._docs[skip:skip + limit]


class FakeApiKeyService:
    """Mirrors the surface `_label_api_key_groups` reads: `.database.find_many`
    and `.collection_name`, backed by a plain list of api_keys documents."""

    def __init__(self, docs=None, raise_on_query=False):
        self.collection_name = "api_keys"
        self.database = FakeDatabase(docs, raise_on_query=raise_on_query)


def _build_app(roles, audit_service=None, pricing_service=None, api_key_service=None):
    app = FastAPI()
    app.include_router(admin_routes.admin_router)
    app.state.audit_service = audit_service
    app.state.pricing_service = pricing_service
    app.state.api_key_service = api_key_service

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


def test_observability_usage_filters_by_api_key():
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?api_key=...aaa111")

    assert resp.status_code == 200
    assert audit_service.last_call_kwargs["filters"] == {"api_key": "...aaa111"}


def test_observability_usage_api_key_filter_composes_with_other_filters():
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service)
    with TestClient(app) as client:
        resp = client.get(
            "/admin/observability/usage?api_key=...aaa111&provider=openai&call_type=embedding"
        )

    assert resp.status_code == 200
    assert audit_service.last_call_kwargs["filters"] == {
        "provider": "openai", "call_type": "embedding", "api_key": "...aaa111",
    }


def test_observability_usage_groups_by_api_key():
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    assert audit_service.last_call_kwargs["group_by"] == "api_key"


def test_observability_usage_api_key_groups_get_client_name_label():
    aggregate_result = {
        "totals": {"requests": 3, "prompt_tokens": 300, "completion_tokens": 60,
                    "total_tokens": 360, "cost_usd": 0.08,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [
            {"key": "...aaa111", "requests": 2, "total_tokens": 240, "cost_usd": 0.05},
            {"key": "...bbb222", "requests": 1, "total_tokens": 120, "cost_usd": 0.03},
        ],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    api_key_service = FakeApiKeyService(docs=[
        {"api_key": "sk-live-aaa111", "client_name": "Acme Corp", "active": True},
        {"api_key": "sk-live-bbb222", "client_name": "Globex", "active": True},
    ])
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    groups = {g["key"]: g for g in resp.json()["groups"]}
    assert groups["...aaa111"]["label"] == "Acme Corp"
    assert groups["...bbb222"]["label"] == "Globex"
    # The plaintext key must never appear anywhere in the response.
    assert "sk-live-aaa111" not in resp.text
    assert "sk-live-bbb222" not in resp.text


def test_observability_usage_api_key_label_falls_back_when_no_match():
    aggregate_result = {
        "totals": {"requests": 1, "prompt_tokens": 100, "completion_tokens": 20,
                    "total_tokens": 120, "cost_usd": 0.01,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [{"key": "...ccc333", "requests": 1, "total_tokens": 120, "cost_usd": 0.01}],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    # No active key matches this masked suffix (e.g. the key was deleted).
    api_key_service = FakeApiKeyService(docs=[
        {"api_key": "sk-live-aaa111", "client_name": "Acme Corp", "active": True},
    ])
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    group = resp.json()["groups"][0]
    assert group["key"] == "...ccc333"
    assert "label" not in group


def test_observability_usage_api_key_label_ambiguous_on_suffix_collision():
    aggregate_result = {
        "totals": {"requests": 2, "prompt_tokens": 200, "completion_tokens": 40,
                    "total_tokens": 240, "cost_usd": 0.02,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [{"key": "...aaa111", "requests": 2, "total_tokens": 240, "cost_usd": 0.02}],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    # Two distinct active keys share the same last-6-character suffix.
    api_key_service = FakeApiKeyService(docs=[
        {"api_key": "sk-live-1-aaa111", "client_name": "Acme Corp", "active": True},
        {"api_key": "sk-live-2-aaa111", "client_name": "Globex", "active": True},
    ])
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    group = resp.json()["groups"][0]
    assert group["label"] is None
    assert group["ambiguous"] is True


def test_observability_usage_api_key_label_ambiguous_even_with_same_client_name():
    """Two distinct active keys sharing a masked suffix must be flagged
    ambiguous even when they also share the same client_name — the collision
    is about the keys, not whether their names happen to differ."""
    aggregate_result = {
        "totals": {"requests": 2, "prompt_tokens": 200, "completion_tokens": 40,
                    "total_tokens": 240, "cost_usd": 0.02,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [{"key": "...aaa111", "requests": 2, "total_tokens": 240, "cost_usd": 0.02}],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    api_key_service = FakeApiKeyService(docs=[
        {"api_key": "sk-live-1-aaa111", "client_name": "Acme Corp", "active": True},
        {"api_key": "sk-live-2-aaa111", "client_name": "Acme Corp", "active": True},
    ])
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    group = resp.json()["groups"][0]
    assert group["label"] is None
    assert group["ambiguous"] is True


def test_observability_usage_api_key_label_paginates_past_first_page():
    """A deployment with more active keys than one page's `limit` must still
    resolve labels for keys beyond the first page."""
    aggregate_result = {
        "totals": {"requests": 1, "prompt_tokens": 100, "completion_tokens": 20,
                    "total_tokens": 120, "cost_usd": 0.01,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [{"key": "...zzz999", "requests": 1, "total_tokens": 120, "cost_usd": 0.01}],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    filler_docs = [
        {"api_key": f"sk-live-filler-{i:06d}", "client_name": f"Filler {i}", "active": True}
        for i in range(600)
    ]
    target_doc = {"api_key": "sk-live-target-zzz999", "client_name": "Last Page Corp", "active": True}
    api_key_service = FakeApiKeyService(docs=filler_docs + [target_doc])
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    group = resp.json()["groups"][0]
    assert group["label"] == "Last Page Corp"
    # 601 docs at 500/page requires 2 pages.
    assert len(api_key_service.database.calls) == 2


def test_observability_usage_api_key_label_skipped_when_service_unavailable():
    aggregate_result = {
        "totals": {"requests": 1, "prompt_tokens": 100, "completion_tokens": 20,
                    "total_tokens": 120, "cost_usd": 0.01,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [{"key": "...aaa111", "requests": 1, "total_tokens": 120, "cost_usd": 0.01}],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=None)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    assert "label" not in resp.json()["groups"][0]


def test_observability_usage_api_key_label_lookup_failure_is_non_fatal():
    aggregate_result = {
        "totals": {"requests": 1, "prompt_tokens": 100, "completion_tokens": 20,
                    "total_tokens": 120, "cost_usd": 0.01,
                    "unpriced_requests": 0, "unreported_requests": 0},
        "series": [],
        "groups": [{"key": "...aaa111", "requests": 1, "total_tokens": 120, "cost_usd": 0.01}],
    }
    audit_service = FakeAuditService(aggregate_result=aggregate_result)
    api_key_service = FakeApiKeyService(raise_on_query=True)
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=api_key")

    assert resp.status_code == 200
    assert "label" not in resp.json()["groups"][0]


def test_observability_usage_api_key_labeling_skipped_for_other_dimensions():
    """Labeling only applies to group_by=api_key — it must not run (and
    therefore not query the api_keys collection) for other dimensions."""
    api_key_service = FakeApiKeyService(raise_on_query=True)
    audit_service = FakeAuditService()
    app = _build_app(["admin"], audit_service=audit_service, api_key_service=api_key_service)
    with TestClient(app) as client:
        resp = client.get("/admin/observability/usage?group_by=model")
    assert resp.status_code == 200


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
