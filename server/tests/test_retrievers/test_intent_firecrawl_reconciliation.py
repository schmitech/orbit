"""
Regression tests for the Firecrawl/base-HTTP-retriever behavioral
reconciliation (Item 2 in
docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md).

Product decisions confirmed with the user before this change (2026-11-15):
- Cancellation (cancel_event) and required-parameter-missing checks: adopted
  from the base IntentHTTPRetriever -- these were bugs in Firecrawl's
  version, not deliberate differences.
- Empty-formatter-result handling: adopted the base's "try the next
  template candidate" behavior instead of Firecrawl's previous "stop on
  first result, empty or not".
- Follow-up-turn storage and per-template failure metadata: explicitly
  NOT adopted -- Firecrawl keeps its simpler candidates-list-only behavior
  by deliberate choice, not as a gap.
- response_generator: left as None (unchanged) -- no adapter built to route
  scraped content through the generic formatter.

These tests exercise `_get_relevant_context_impl` directly against a
minimally-constructed retriever with its template/execution/formatting
methods mocked, not a live Firecrawl API.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from retrievers.implementations.intent.intent_firecrawl_retriever import IntentFirecrawlRetriever

pytestmark = pytest.mark.unit


def _retriever(confidence_threshold=0.5):
    """Minimal IntentFirecrawlRetriever, bypassing __init__ (no real config/adapters needed)."""
    retriever = object.__new__(IntentFirecrawlRetriever)
    retriever.confidence_threshold = confidence_threshold
    retriever.template_reranker = None
    retriever.parameter_extractor = None
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

    result = await retriever._get_relevant_context_impl(
        "query", cancel_event=cancel_event
    )

    assert result == []
    retriever._find_best_templates.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_during_template_iteration_returns_empty():
    retriever = _retriever()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock()

    cancel_event = MagicMock()
    # Not set on the pre-search check, but set by the time the loop runs.
    cancel_event.is_set.side_effect = [False, True]

    result = await retriever._get_relevant_context_impl(
        "query", cancel_event=cancel_event
    )

    assert result == []
    retriever._execute_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_cancel_event_behaves_as_before():
    """cancel_event is optional; omitting it must not change behavior."""
    retriever = _retriever()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock(return_value=([{"url": "x"}], None))
    retriever._format_http_results_async = AsyncMock(return_value=[{"content": "ok"}])

    result = await retriever._get_relevant_context_impl("query")

    assert result == [{"content": "ok"}]


@pytest.mark.asyncio
async def test_template_with_missing_required_parameter_is_skipped():
    """
    Reconciled onto the base IntentHTTPRetriever's behavior: a template
    missing a required parameter after extraction must be skipped in favor
    of the next candidate, not attempted with an unfilled placeholder.
    """
    retriever = _retriever()
    templates = [
        {"template": _template("missing_param_template", required_params=["url"]), "similarity": 0.9},
        {"template": _template("good_template"), "similarity": 0.8},
    ]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    # First template's extraction yields no value for the required 'url' param.
    retriever._extract_parameters = AsyncMock(side_effect=[{}, {"foo": "bar"}])
    retriever._execute_template = AsyncMock(return_value=([{"url": "x"}], None))
    retriever._format_http_results_async = AsyncMock(return_value=[{"content": "ok"}])

    result = await retriever._get_relevant_context_impl("query")

    assert result == [{"content": "ok"}]
    # Only the second (good) template should have reached execution.
    retriever._execute_template.assert_awaited_once()
    executed_template = retriever._execute_template.await_args.args[0]
    assert executed_template["id"] == "good_template"


@pytest.mark.asyncio
async def test_empty_formatted_result_tries_next_template():
    """
    Reconciled onto the base's behavior: an empty formatted result from one
    template candidate must not be returned as final output -- the next
    candidate must be tried instead (previously Firecrawl stopped and
    returned the empty result immediately).
    """
    retriever = _retriever()
    templates = [
        {"template": _template("empty_result_template"), "similarity": 0.9},
        {"template": _template("good_template"), "similarity": 0.8},
    ]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock(return_value=([{"url": "x"}], None))
    retriever._format_http_results_async = AsyncMock(
        side_effect=[[], [{"content": "ok"}]]
    )

    result = await retriever._get_relevant_context_impl("query")

    assert result == [{"content": "ok"}]
    assert retriever._format_http_results_async.await_count == 2


@pytest.mark.asyncio
async def test_all_templates_empty_result_falls_through_to_all_failed_response():
    """If every candidate's formatted result is empty, the final response is
    the same bounded 'all templates failed' message as an execution error."""
    retriever = _retriever()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock(return_value=([{"url": "x"}], None))
    retriever._format_http_results_async = AsyncMock(return_value=[])

    result = await retriever._get_relevant_context_impl("query")

    assert len(result) == 1
    assert result[0]["metadata"]["error"] == "all_templates_failed"


@pytest.mark.asyncio
async def test_follow_up_turn_storage_still_not_called():
    """
    Explicit product decision (kept, not a gap): Firecrawl does not adopt
    the base's follow-up-turn storage. This pins that it stays that way.
    """
    retriever = _retriever()
    retriever._store_followup_turn = MagicMock()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock(return_value=([{"url": "x"}], None))
    retriever._format_http_results_async = AsyncMock(return_value=[{"content": "ok"}])

    await retriever._get_relevant_context_impl("query")

    retriever._store_followup_turn.assert_not_called()


@pytest.mark.asyncio
async def test_candidates_metadata_has_no_per_template_failure_reasons():
    """
    Explicit product decision (kept, not a gap): Firecrawl's candidates list
    stays template id + similarity only, with no per-template failure
    reasons (unlike the base's failed_templates metadata).
    """
    retriever = _retriever()
    templates = [{"template": _template("t1"), "similarity": 0.9}]
    retriever._find_best_templates = AsyncMock(return_value=templates)
    retriever._extract_parameters = AsyncMock(return_value={})
    retriever._execute_template = AsyncMock(return_value=(None, "scrape failed"))

    result = await retriever._get_relevant_context_impl("query")

    assert result[0]["metadata"]["candidates"] == [{"template_id": "t1", "similarity": 0.9}]
    assert "failed_templates" not in result[0]["metadata"]
