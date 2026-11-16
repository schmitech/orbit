"""
Cross-retriever regression coverage for IntentHTTPRetriever._get_relevant_context_impl
(server/retrievers/base/intent_http_base.py), the shared base that
IntentGraphQLRetriever and IntentHTTPJSONRetriever use directly (neither
overrides _get_relevant_context_impl) and that IntentFirecrawlRetriever was
reconciled against in
docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md Item 2.

Nothing in this base class was changed during the Firecrawl reconciliation
work -- these tests exist because the plan explicitly calls for the test
matrix below to be run "before merging" to confirm the base's own behavior
(which Firecrawl was reconciled against) is itself correctly covered, not
just asserted by reading the code. Covers, per the plan's enumerated list:
cancellation mid-search, a template with a missing required parameter,
follow-up-turn storage on success, the failure envelope/metadata shape
(including per-template failure reasons), candidate metadata fields, and
empty-formatter-result behavior (try the next template).

These exercise `_get_relevant_context_impl` directly against a minimally
constructed instance with template-matching/execution/formatting mocked,
not a live HTTP/GraphQL backend.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from retrievers.base.intent_http_base import IntentHTTPRetriever

pytestmark = pytest.mark.unit


class _ConcreteIntentHTTPRetriever(IntentHTTPRetriever):
    """
    Minimal concrete subclass satisfying IntentHTTPRetriever's abstractmethods
    so tests can construct an instance (via object.__new__, bypassing
    __init__) without needing a real HTTP backend. The abstract method bodies
    are never exercised -- tests replace _execute_template/_format_http_results
    with mocks per-test.
    """

    def _get_datasource_name(self) -> str:
        return "test_http"

    async def _execute_template(self, template, parameters):
        raise NotImplementedError

    def _format_http_results(self, results, template, parameters, similarity):
        raise NotImplementedError


def _retriever(confidence_threshold=0.5):
    """Minimal IntentHTTPRetriever, bypassing __init__."""
    retriever = object.__new__(_ConcreteIntentHTTPRetriever)
    retriever.confidence_threshold = confidence_threshold
    retriever.template_reranker = None
    retriever.parameter_extractor = None
    retriever.response_generator = None
    retriever.context_format = None
    return retriever


def _template(template_id="t1", required_params=None):
    return {
        "id": template_id,
        "description": "",
        "parameters": [
            {"name": name, "required": True} for name in (required_params or [])
        ],
    }


@pytest.mark.asyncio
async def test_cancelled_before_template_search_returns_empty():
    retriever = _retriever()
    retriever._find_best_templates = AsyncMock()
    cancel_event = MagicMock()
    cancel_event.is_set.return_value = True

    result = await retriever._get_relevant_context_impl("query", cancel_event=cancel_event)

    assert result == []
    retriever._find_best_templates.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_during_template_iteration_returns_empty():
    retriever = _retriever()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._execute_template = AsyncMock()

    cancel_event = MagicMock()
    cancel_event.is_set.side_effect = [False, True]  # clear pre-search, set during iteration

    result = await retriever._get_relevant_context_impl("query", cancel_event=cancel_event)

    assert result == []
    retriever._execute_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_with_missing_required_parameter_is_skipped_and_recorded():
    """
    A template missing a required parameter after extraction must be
    skipped (not attempted with an unfilled placeholder) and recorded in
    failed_templates, unlike Firecrawl's deliberately simpler candidates list.
    """
    retriever = _retriever()
    templates = [
        {"template": _template("missing_param_template", required_params=["url"]), "similarity": 0.9},
        {"template": _template("good_template"), "similarity": 0.8},
    ]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(side_effect=[{}, {"foo": "bar"}])
    retriever._execute_template = AsyncMock(return_value=([{"x": 1}], None))
    retriever._format_http_results = MagicMock(return_value=[{"content": "ok"}])
    retriever._store_followup_turn = MagicMock()

    result = await retriever._get_relevant_context_impl("query")

    assert result == [{"content": "ok"}]
    retriever._execute_template.assert_awaited_once()
    executed_template = retriever._execute_template.await_args.args[0]
    assert executed_template["id"] == "good_template"


@pytest.mark.asyncio
async def test_all_templates_missing_required_param_reports_failed_templates_metadata():
    """
    Confirms the failure envelope's `failed_templates` metadata (which
    Firecrawl deliberately does not adopt) is populated with per-template
    reasons when every candidate is skipped for a missing required parameter.
    """
    retriever = _retriever()
    templates = [{"template": _template("t1", required_params=["url"]), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock()

    result = await retriever._get_relevant_context_impl("query")

    assert len(result) == 1
    metadata = result[0]["metadata"]
    assert metadata["error"] == "parameter_extraction_failed"
    assert metadata["failed_templates"] == [
        {"template_id": "t1", "error": "Missing required params: ['url']"}
    ]
    retriever._execute_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_follow_up_turn_storage_called_on_success_without_response_generator():
    """Unlike Firecrawl (deliberately not adopted), the base calls
    _store_followup_turn() on a successful result when response_generator is None."""
    retriever = _retriever()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={"foo": "bar"})
    retriever._execute_template = AsyncMock(return_value=([{"x": 1}], None))
    retriever._format_http_results = MagicMock(return_value=[{"content": "ok"}])
    retriever._store_followup_turn = MagicMock()

    result = await retriever._get_relevant_context_impl(
        "query", session_id="sess-1"
    )

    assert result == [{"content": "ok"}]
    retriever._store_followup_turn.assert_called_once_with("sess-1", "query", "t1", {"foo": "bar"})


@pytest.mark.asyncio
async def test_follow_up_turn_storage_called_on_success_with_response_generator():
    """Same follow-up-turn storage call must happen on the response_generator branch too."""
    retriever = _retriever()
    retriever.response_generator = MagicMock()
    retriever.response_generator.format_response_data.return_value = {
        "message": "done", "summary": None, "table": None, "result_count": 1,
    }
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={"foo": "bar"})
    retriever._execute_template = AsyncMock(return_value=([{"x": 1}], None))
    retriever._store_followup_turn = MagicMock()

    result = await retriever._get_relevant_context_impl("query", session_id="sess-1")

    assert len(result) == 1
    assert result[0]["metadata"]["domain_aware"] is True
    retriever._store_followup_turn.assert_called_once_with("sess-1", "query", "t1", {"foo": "bar"})


@pytest.mark.asyncio
async def test_empty_formatted_result_tries_next_template():
    """The base's own 'try the next candidate on an empty result' behavior
    that Firecrawl was reconciled to match."""
    retriever = _retriever()
    templates = [
        {"template": _template("empty_result_template"), "similarity": 0.9},
        {"template": _template("good_template"), "similarity": 0.8},
    ]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock(return_value=([{"x": 1}], None))
    retriever._format_http_results = MagicMock(side_effect=[[], [{"content": "ok"}]])
    retriever._store_followup_turn = MagicMock()

    result = await retriever._get_relevant_context_impl("query")

    assert result == [{"content": "ok"}]
    assert retriever._format_http_results.call_count == 2


@pytest.mark.asyncio
async def test_below_threshold_response_includes_candidate_metadata():
    retriever = _retriever(confidence_threshold=0.9)
    templates = [
        {"template": _template("t1"), "similarity": 0.5},
        {"template": _template("t2"), "similarity": 0.3},
    ]
    retriever._find_best_templates = AsyncMock(return_value=templates)

    result = await retriever._get_relevant_context_impl("query")

    assert len(result) == 1
    metadata = result[0]["metadata"]
    assert metadata["error"] == "below_threshold"
    assert metadata["candidates"] == [
        {"template_id": "t1", "similarity": 0.5},
        {"template_id": "t2", "similarity": 0.3},
    ]


@pytest.mark.asyncio
async def test_no_matching_templates_returns_bounded_error_response():
    retriever = _retriever()
    retriever._find_best_templates = AsyncMock(return_value=[])

    result = await retriever._get_relevant_context_impl("query")

    assert len(result) == 1
    assert result[0]["metadata"]["error"] == "no_matching_template"
