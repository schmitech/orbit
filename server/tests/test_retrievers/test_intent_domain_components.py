"""
Tests for record_intent_telemetry (server/retrievers/base/intent_domain_components.py) —
the single shared function every intent retriever variant (SQL, HTTP, Composite,
Firecrawl, Agent) calls to report a get_relevant_context() outcome to metrics
and the misses store.

    venv/bin/python -m pytest server/tests/test_retrievers/test_intent_domain_components.py
"""

from unittest.mock import MagicMock

import pytest

from retrievers.base.intent_domain_components import record_intent_telemetry
from services import template_misses
from services.metrics_service import MetricsService, set_metrics_service_instance


@pytest.fixture(autouse=True)
def _reset_state():
    template_misses._misses.clear()
    template_misses._feedback.clear()
    template_misses._next_id = 1
    set_metrics_service_instance(None)
    yield
    template_misses._misses.clear()
    template_misses._feedback.clear()
    template_misses._next_id = 1
    set_metrics_service_instance(None)


def _fake_retriever(adapter_name="intent-sql-postgres", confidence_threshold=0.4):
    retriever = MagicMock()
    retriever.audit_adapter_name = adapter_name
    retriever.confidence_threshold = confidence_threshold
    retriever.__class__.__name__ = "IntentSQLRetriever"
    return retriever


def test_empty_result_records_nothing():
    record_intent_telemetry(_fake_retriever(), "some query", [])
    assert template_misses.list_misses() == []


def test_executed_outcome_records_metrics_but_not_a_miss():
    service = MetricsService({"monitoring": {"enabled": True}})
    set_metrics_service_instance(service)

    result = [{
        "content": "ok",
        "metadata": {"source": "intent", "template_id": "orders_above_amount", "result_count": 12},
        "confidence": 0.87,
    }]
    record_intent_telemetry(_fake_retriever(), "show me orders above $500", result)

    assert template_misses.list_misses() == []
    from prometheus_client import generate_latest
    text = generate_latest(service.registry).decode("utf-8")
    assert 'outcome="executed"' in text
    assert 'orbit_intent_rows_returned_sum{adapter="intent-sql-postgres",template_id="orders_above_amount"} 12.0' in text


@pytest.mark.parametrize("error,expected_outcome", [
    ("no_matching_template", "no_match"),
    ("below_threshold", "below_threshold"),
    ("parameter_extraction_failed", "param_validation_failed"),
    ("datasource_unavailable", "datasource_unavailable"),
    ("adapter_not_found", "error"),
    ("cross_adapter_all_failed", "error"),
    ("some_unmapped_error", "error"),
])
def test_error_metadata_maps_to_expected_outcome(error, expected_outcome):
    service = MetricsService({"monitoring": {"enabled": True}})
    set_metrics_service_instance(service)

    result = [{"content": "x", "metadata": {"source": "intent", "error": error}, "confidence": 0.0}]
    record_intent_telemetry(_fake_retriever(), "query text", result)

    from prometheus_client import generate_latest
    text = generate_latest(service.registry).decode("utf-8")
    assert f'outcome="{expected_outcome}"' in text


def test_below_threshold_is_recorded_as_a_miss_not_param_validation_failed():
    # Regression: an all-below-threshold match used to fall through to the
    # same generic path as a real parameter-extraction failure, misleading
    # the Misses panel about why the query didn't answer.
    result = [{
        "content": "none met threshold",
        "metadata": {
            "source": "intent",
            "error": "below_threshold",
            "candidates": [{"template_id": "orders_by_date_range", "similarity": 0.18}],
        },
        "confidence": 0.0,
    }]
    record_intent_telemetry(_fake_retriever(confidence_threshold=0.4), "off topic query", result)

    misses = template_misses.list_misses()
    assert len(misses) == 1
    assert misses[0]["reason"] == "below_threshold"
    assert misses[0]["candidates"] == [{"template_id": "orders_by_date_range", "similarity": 0.18}]
    assert misses[0]["threshold"] == 0.4


def test_param_validation_failed_is_recorded_with_its_own_reason():
    result = [{
        "content": "couldn't extract",
        "metadata": {"source": "intent", "error": "parameter_extraction_failed", "candidates": []},
        "confidence": 0.0,
    }]
    record_intent_telemetry(_fake_retriever(), "query", result)

    misses = template_misses.list_misses()
    assert len(misses) == 1
    assert misses[0]["reason"] == "param_validation_failed"


def test_datasource_unavailable_is_not_recorded_as_a_miss():
    # Not a matching problem — the query would have worked, the datasource
    # just wasn't reachable. Shouldn't pollute the Misses panel.
    result = [{
        "content": "unavailable",
        "metadata": {"source": "intent", "error": "datasource_unavailable"},
        "confidence": 0.0,
    }]
    record_intent_telemetry(_fake_retriever(), "query", result)

    assert template_misses.list_misses() == []


def test_uses_class_name_when_audit_adapter_name_is_unset():
    service = MetricsService({"monitoring": {"enabled": True}})
    set_metrics_service_instance(service)

    retriever = _fake_retriever()
    retriever.audit_adapter_name = None
    retriever.__class__.__name__ = "IntentFirecrawlRetriever"

    result = [{"content": "x", "metadata": {"source": "firecrawl", "error": "no_matching_template"}, "confidence": 0.0}]
    record_intent_telemetry(retriever, "query", result)

    from prometheus_client import generate_latest
    text = generate_latest(service.registry).decode("utf-8")
    assert 'adapter="IntentFirecrawlRetriever"' in text


def test_missing_metrics_service_instance_does_not_raise():
    # get_metrics_service_instance() is None until service_factory wires one
    # up — record_intent_telemetry must still safely record the miss.
    result = [{"content": "x", "metadata": {"source": "intent", "error": "no_matching_template"}, "confidence": 0.0}]
    record_intent_telemetry(_fake_retriever(), "query", result)

    assert len(template_misses.list_misses()) == 1
