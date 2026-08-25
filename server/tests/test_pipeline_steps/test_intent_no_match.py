"""
Regression test: IntentNoMatchStep must short-circuit LLM inference when an
intent retriever returns a "no match" sentinel doc (no template matched, no
candidate cleared the confidence threshold, or parameter extraction failed)
and the adapter requires grounded answers (retrieval_behavior ALWAYS).

Without this, the sentinel doc is formatted like ordinary retrieved context
and handed to LLMInferenceStep, which is then free to answer from the
model's general knowledge instead of admitting it has no matching data.
"""

from unittest.mock import MagicMock, patch

import pytest

from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.intent_no_match import IntentNoMatchStep
from adapters.capabilities import AdapterCapabilities, RetrievalBehavior


def _make_step():
    step = IntentNoMatchStep.__new__(IntentNoMatchStep)
    step.container = MagicMock()
    return step


def _context_with_doc(doc, adapter_name="intent-sql-sqlite-hr", original_adapter_name=None):
    context = ProcessingContext(message="porque los gallos cantan?", adapter_name=adapter_name)
    context.retrieved_docs = [doc]
    context.original_adapter_name = original_adapter_name
    return context


NO_MATCH_DOC = {
    "content": "I couldn't find a matching query pattern for your request.",
    "metadata": {"source": "intent", "error": "no_matching_template"},
}

BELOW_THRESHOLD_DOC = {
    "content": "I found potential matches but none met the confidence threshold.",
    "metadata": {"error": "below_threshold"},
}

PARAM_EXTRACTION_FAILED_DOC = {
    "content": "I couldn't understand the required details for that request.",
    "metadata": {"error": "parameter_extraction_failed"},
}

REAL_DOC = {
    "content": "Engineering has 25 employees.",
    "metadata": {"source": "intent", "template_id": "headcount_by_department"},
}


def _capabilities(behavior):
    return AdapterCapabilities(retrieval_behavior=behavior)


class TestShouldExecute:
    @pytest.mark.parametrize("doc", [NO_MATCH_DOC, BELOW_THRESHOLD_DOC, PARAM_EXTRACTION_FAILED_DOC])
    def test_true_for_no_match_sentinel_when_behavior_always(self, doc):
        step = _make_step()
        context = _context_with_doc(doc)
        with patch("inference.pipeline.steps.intent_no_match.get_capability_registry") as get_registry:
            get_registry.return_value.get.return_value = _capabilities(RetrievalBehavior.ALWAYS)
            assert step.should_execute(context) is True

    def test_false_when_behavior_not_always(self):
        step = _make_step()
        context = _context_with_doc(NO_MATCH_DOC)
        with patch("inference.pipeline.steps.intent_no_match.get_capability_registry") as get_registry:
            get_registry.return_value.get.return_value = _capabilities(RetrievalBehavior.CONDITIONAL)
            assert step.should_execute(context) is False

    def test_false_when_no_capabilities_found(self):
        step = _make_step()
        context = _context_with_doc(NO_MATCH_DOC)
        with patch("inference.pipeline.steps.intent_no_match.get_capability_registry") as get_registry:
            get_registry.return_value.get.return_value = None
            assert step.should_execute(context) is False

    def test_false_for_real_retrieved_doc(self):
        step = _make_step()
        context = _context_with_doc(REAL_DOC)
        with patch("inference.pipeline.steps.intent_no_match.get_capability_registry") as get_registry:
            get_registry.return_value.get.return_value = _capabilities(RetrievalBehavior.ALWAYS)
            assert step.should_execute(context) is False

    def test_uses_original_adapter_capabilities_when_skill_swapped(self):
        """Skill routing can swap context.adapter_name while retrieval still ran
        against the original intent adapter (ContextRetrievalStep._resolve_retrieval_adapter).
        The capabilities lookup must follow original_adapter_name, not the swapped skill,
        or a skill with no/NONE capabilities would mask the no-match response."""
        step = _make_step()
        context = _context_with_doc(
            NO_MATCH_DOC, adapter_name="pdf-skill", original_adapter_name="intent-sql-sqlite-hr"
        )

        def _get(name):
            if name == "intent-sql-sqlite-hr":
                return _capabilities(RetrievalBehavior.ALWAYS)
            return None  # the swapped skill adapter has no capabilities registered

        with patch("inference.pipeline.steps.intent_no_match.get_capability_registry") as get_registry:
            get_registry.return_value.get.side_effect = _get
            assert step.should_execute(context) is True
            get_registry.return_value.get.assert_called_with("intent-sql-sqlite-hr")

    def test_false_when_no_retrieved_docs(self):
        step = _make_step()
        context = ProcessingContext(message="hi", adapter_name="intent-sql-sqlite-hr")
        context.retrieved_docs = []
        assert step.should_execute(context) is False

    def test_false_when_context_already_blocked(self):
        step = _make_step()
        context = _context_with_doc(NO_MATCH_DOC)
        context.is_blocked = True
        assert step.should_execute(context) is False


class TestProcess:
    @pytest.mark.asyncio
    async def test_sets_response_and_blocks_pipeline(self):
        step = _make_step()
        context = _context_with_doc(NO_MATCH_DOC)

        result = await step.process(context)

        assert result.response == NO_MATCH_DOC["content"]
        assert result.is_blocked is True
        assert result.error == NO_MATCH_DOC["content"]
        assert result.metadata["intent_no_match"] == NO_MATCH_DOC["metadata"]
