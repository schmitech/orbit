"""
Regression test: ContextRetrievalStep must forward session_id to a retriever
that has Phase 5 intent clarification enabled, even when the adapter's
`supports_session_tracking` capability is false — which is how every shipped
intent adapter config is set today (see docs/roadmap/intent-template-retrieval.md,
Phase 5's P2 review fix).

Without this, IntentSQLRetriever.get_relevant_context() never receives a
session_id, so `pop_pending()`/`store_pending()` in
services/intent_clarification_state.py never fire and a clarification
follow-up always re-matches from scratch instead of resuming the pinned
template.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.context_retrieval import ContextRetrievalStep


def _make_step(retriever):
    step = ContextRetrievalStep.__new__(ContextRetrievalStep)
    step.container = MagicMock()
    step.container.has.return_value = False  # no adapter_manager -> static retriever path
    step.container.get.side_effect = lambda key: retriever if key == 'retriever' else MagicMock()
    step._get_capabilities = MagicMock(return_value=None)  # -> _build_retriever_kwargs returns {}
    step._apply_language_boost = MagicMock(side_effect=lambda docs, *_: docs)
    step._get_truncation_info = MagicMock(return_value=None)
    step._format_context = MagicMock(return_value="")
    return step


def _make_retriever(clarification_enabled):
    retriever = MagicMock()
    retriever.clarification_enabled = clarification_enabled
    retriever.get_relevant_context = AsyncMock(return_value=[])
    return retriever


@pytest.mark.asyncio
async def test_session_id_forwarded_when_retriever_has_clarification_enabled():
    retriever = _make_retriever(clarification_enabled=True)
    step = _make_step(retriever)
    context = ProcessingContext(message="engineering", adapter_name="intent-sql-postgres", session_id="sess-1")

    await step.process(context)

    retriever.get_relevant_context.assert_awaited_once()
    _, kwargs = retriever.get_relevant_context.call_args
    assert kwargs.get('session_id') == "sess-1"


@pytest.mark.asyncio
async def test_session_id_not_forwarded_when_clarification_disabled():
    retriever = _make_retriever(clarification_enabled=False)
    step = _make_step(retriever)
    context = ProcessingContext(message="engineering", adapter_name="intent-sql-postgres", session_id="sess-1")

    await step.process(context)

    _, kwargs = retriever.get_relevant_context.call_args
    assert 'session_id' not in kwargs


@pytest.mark.asyncio
async def test_no_session_id_on_context_means_nothing_forwarded():
    retriever = _make_retriever(clarification_enabled=True)
    step = _make_step(retriever)
    context = ProcessingContext(message="engineering", adapter_name="intent-sql-postgres", session_id=None)

    await step.process(context)

    _, kwargs = retriever.get_relevant_context.call_args
    assert 'session_id' not in kwargs


@pytest.mark.asyncio
async def test_capability_supplied_session_id_is_not_overridden():
    """When supports_session_tracking already forwarded session_id via
    capabilities, the clarification fallback must not clobber it."""
    retriever = _make_retriever(clarification_enabled=True)
    step = _make_step(retriever)
    step._build_retriever_kwargs = MagicMock(return_value={"session_id": "from-capabilities"})
    context = ProcessingContext(message="engineering", adapter_name="intent-sql-postgres", session_id="sess-1")

    await step.process(context)

    _, kwargs = retriever.get_relevant_context.call_args
    assert kwargs.get('session_id') == "from-capabilities"
