"""
Tests for the in-memory intent-template misses/feedback store
(server/services/template_misses.py) — backs the admin panel's Misses panel
and the POST .../feedback endpoint (see docs/template-diagnostics.md).

    venv/bin/python -m pytest server/tests/test_services/test_template_misses.py
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

import pytest

from services import template_misses


@pytest.fixture(autouse=True)
def _reset_store():
    """Each test gets an empty store — the module holds process-global state."""
    template_misses._misses.clear()
    template_misses._feedback.clear()
    template_misses._next_id = 1
    yield
    template_misses._misses.clear()
    template_misses._feedback.clear()
    template_misses._next_id = 1


def test_record_miss_returns_a_stable_string_id():
    miss_id = template_misses.record_miss(
        adapter="intent-sql-postgres",
        query="what's the weather in Paris?",
        reason="below_threshold",
        candidates=[{"template_id": "orders_by_date_range", "similarity": 0.18}],
        threshold=0.4,
    )
    assert miss_id == "1"

    second_id = template_misses.record_miss(
        adapter="intent-sql-postgres", query="q2", reason="no_match", candidates=[], threshold=0.4,
    )
    assert second_id == "2"


def test_list_misses_returns_most_recent_first():
    template_misses.record_miss(adapter="a1", query="first", reason="no_match", candidates=[], threshold=0.4)
    template_misses.record_miss(adapter="a1", query="second", reason="no_match", candidates=[], threshold=0.4)

    misses = template_misses.list_misses(adapter="a1")
    assert [m["query"] for m in misses] == ["second", "first"]


def test_list_misses_filters_by_adapter():
    template_misses.record_miss(adapter="a1", query="for a1", reason="no_match", candidates=[], threshold=0.4)
    template_misses.record_miss(adapter="a2", query="for a2", reason="no_match", candidates=[], threshold=0.4)

    misses_a1 = template_misses.list_misses(adapter="a1")
    assert len(misses_a1) == 1
    assert misses_a1[0]["query"] == "for a1"

    all_misses = template_misses.list_misses()
    assert len(all_misses) == 2


def test_list_misses_respects_limit():
    for i in range(5):
        template_misses.record_miss(adapter="a1", query=f"q{i}", reason="no_match", candidates=[], threshold=0.4)

    assert len(template_misses.list_misses(adapter="a1", limit=2)) == 2


def test_record_miss_preserves_candidates_and_threshold():
    template_misses.record_miss(
        adapter="a1",
        query="q",
        reason="below_threshold",
        candidates=[{"template_id": "t1", "similarity": 0.31}],
        threshold=0.4,
    )
    miss = template_misses.list_misses(adapter="a1")[0]
    assert miss["reason"] == "below_threshold"
    assert miss["candidates"] == [{"template_id": "t1", "similarity": 0.31}]
    assert miss["threshold"] == 0.4
    assert isinstance(miss["timestamp"], float)


def test_misses_store_is_bounded_to_max_entries():
    for i in range(template_misses._MAX_ENTRIES + 10):
        template_misses.record_miss(adapter="a1", query=f"q{i}", reason="no_match", candidates=[], threshold=0.4)

    all_misses = template_misses.list_misses(adapter="a1", limit=template_misses._MAX_ENTRIES + 100)
    assert len(all_misses) == template_misses._MAX_ENTRIES
    # Oldest entries were evicted; the most recent one is still first.
    assert all_misses[0]["query"] == f"q{template_misses._MAX_ENTRIES + 9}"


def test_record_feedback_and_list_feedback_roundtrip():
    template_misses.record_feedback(
        adapter="intent-sql-postgres",
        verdict="incorrect",
        request_id="r1",
        template_id=None,
        expected_template_id="orders_by_date_range",
    )

    feedback = template_misses.list_feedback(adapter="intent-sql-postgres")
    assert len(feedback) == 1
    entry = feedback[0]
    assert entry["verdict"] == "incorrect"
    assert entry["request_id"] == "r1"
    assert entry["template_id"] is None
    assert entry["expected_template_id"] == "orders_by_date_range"


def test_list_feedback_filters_by_adapter_and_orders_most_recent_first():
    template_misses.record_feedback(adapter="a1", verdict="correct")
    template_misses.record_feedback(adapter="a2", verdict="incorrect")
    template_misses.record_feedback(adapter="a1", verdict="incorrect")

    feedback_a1 = template_misses.list_feedback(adapter="a1")
    assert [f["verdict"] for f in feedback_a1] == ["incorrect", "correct"]
