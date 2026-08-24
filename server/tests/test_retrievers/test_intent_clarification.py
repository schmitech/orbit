"""
Tests for the Phase 5 graceful-degradation additions to IntentSQLRetriever
(server/retrievers/base/intent_sql_base.py) — confidence-banded
disambiguation/slot-fill clarification — and the pending-clarification store
(server/services/intent_clarification_state.py) that lets a follow-up turn
resume against a pinned template.

Mirrors test_rescue_by_nl_example.py's approach: these helpers only touch a
handful of attributes, so we call them as bound methods on a minimal stub
object rather than constructing a fully-initialized IntentSQLRetriever.

    venv/bin/python -m pytest server/tests/test_retrievers/test_intent_clarification.py
"""

import sys
import os
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest

from retrievers.base.intent_sql_base import IntentSQLRetriever
from services import intent_clarification_state as clarification_state

# Helpers that call other `self.*` helpers internally — bound onto every stub so
# those internal calls resolve, even though _StubRetriever doesn't inherit from
# IntentSQLRetriever. Test-specific behavior (_execute_template, _extract_parameters,
# _format_execution_response) is still supplied per-test via plain instance attributes.
_BOUND_HELPER_METHODS = (
    "_clarification_adapter_key",
    "_missing_required_params",
    "_extract_parameters_for_template",
    "_match_disambiguation_choice",
    "_build_disambiguation_response",
    "_build_slot_fill_clarification",
)


@pytest.fixture(autouse=True)
def _reset_pending_store():
    clarification_state._pending.clear()
    yield
    clarification_state._pending.clear()


class _StubDomainAdapter:
    def __init__(self, templates_by_id):
        self._templates_by_id = templates_by_id

    def get_template_by_id(self, template_id):
        return self._templates_by_id.get(template_id)


class _StubRetriever:
    """Bare object exposing only what the clarification helpers touch."""

    def __init__(self, templates_by_id=None, **overrides):
        self.domain_adapter = _StubDomainAdapter(templates_by_id or {})
        self.audit_adapter_name = "intent-sql-test"
        self.confidence_threshold = 0.4
        self.clarification_enabled = True
        self.clarification_high_threshold = 0.65
        self.clarification_ambiguity_gap = 0.05
        self.clarification_max_rounds = 2
        self.clarification_ttl_seconds = 300
        self.no_match_message = "I couldn't find a matching query pattern for your request."
        self.parameter_extractor = None
        for name in _BOUND_HELPER_METHODS:
            setattr(self, name, types.MethodType(getattr(IntentSQLRetriever, name), self))
        for key, value in overrides.items():
            setattr(self, key, value)


def _template(template_id, description="", parameters=None, content_hash="hash1"):
    return {
        "id": template_id,
        "description": description,
        "parameters": parameters or [],
        "_content_hash": content_hash,
    }


def _candidate(template_id, similarity, description=""):
    return {"template": _template(template_id, description=description), "similarity": similarity}


def _async_extractor(return_value):
    """Build a stand-in for _extract_parameters with the (query, template) signature
    _extract_parameters_for_template calls it with — note it's assigned as a plain
    instance attribute, so it is NOT auto-bound to `self` like a class method would be."""
    async def _extract(query, template):
        return dict(return_value)
    return _extract


class TestMissingRequiredParams:
    def test_no_required_params_returns_empty(self):
        stub = _StubRetriever()
        template = _template("t1", parameters=[{"name": "dept", "required": False}])
        assert IntentSQLRetriever._missing_required_params(stub, template, {}) == []

    def test_missing_required_param_is_reported(self):
        stub = _StubRetriever()
        template = _template("t1", parameters=[{"name": "dept", "required": True}])
        assert IntentSQLRetriever._missing_required_params(stub, template, {}) == ["dept"]

    def test_present_required_param_is_not_reported(self):
        stub = _StubRetriever()
        template = _template("t1", parameters=[{"name": "dept", "required": True}])
        assert IntentSQLRetriever._missing_required_params(stub, template, {"dept": "engineering"}) == []

    def test_none_value_counts_as_missing(self):
        stub = _StubRetriever()
        template = _template("t1", parameters=[{"name": "dept", "required": True}])
        assert IntentSQLRetriever._missing_required_params(stub, template, {"dept": None}) == ["dept"]


class TestBuildDisambiguationResponse:
    def test_returns_clarify_metadata_and_top_candidates(self):
        stub = _StubRetriever()
        templates = [
            _candidate("orders_by_date", 0.55, description="Look up orders by date"),
            _candidate("orders_by_amount", 0.52, description="Look up orders by amount"),
        ]
        result = IntentSQLRetriever._build_disambiguation_response(stub, templates, session_id="s1")

        assert len(result) == 1
        doc = result[0]
        assert doc["metadata"]["source"] == "intent"
        assert doc["metadata"]["intent_action"] == "clarify"
        assert doc["metadata"]["clarify_kind"] == "disambiguate"
        assert [c["template_id"] for c in doc["metadata"]["candidates"]] == ["orders_by_date", "orders_by_amount"]
        assert doc["confidence"] == 0.55
        assert "Look up orders by date" in doc["content"]

    def test_stores_pending_state_for_session(self):
        stub = _StubRetriever()
        templates = [_candidate("t1", 0.55), _candidate("t2", 0.52)]
        IntentSQLRetriever._build_disambiguation_response(stub, templates, session_id="s1")

        pending = clarification_state.pop_pending("intent-sql-test", "s1")
        assert pending["kind"] == "disambiguate"
        assert pending["candidates"] == ["t1", "t2"]

    def test_no_session_id_does_not_store_pending(self):
        stub = _StubRetriever()
        templates = [_candidate("t1", 0.55), _candidate("t2", 0.52)]
        IntentSQLRetriever._build_disambiguation_response(stub, templates, session_id=None)

        assert clarification_state.pop_pending("intent-sql-test", "s1") is None


class TestBuildSlotFillClarification:
    def test_returns_clarify_metadata_with_missing_params(self):
        stub = _StubRetriever()
        template = _template("orders_by_dept", parameters=[
            {"name": "dept", "required": True, "description": "the department name"},
        ])
        result = IntentSQLRetriever._build_slot_fill_clarification(
            stub, template, {}, ["dept"], 0.8, session_id="s1"
        )

        doc = result[0]
        assert doc["metadata"]["intent_action"] == "clarify"
        assert doc["metadata"]["clarify_kind"] == "slot_fill"
        assert doc["metadata"]["missing_params"] == ["dept"]
        assert doc["metadata"]["pending"]["template_id"] == "orders_by_dept"
        assert "the department name" in doc["content"]
        assert doc["confidence"] == 0.8

    def test_stores_pending_state_including_extracted_params(self):
        stub = _StubRetriever()
        template = _template("orders_by_dept", parameters=[{"name": "dept", "required": True}])
        IntentSQLRetriever._build_slot_fill_clarification(
            stub, template, {"limit": 10}, ["dept"], 0.8, session_id="s1"
        )

        pending = clarification_state.pop_pending("intent-sql-test", "s1")
        assert pending["kind"] == "slot_fill"
        assert pending["template_id"] == "orders_by_dept"
        assert pending["template_hash"] == "hash1"
        assert pending["extracted"] == {"limit": 10}
        assert pending["round"] == 1


class TestMatchDisambiguationChoice:
    @pytest.mark.parametrize("answer,expected", [
        ("1", "t1"), ("one", "t1"), ("first", "t1"),
        ("2", "t2"), ("the second one", "t2"),
        ("3", "t3"),
    ])
    def test_ordinal_answers_map_to_candidate(self, answer, expected):
        stub = _StubRetriever()
        assert IntentSQLRetriever._match_disambiguation_choice(stub, answer, ["t1", "t2", "t3"]) == expected

    def test_template_id_keyword_in_answer_matches(self):
        stub = _StubRetriever()
        assert IntentSQLRetriever._match_disambiguation_choice(
            stub, "I meant the orders_by_dept one", ["orders_by_dept", "orders_by_amount"]
        ) == "orders_by_dept"

    def test_unrecognized_answer_returns_none(self):
        stub = _StubRetriever()
        assert IntentSQLRetriever._match_disambiguation_choice(stub, "banana", ["t1", "t2"]) is None


class TestResumePendingClarification:
    @pytest.mark.asyncio
    async def test_slot_fill_resume_with_all_params_filled_executes_template(self):
        template = _template("orders_by_dept", parameters=[{"name": "dept", "required": True}])
        execute_calls = []

        async def fake_execute_template(tmpl, params):
            execute_calls.append(params)
            return [{"id": 1}], None

        stub = _StubRetriever(
            templates_by_id={"orders_by_dept": template},
            _extract_parameters=_async_extractor({"dept": "engineering"}),
        )
        stub._execute_template = fake_execute_template
        stub._format_execution_response = lambda tmpl, params, results, sim: [{
            "content": "ok", "metadata": {"source": "intent", "template_id": "orders_by_dept"}, "confidence": sim,
        }]

        pending = {"kind": "slot_fill", "template_id": "orders_by_dept", "template_hash": "hash1",
                   "extracted": {}, "missing_params": ["dept"], "round": 1}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "engineering", pending, "s1")

        assert result[0]["metadata"]["template_id"] == "orders_by_dept"
        assert execute_calls == [{"dept": "engineering"}]

    @pytest.mark.asyncio
    async def test_slot_fill_resume_still_missing_reasks_and_bumps_round(self):
        template = _template("orders_by_dept", parameters=[
            {"name": "dept", "required": True}, {"name": "year", "required": True},
        ])
        stub = _StubRetriever(
            templates_by_id={"orders_by_dept": template},
            _extract_parameters=_async_extractor({"dept": "engineering"}),
        )

        pending = {"kind": "slot_fill", "template_id": "orders_by_dept", "template_hash": "hash1",
                   "extracted": {}, "missing_params": ["dept", "year"], "round": 1}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "engineering", pending, "s1")

        assert result[0]["metadata"]["clarify_kind"] == "slot_fill"
        assert result[0]["metadata"]["missing_params"] == ["year"]

        stored = clarification_state.pop_pending("intent-sql-test", "s1")
        assert stored["round"] == 2
        assert stored["extracted"] == {"dept": "engineering"}

    @pytest.mark.asyncio
    async def test_slot_fill_resume_gives_up_after_max_rounds(self):
        template = _template("orders_by_dept", parameters=[{"name": "dept", "required": True}])
        stub = _StubRetriever(
            templates_by_id={"orders_by_dept": template},
            _extract_parameters=_async_extractor({}),
        )

        pending = {"kind": "slot_fill", "template_id": "orders_by_dept", "template_hash": "hash1",
                   "extracted": {}, "missing_params": ["dept"], "round": 2}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "still no idea", pending, "s1")

        assert result[0]["metadata"]["error"] == "parameter_extraction_failed"
        assert clarification_state.pop_pending("intent-sql-test", "s1") is None

    @pytest.mark.asyncio
    async def test_slot_fill_resume_falls_through_when_template_hash_changed(self):
        template = _template("orders_by_dept", parameters=[{"name": "dept", "required": True}], content_hash="hash2")
        stub = _StubRetriever(templates_by_id={"orders_by_dept": template})

        pending = {"kind": "slot_fill", "template_id": "orders_by_dept", "template_hash": "hash1",
                   "extracted": {}, "missing_params": ["dept"], "round": 1}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "engineering", pending, "s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_slot_fill_resume_falls_through_when_template_removed(self):
        stub = _StubRetriever(templates_by_id={})
        pending = {"kind": "slot_fill", "template_id": "gone", "template_hash": "hash1",
                   "extracted": {}, "missing_params": ["dept"], "round": 1}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "engineering", pending, "s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_disambiguate_resume_unrecognized_answer_falls_through(self):
        stub = _StubRetriever()
        pending = {"kind": "disambiguate", "candidates": ["t1", "t2"], "round": 1}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "banana", pending, "s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_disambiguate_resume_executes_chosen_template(self):
        template = _template("orders_by_dept", parameters=[])
        stub = _StubRetriever(
            templates_by_id={"orders_by_dept": template},
            _extract_parameters=_async_extractor({}),
        )

        async def fake_execute_template(tmpl, params):
            return [{"id": 1}], None

        stub._execute_template = fake_execute_template
        stub._format_execution_response = lambda tmpl, params, results, sim: [{
            "content": "ok", "metadata": {"source": "intent", "template_id": "orders_by_dept"}, "confidence": sim,
        }]

        pending = {"kind": "disambiguate", "candidates": ["orders_by_dept", "other"], "round": 1}

        result = await IntentSQLRetriever._resume_pending_clarification(stub, "the first one", pending, "s1")
        assert result[0]["metadata"]["template_id"] == "orders_by_dept"
