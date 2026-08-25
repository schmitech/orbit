"""
Regression test: an uploaded file's content must still be retrievable when a skill
request swaps context.adapter_name to a skill adapter (e.g. pdf-generator) that itself
declares retrieval_behavior: none / supports_file_ids: false.

Before this fix, ContextRetrievalStep.should_execute keyed retrieval purely off the
(post-swap) skill adapter's capabilities, so a CSV uploaded and referenced in the same
turn as a "generate a PDF" skill request never got retrieved into context.formatted_context
— even though the original file-capable adapter (e.g. simple-chat-with-files) would have
retrieved it fine for a plain question. ContextRetrievalStep now falls back to the
original (pre-swap) adapter's capabilities/retriever when the swapped adapter itself
wouldn't retrieve but the original would, given the same file_ids.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.capabilities import AdapterCapabilities, RetrievalBehavior
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.context_retrieval import ContextRetrievalStep


def _skill_capabilities():
    """pdf-generator-like: retrieval disabled, no file_ids support."""
    return AdapterCapabilities(retrieval_behavior=RetrievalBehavior.NONE, supports_file_ids=False)


def _file_adapter_capabilities():
    """simple-chat-with-files-like: conditional retrieval, file_ids supported, skipped
    when no files are attached (matches config/adapters/multimodal.yaml)."""
    return AdapterCapabilities(
        retrieval_behavior=RetrievalBehavior.CONDITIONAL, supports_file_ids=True, skip_when_no_files=True,
    )


def _make_step(retriever, capabilities_by_adapter):
    step = ContextRetrievalStep.__new__(ContextRetrievalStep)
    step.container = MagicMock()
    step.container.has.side_effect = lambda key: key == 'adapter_manager'
    adapter_manager = MagicMock()
    adapter_manager.get_adapter = AsyncMock(return_value=retriever)
    step.container.get.side_effect = lambda key: adapter_manager if key == 'adapter_manager' else MagicMock()
    step._get_capabilities = MagicMock(side_effect=lambda name: capabilities_by_adapter.get(name))
    step._apply_language_boost = MagicMock(side_effect=lambda docs, *_: docs)
    step._get_truncation_info = MagicMock(return_value=None)
    step._format_context = MagicMock(return_value="col1,col2\n1,2")
    return step


def _make_retriever():
    retriever = MagicMock()
    retriever.get_relevant_context = AsyncMock(return_value=[{"content": "col1,col2\n1,2"}])
    return retriever


@pytest.mark.asyncio
async def test_should_execute_falls_back_to_original_adapter_when_skill_adapter_wont_retrieve():
    capabilities_by_adapter = {
        "pdf-generator": _skill_capabilities(),
        "simple-chat-with-files": _file_adapter_capabilities(),
    }
    step = _make_step(_make_retriever(), capabilities_by_adapter)
    context = ProcessingContext(
        message="generate a pdf for the uploaded csv",
        adapter_name="pdf-generator",
        original_adapter_name="simple-chat-with-files",
        file_ids=["file-123"],
    )

    assert step.should_execute(context) is True


@pytest.mark.asyncio
async def test_should_execute_false_when_neither_adapter_would_retrieve():
    capabilities_by_adapter = {
        "pdf-generator": _skill_capabilities(),
        "simple-chat-with-files": _file_adapter_capabilities(),
    }
    step = _make_step(_make_retriever(), capabilities_by_adapter)
    context = ProcessingContext(
        message="generate a pdf report",
        adapter_name="pdf-generator",
        original_adapter_name="simple-chat-with-files",
        file_ids=[],  # nothing attached -> original adapter's CONDITIONAL retrieval also skips
    )

    assert step.should_execute(context) is False


@pytest.mark.asyncio
async def test_should_execute_falls_back_to_original_adapter_when_swapped_adapter_has_no_capabilities():
    """Regression: an unrecognized/unregistered skill adapter (no capabilities entry at
    all) must not short-circuit the fallback to the original adapter — the file-capable
    original adapter should still be checked."""
    capabilities_by_adapter = {
        # "pdf-generator" intentionally absent -> _get_capabilities returns None
        "simple-chat-with-files": _file_adapter_capabilities(),
    }
    step = _make_step(_make_retriever(), capabilities_by_adapter)
    context = ProcessingContext(
        message="generate a pdf for the uploaded csv",
        adapter_name="pdf-generator",
        original_adapter_name="simple-chat-with-files",
        file_ids=["file-123"],
    )

    assert step.should_execute(context) is True


@pytest.mark.asyncio
async def test_process_retrieves_via_original_adapter_and_populates_formatted_context():
    retriever = _make_retriever()
    capabilities_by_adapter = {
        "pdf-generator": _skill_capabilities(),
        "simple-chat-with-files": _file_adapter_capabilities(),
    }
    step = _make_step(retriever, capabilities_by_adapter)
    context = ProcessingContext(
        message="generate a pdf for the uploaded csv",
        adapter_name="pdf-generator",
        original_adapter_name="simple-chat-with-files",
        file_ids=["file-123"],
    )

    result = await step.process(context)

    assert result.error is None
    assert result.formatted_context
    # file_ids only get forwarded when the resolved adapter's capabilities support it
    # (simple-chat-with-files does, pdf-generator doesn't) — confirms the retriever was
    # invoked using the original adapter's capabilities, not the skill adapter's.
    _, kwargs = retriever.get_relevant_context.call_args
    assert kwargs.get('file_ids') == ["file-123"]


@pytest.mark.asyncio
async def test_process_uses_skill_adapter_directly_when_it_already_retrieves():
    """No fallback needed (and no behavior change) when the current adapter itself
    already retrieves — e.g. a normal file-aware adapter with no skill swap."""
    retriever = _make_retriever()
    capabilities_by_adapter = {
        "simple-chat-with-files": _file_adapter_capabilities(),
    }
    step = _make_step(retriever, capabilities_by_adapter)
    context = ProcessingContext(
        message="how many records in this file?",
        adapter_name="simple-chat-with-files",
        file_ids=["file-123"],
    )

    result = await step.process(context)

    assert result.error is None
    assert result.formatted_context
