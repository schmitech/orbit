"""
Tests for the follow-up-rewrite "last resolved turn" store
(server/services/intent_followup_state.py), the TTL-bounded cache that lets a
follow-up turn ("what about Ottawa") be rewritten against the previous turn's
effective query and parameters.

    venv/bin/python -m pytest server/tests/test_services/test_intent_followup_state.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest

from services import intent_followup_state as followup_state


@pytest.fixture(autouse=True)
def _reset_store():
    followup_state._last_turn.clear()
    yield
    followup_state._last_turn.clear()


class TestStoreAndGetLastTurn:
    def test_round_trips_payload(self):
        followup_state.store_last_turn(
            "adapter-a", "sess-1",
            {"effective_query": "How many customers bought in Toronto", "template_id": "t1", "parameters": {"city": "Toronto"}},
        )
        result = followup_state.get_last_turn("adapter-a", "sess-1")
        assert result["effective_query"] == "How many customers bought in Toronto"
        assert result["template_id"] == "t1"
        assert result["parameters"] == {"city": "Toronto"}

    def test_no_entry_returns_none(self):
        assert followup_state.get_last_turn("adapter-a", "sess-missing") is None

    def test_no_session_id_is_a_no_op(self):
        followup_state.store_last_turn("adapter-a", "", {"effective_query": "x"})
        assert followup_state.get_last_turn("adapter-a", "") is None

    def test_storing_again_replaces_prior_entry(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"})
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Ottawa"})
        assert followup_state.get_last_turn("adapter-a", "sess-1")["effective_query"] == "Ottawa"

    def test_get_is_non_destructive(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"})
        followup_state.get_last_turn("adapter-a", "sess-1")
        assert followup_state.get_last_turn("adapter-a", "sess-1") is not None


class TestIsolation:
    def test_different_sessions_do_not_share_state(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"})
        assert followup_state.get_last_turn("adapter-a", "sess-2") is None

    def test_different_adapters_do_not_share_state(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"})
        assert followup_state.get_last_turn("adapter-b", "sess-1") is None


class TestTTLExpiry:
    def test_entry_expires_after_ttl(self, monkeypatch):
        current_time = [1000.0]
        monkeypatch.setattr(followup_state.time, "time", lambda: current_time[0])

        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"}, ttl=10.0)
        assert followup_state.get_last_turn("adapter-a", "sess-1") is not None

        current_time[0] += 11.0
        assert followup_state.get_last_turn("adapter-a", "sess-1") is None

    def test_entry_within_ttl_is_returned(self, monkeypatch):
        current_time = [1000.0]
        monkeypatch.setattr(followup_state.time, "time", lambda: current_time[0])

        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"}, ttl=300.0)
        current_time[0] += 100.0
        assert followup_state.get_last_turn("adapter-a", "sess-1") is not None


class TestClearLastTurn:
    def test_clears_existing_entry(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"})
        followup_state.clear_last_turn("adapter-a", "sess-1")
        assert followup_state.get_last_turn("adapter-a", "sess-1") is None

    def test_no_session_id_is_a_no_op(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto"})
        followup_state.clear_last_turn("adapter-a", "")
        assert followup_state.get_last_turn("adapter-a", "sess-1") is not None
