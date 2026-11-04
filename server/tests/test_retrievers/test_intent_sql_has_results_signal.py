"""
Tests for the Phase 3 structured `has_results` signal threaded through
IntentSQLRetriever's result-formatting methods.

See docs/roadmap/response-processor-cleanup.md Phase 3: `has_results` is a
typed, explicit "this source has/doesn't have meaningful data" signal set by
the retriever, which ResponseProcessor._sources_contain_actual_data prefers
over its row_count/content-pattern fallbacks.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.base.intent_sql_base import IntentSQLRetriever


class _ConcreteIntentSQLRetriever(IntentSQLRetriever):
    """Minimal concrete subclass so tests can instantiate the base class without a real
    database connection - only abstract methods are stubbed, nothing under test here."""

    async def _execute_raw_query(self, query, params=None):
        raise NotImplementedError

    def _get_datasource_name(self):
        return "test"

    def get_test_query(self):
        return "SELECT 1"


def make_retriever():
    """Construct a bare retriever without running __init__, setting only the
    attributes _format_execution_response/_format_sql_results actually touch."""
    retriever = object.__new__(_ConcreteIntentSQLRetriever)
    retriever.return_results = None
    retriever.response_generator = None
    retriever.context_format = None
    retriever.domain_adapter = None
    return retriever


def test_format_sql_results_has_results_true_for_nonempty_results():
    retriever = make_retriever()
    retriever.domain_adapter = SimpleNamespace(
        format_document=lambda raw_doc, metadata: {"metadata": dict(metadata)}
    )
    template = {"id": "t1", "description": "test"}
    results = [{"id": 1, "name": "Jane Doe"}]

    docs = retriever._format_sql_results(results, template, {}, similarity=0.9)

    assert docs[0]["metadata"]["has_results"] is True
    assert docs[0]["metadata"]["result_count"] == 1


def test_format_sql_results_has_results_false_for_empty_results():
    retriever = make_retriever()
    template = {"id": "t1", "description": "test"}

    docs = retriever._format_sql_results([], template, {}, similarity=0.9)

    assert docs[0]["metadata"]["has_results"] is False
    assert docs[0]["metadata"]["result_count"] == 0


def test_format_execution_response_has_results_with_domain_adapter(monkeypatch):
    """With a response_generator present, has_results reflects the pre-truncation
    original_result_count, not the post-truncation count the LLM sees."""
    retriever = make_retriever()
    retriever.return_results = 1

    class FakeGenerator:
        def format_response_data(self, results, template):
            return {
                "message": "",
                "summary": f"{len(results)} record(s) found.",
                "result_count": len(results),
            }

    retriever.response_generator = FakeGenerator()

    template = {"id": "t1", "description": "test"}
    results = [{"id": 1}, {"id": 2}, {"id": 3}]

    docs = retriever._format_execution_response(template, {}, results, similarity=1.0)

    assert docs[0]["metadata"]["has_results"] is True
    assert docs[0]["metadata"]["total_available"] == 3
    assert docs[0]["metadata"]["truncated"] is True
