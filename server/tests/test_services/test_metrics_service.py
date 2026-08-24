"""
Tests for MetricsService dashboard aggregation.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from prometheus_client import generate_latest

from services.metrics_service import (
    MetricsService,
    get_metrics_service_instance,
    set_metrics_service_instance,
)


def _metrics_text(service):
    return generate_latest(service.registry).decode("utf-8")


def test_dashboard_total_requests_is_lifetime_count():
    service = MetricsService({"monitoring": {"enabled": True}})

    for _ in range(1005):
        service.record_request("GET", "/test", 200, 0.01)

    dashboard_metrics = service.get_dashboard_metrics()

    assert len(service.request_timestamps) == 1000
    assert dashboard_metrics["requests"]["total"] == 1005


def test_dashboard_metrics_excludes_unmatched_route_label():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_request("GET", "__unmatched_route__", 404, 0.01)
    service.record_request("GET", "/v1/chat/completions", 200, 0.02)

    dashboard_metrics = service.get_dashboard_metrics()

    assert dashboard_metrics["requests"]["total"] == 1
    assert dashboard_metrics["endpoint_stats"] == [
        {
            "endpoint": "/v1/chat/completions",
            "method": "GET",
            "total_requests": 1,
            "avg_latency_ms": 20.0,
            "error_rate": 0.0,
        }
    ]


# --- Intent-template outcome metrics (Phase 4: production observability) ---

def test_record_intent_outcome_increments_counter_and_confidence_histogram():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_intent_outcome("intent-sql-postgres", "orders_above_amount", "executed", confidence=0.87)

    text = _metrics_text(service)
    assert 'orbit_intent_template_matches_total{adapter="intent-sql-postgres",outcome="executed",template_id="orders_above_amount"} 1.0' in text
    assert "orbit_intent_confidence_sum{adapter=\"intent-sql-postgres\"} 0.87" in text
    assert "orbit_intent_confidence_count{adapter=\"intent-sql-postgres\"} 1.0" in text


def test_record_intent_outcome_without_template_id_uses_none_label():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_intent_outcome("intent-sql-postgres", None, "below_threshold")

    text = _metrics_text(service)
    assert 'orbit_intent_template_matches_total{adapter="intent-sql-postgres",outcome="below_threshold",template_id="none"} 1.0' in text


def test_record_intent_outcome_without_confidence_does_not_touch_histogram():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_intent_outcome("intent-sql-postgres", None, "no_match")

    text = _metrics_text(service)
    assert 'orbit_intent_confidence_count{adapter="intent-sql-postgres"}' not in text


def test_record_intent_rows_returned_updates_histogram():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_intent_rows_returned("intent-sql-postgres", "orders_above_amount", 12)

    text = _metrics_text(service)
    assert 'orbit_intent_rows_returned_sum{adapter="intent-sql-postgres",template_id="orders_above_amount"} 12.0' in text


def test_record_intent_row_cap_applied_increments_counter():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_intent_row_cap_applied("intent-sql-postgres")
    service.record_intent_row_cap_applied("intent-sql-postgres")

    text = _metrics_text(service)
    assert 'orbit_intent_row_cap_applied_total{adapter="intent-sql-postgres"} 2.0' in text


def test_record_intent_guard_rejection_increments_counter_with_reason_label():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_intent_guard_rejection("intent-sql-postgres", reason="QueryGuardError")

    text = _metrics_text(service)
    assert 'orbit_intent_guard_rejections_total{adapter="intent-sql-postgres",reason="QueryGuardError"} 1.0' in text


def test_intent_metrics_are_noops_when_service_disabled():
    service = MetricsService({"monitoring": {"enabled": False}})

    # None of these should raise, even though no registry/metric objects exist.
    service.record_intent_outcome("a", "t", "executed", confidence=0.5)
    service.record_intent_rows_returned("a", "t", 5)
    service.record_intent_row_cap_applied("a")
    service.record_intent_guard_rejection("a", reason="x")


# --- Module-level singleton (retrievers have no access to app.state) ---

def test_singleton_starts_unset(monkeypatch):
    monkeypatch.setattr("services.metrics_service._instance", None)
    assert get_metrics_service_instance() is None


def test_set_and_get_metrics_service_instance(monkeypatch):
    monkeypatch.setattr("services.metrics_service._instance", None)
    service = MetricsService({"monitoring": {"enabled": True}})

    set_metrics_service_instance(service)
    assert get_metrics_service_instance() is service

    set_metrics_service_instance(None)
    assert get_metrics_service_instance() is None
