"""
Tests for the non-destructive `has_pending` peek added to
server/services/intent_clarification_state.py, used by follow-up query
rewriting to skip ahead of a pending clarification without consuming it
(see inference/pipeline/steps/context_retrieval.py).

    venv/bin/python -m pytest server/tests/test_services/test_intent_clarification_state_has_pending.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest

from services import intent_clarification_state as clarification_state


@pytest.fixture(autouse=True)
def _reset_pending_store():
    clarification_state._pending.clear()
    yield
    clarification_state._pending.clear()


def test_has_pending_true_after_store():
    clarification_state.store_pending("adapter-a", "sess-1", {"kind": "disambiguate"})
    assert clarification_state.has_pending("adapter-a", "sess-1") is True


def test_has_pending_false_when_nothing_stored():
    assert clarification_state.has_pending("adapter-a", "sess-1") is False


def test_has_pending_does_not_consume_entry():
    clarification_state.store_pending("adapter-a", "sess-1", {"kind": "disambiguate"})
    clarification_state.has_pending("adapter-a", "sess-1")
    # pop_pending still finds it afterward -- the peek did not consume it.
    assert clarification_state.pop_pending("adapter-a", "sess-1") is not None


def test_has_pending_false_after_expiry(monkeypatch):
    current_time = [1000.0]
    monkeypatch.setattr(clarification_state.time, "time", lambda: current_time[0])

    clarification_state.store_pending("adapter-a", "sess-1", {"kind": "disambiguate"}, ttl=10.0)
    assert clarification_state.has_pending("adapter-a", "sess-1") is True

    current_time[0] += 11.0
    assert clarification_state.has_pending("adapter-a", "sess-1") is False


def test_has_pending_false_for_empty_session_id():
    clarification_state.store_pending("adapter-a", "sess-1", {"kind": "disambiguate"})
    assert clarification_state.has_pending("adapter-a", "") is False
