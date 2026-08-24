"""Tests for the intent-adapter observability endpoints added alongside
production metrics: GET /admin/adapters/{name}/misses and
POST /admin/adapters/{name}/feedback (see docs/template-diagnostics.md).

Both operate purely on the in-memory store in
server/services/template_misses.py — no adapter_manager or config wiring
needed, unlike test-query.

    venv/bin/python -m pytest server/tests/test_routes/test_admin_adapter_misses.py
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.rbac import permissions_for_roles
from routes import admin as admin_routes
from routes import auth_dependencies
from services import template_misses


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


def _build_app(roles=("admin",)):
    app = FastAPI()
    app.include_router(admin_routes.admin_router)

    async def fake_user():
        return _user_info(list(roles))

    app.dependency_overrides[auth_dependencies.get_current_user] = fake_user
    app.dependency_overrides[auth_dependencies.get_optional_user] = fake_user
    return app


@pytest.fixture(autouse=True)
def _reset_store():
    template_misses._misses.clear()
    template_misses._feedback.clear()
    template_misses._next_id = 1
    yield
    template_misses._misses.clear()
    template_misses._feedback.clear()
    template_misses._next_id = 1


def test_get_misses_returns_empty_list_when_none_recorded():
    with TestClient(_build_app()) as client:
        resp = client.get("/admin/adapters/intent-sql-postgres/misses")

    assert resp.status_code == 200
    body = resp.json()
    assert body["adapter"] == "intent-sql-postgres"
    assert body["misses"] == []


def test_get_misses_returns_recorded_misses_for_this_adapter_only():
    template_misses.record_miss(
        adapter="intent-sql-postgres",
        query="what's the weather in Paris?",
        reason="below_threshold",
        candidates=[{"template_id": "orders_by_date_range", "similarity": 0.18}],
        threshold=0.4,
    )
    template_misses.record_miss(
        adapter="some-other-adapter", query="unrelated", reason="no_match", candidates=[], threshold=0.4,
    )

    with TestClient(_build_app()) as client:
        resp = client.get("/admin/adapters/intent-sql-postgres/misses")

    assert resp.status_code == 200
    misses = resp.json()["misses"]
    assert len(misses) == 1
    assert misses[0]["query"] == "what's the weather in Paris?"
    assert misses[0]["reason"] == "below_threshold"


def test_get_misses_respects_limit_query_param():
    for i in range(5):
        template_misses.record_miss(
            adapter="intent-sql-postgres", query=f"q{i}", reason="no_match", candidates=[], threshold=0.4,
        )

    with TestClient(_build_app()) as client:
        resp = client.get("/admin/adapters/intent-sql-postgres/misses?limit=2")

    assert len(resp.json()["misses"]) == 2


def test_get_misses_requires_admin_permission_or_api_key():
    with TestClient(_build_app(roles=("user",))) as client:
        resp = client.get("/admin/adapters/intent-sql-postgres/misses")

    assert resp.status_code == 401


def test_post_feedback_records_and_returns_status():
    with TestClient(_build_app()) as client:
        resp = client.post(
            "/admin/adapters/intent-sql-postgres/feedback",
            json={
                "verdict": "incorrect",
                "request_id": "r1",
                "template_id": None,
                "expected_template_id": "orders_by_date_range",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "recorded"}

    feedback = template_misses.list_feedback(adapter="intent-sql-postgres")
    assert len(feedback) == 1
    assert feedback[0]["verdict"] == "incorrect"
    assert feedback[0]["expected_template_id"] == "orders_by_date_range"


def test_post_feedback_requires_only_verdict():
    with TestClient(_build_app()) as client:
        resp = client.post(
            "/admin/adapters/intent-sql-postgres/feedback",
            json={"verdict": "correct"},
        )

    assert resp.status_code == 200
    feedback = template_misses.list_feedback(adapter="intent-sql-postgres")
    assert feedback[0]["verdict"] == "correct"
    assert feedback[0]["request_id"] is None
    assert feedback[0]["expected_template_id"] is None


def test_post_feedback_missing_verdict_is_rejected():
    with TestClient(_build_app()) as client:
        resp = client.post("/admin/adapters/intent-sql-postgres/feedback", json={})

    assert resp.status_code == 422


def test_post_feedback_requires_admin_permission():
    with TestClient(_build_app(roles=("user",))) as client:
        resp = client.post(
            "/admin/adapters/intent-sql-postgres/feedback",
            json={"verdict": "correct"},
        )

    assert resp.status_code in (401, 403)
