"""
Tests for ContextRetrievalStep's follow-up query rewriting wiring
(server/inference/pipeline/steps/context_retrieval.py):
- session_id is forwarded when the adapter has `supports_followup_rewrite`,
  independent of `supports_session_tracking` (mirrors the existing
  clarification-session forwarding test).
- the rewrite step is skipped whenever a clarification is pending for the
  (adapter, session), so an answer like "the second one" resolves the
  clarification instead of being rewritten against stale prior context.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adapters.capabilities import AdapterCapabilities
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.context_retrieval import ContextRetrievalStep
from services import intent_clarification_state as clarification_state
from services import intent_followup_state


@pytest.fixture(autouse=True)
def _reset_pending_store():
    clarification_state._pending.clear()
    intent_followup_state._last_turn.clear()
    yield
    clarification_state._pending.clear()
    intent_followup_state._last_turn.clear()


def _make_step(retriever, capabilities):
    step = ContextRetrievalStep.__new__(ContextRetrievalStep)
    step.container = MagicMock()
    step.container.has.return_value = False
    step.container.get.side_effect = lambda key: retriever if key == 'retriever' else MagicMock()
    step._get_capabilities = MagicMock(return_value=capabilities)
    step._resolve_retrieval_adapter = MagicMock(return_value=("intent-sql-postgres", capabilities))
    step._get_retriever = AsyncMock(return_value=retriever)
    step._build_retriever_kwargs = MagicMock(return_value={})
    step._apply_language_boost = MagicMock(side_effect=lambda docs, *_: docs)
    step._get_truncation_info = MagicMock(return_value=None)
    step._format_context = MagicMock(return_value="")
    return step


def _make_retriever(clarification_enabled=False, audit_adapter_name="intent-sql-postgres"):
    retriever = MagicMock()
    retriever.clarification_enabled = clarification_enabled
    retriever.audit_adapter_name = audit_adapter_name
    retriever.get_relevant_context = AsyncMock(return_value=[])
    return retriever


@pytest.mark.asyncio
async def test_session_id_forwarded_when_followup_rewrite_enabled():
    capabilities = AdapterCapabilities(supports_followup_rewrite=True)
    retriever = _make_retriever()
    step = _make_step(retriever, capabilities)
    context = ProcessingContext(message="what about Ottawa", adapter_name="intent-sql-postgres", session_id="sess-1")

    with patch(
        "inference.pipeline.steps.context_retrieval.maybe_rewrite_followup_query",
        new=AsyncMock(return_value=context.message),
    ):
        await step.process(context)

    retriever.get_relevant_context.assert_awaited_once()
    _, kwargs = retriever.get_relevant_context.call_args
    assert kwargs.get('session_id') == "sess-1"


@pytest.mark.asyncio
async def test_session_id_not_forwarded_when_followup_rewrite_disabled():
    capabilities = AdapterCapabilities(supports_followup_rewrite=False)
    retriever = _make_retriever()
    step = _make_step(retriever, capabilities)
    context = ProcessingContext(message="what about Ottawa", adapter_name="intent-sql-postgres", session_id="sess-1")

    await step.process(context)

    _, kwargs = retriever.get_relevant_context.call_args
    assert 'session_id' not in kwargs


@pytest.mark.asyncio
async def test_rewrite_is_skipped_when_clarification_pending():
    clarification_state.store_pending("intent-sql-postgres", "sess-1", {"kind": "slot_fill"})
    capabilities = AdapterCapabilities(supports_followup_rewrite=True)
    retriever = _make_retriever()
    step = _make_step(retriever, capabilities)
    context = ProcessingContext(message="the second one", adapter_name="intent-sql-postgres", session_id="sess-1")

    with patch(
        "inference.pipeline.steps.context_retrieval.maybe_rewrite_followup_query",
        new=AsyncMock(return_value="SHOULD NOT BE USED"),
    ) as mock_rewrite:
        await step.process(context)

    mock_rewrite.assert_not_called()
    _, kwargs = retriever.get_relevant_context.call_args
    assert kwargs.get('query') == "the second one"


@pytest.mark.asyncio
async def test_rewrite_is_used_when_no_clarification_pending():
    capabilities = AdapterCapabilities(supports_followup_rewrite=True)
    retriever = _make_retriever()
    step = _make_step(retriever, capabilities)
    context = ProcessingContext(message="what about Ottawa", adapter_name="intent-sql-postgres", session_id="sess-1")

    with patch(
        "inference.pipeline.steps.context_retrieval.maybe_rewrite_followup_query",
        new=AsyncMock(return_value="How many customers bought in Ottawa"),
    ) as mock_rewrite:
        await step.process(context)

    mock_rewrite.assert_awaited_once()
    _, kwargs = retriever.get_relevant_context.call_args
    assert kwargs.get('query') == "How many customers bought in Ottawa"


@pytest.mark.asyncio
async def test_followup_state_lookup_uses_retriever_state_key_not_configured_adapter_name():
    """Regression: on the static-retriever fallback path, `audit_adapter_name` is
    left unset, so the retriever (intent_sql_base.py/intent_http_base.py) stores
    its last-turn state under its class name, not the configured adapter name
    ("intent-sql-postgres"). The rewrite lookup must use that same class-name key
    -- previously it looked up by the configured adapter name instead, so the
    lookup always missed and rewriting was silently disabled whenever the two
    names differ.
    """
    capabilities = AdapterCapabilities(supports_followup_rewrite=True)
    retriever = _make_retriever(audit_adapter_name=None)
    retriever_class_name = retriever.__class__.__name__
    assert retriever_class_name != "intent-sql-postgres"

    intent_followup_state.store_last_turn(
        retriever_class_name, "sess-1",
        {"effective_query": "How many customers bought in Toronto", "template_id": "t1", "parameters": {"city": "Toronto"}},
    )

    step = _make_step(retriever, capabilities)
    context = ProcessingContext(message="what about Ottawa", adapter_name="intent-sql-postgres", session_id="sess-1")

    captured_state_keys = []
    real_get_last_turn = intent_followup_state.get_last_turn

    def _spy_get_last_turn(adapter, session_id):
        captured_state_keys.append(adapter)
        return real_get_last_turn(adapter, session_id)

    with patch(
        "inference.pipeline.steps.intent_query_rewrite.get_last_turn", side_effect=_spy_get_last_turn,
    ):
        await step.process(context)

    assert captured_state_keys == [retriever_class_name]
    retriever.get_relevant_context.assert_awaited_once()
