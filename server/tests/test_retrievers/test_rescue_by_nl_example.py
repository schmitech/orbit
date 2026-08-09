"""
Tests for IntentSQLRetriever._rescue_by_nl_example (server/retrievers/base/intent_sql_base.py).

This is the Jaccard word-overlap fallback that injects templates the vector
search missed. It's called as a bound method on a minimal stand-in object
(rather than a fully initialized IntentSQLRetriever) since it only touches
`self.domain_adapter.get_all_templates()`.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.base.intent_sql_base import IntentSQLRetriever


class _StubDomainAdapter:
    def __init__(self, templates):
        self._templates = templates

    def get_all_templates(self):
        return self._templates


class _StubRetriever:
    """Bare object exposing only what _rescue_by_nl_example touches."""
    def __init__(self, templates):
        self.domain_adapter = _StubDomainAdapter(templates)


def rescue(query, existing, all_templates):
    stub = _StubRetriever(all_templates)
    return IntentSQLRetriever._rescue_by_nl_example(stub, query, existing)


def make_candidate(template_id, similarity=0.5):
    return {"template": {"id": template_id}, "similarity": similarity, "embedding_text": ""}


class TestRescueByNlExample:
    def test_exact_match_injects_with_high_score(self):
        all_templates = [{"id": "find_by_name", "nl_examples": ["Find employees named John"]}]
        result = rescue("Find employees named John", [], all_templates)
        assert len(result) == 1
        assert result[0]["template"]["id"] == "find_by_name"
        assert result[0]["similarity"] == 0.95  # min(0.95, 0.8 + 1.0*0.15)
        assert result[0]["_rescued_by_nl_example"] is True

    def test_high_word_overlap_injects(self):
        all_templates = [{"id": "list_dept", "nl_examples": ["show me all employees in engineering"]}]
        result = rescue("show me employees in engineering", [], all_templates)
        assert len(result) == 1
        assert result[0]["template"]["id"] == "list_dept"

    def test_low_word_overlap_does_not_inject(self):
        all_templates = [{"id": "unrelated", "nl_examples": ["completely different topic entirely"]}]
        result = rescue("find employees named john", [], all_templates)
        assert result == []

    def test_already_present_template_is_not_duplicated(self):
        existing = [make_candidate("find_by_name", 0.9)]
        all_templates = [{"id": "find_by_name", "nl_examples": ["Find employees named John"]}]
        result = rescue("Find employees named John", existing, all_templates)
        assert len(result) == 1
        assert result[0]["template"]["id"] == "find_by_name"
        assert "_rescued_by_nl_example" not in result[0]

    def test_no_templates_returns_existing_unchanged(self):
        existing = [make_candidate("tpl_a")]
        result = rescue("any query", existing, [])
        assert result == existing

    def test_template_without_nl_examples_is_skipped(self):
        all_templates = [{"id": "no_examples"}]
        result = rescue("Find employees named John", [], all_templates)
        assert result == []

    def test_domain_adapter_error_returns_existing_templates(self):
        stub = _StubRetriever([])
        stub.domain_adapter.get_all_templates = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        existing = [make_candidate("tpl_a")]
        result = IntentSQLRetriever._rescue_by_nl_example(stub, "any query", existing)
        assert result == existing

    def test_injected_score_never_exceeds_point_nine_five(self):
        all_templates = [{"id": "tpl", "nl_examples": ["exact match query"]}]
        result = rescue("exact match query", [], all_templates)
        assert result[0]["similarity"] <= 0.95

    def test_multiple_rescues_in_one_call(self):
        all_templates = [
            {"id": "tpl_a", "nl_examples": ["find employees named john"]},
            {"id": "tpl_b", "nl_examples": ["find employees named john too"]},
        ]
        result = rescue("find employees named john", [], all_templates)
        ids = {r["template"]["id"] for r in result}
        assert ids == {"tpl_a", "tpl_b"}
