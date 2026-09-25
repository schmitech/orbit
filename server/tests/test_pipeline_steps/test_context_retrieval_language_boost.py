"""
Language-aware retrieval boosting must only act on an accepted detection:
an abstained ('unknown') result must not re-rank documents, and document
language tags are compared by normalized base language, not truncation.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from adapters.capabilities import AdapterCapabilities, RetrievalBehavior
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.context_retrieval import ContextRetrievalStep


def _make_step(config=None):
    step = ContextRetrievalStep.__new__(ContextRetrievalStep)
    retriever = MagicMock()
    retriever.get_relevant_context = AsyncMock(return_value=[{"content": "doc", "confidence": 0.5}])
    adapter_manager = MagicMock()
    adapter_manager.get_adapter = AsyncMock(return_value=retriever)
    services = {"adapter_manager": adapter_manager, "config": config or {}}
    step.container = MagicMock()
    step.container.has.side_effect = lambda key: key in services
    step.container.get.side_effect = lambda key: services.get(key, MagicMock())
    step._get_capabilities = MagicMock(
        return_value=AdapterCapabilities(retrieval_behavior=RetrievalBehavior.ALWAYS)
    )
    step._get_truncation_info = MagicMock(return_value=None)
    step._format_context = MagicMock(return_value="doc")
    return step


@pytest.mark.asyncio
@pytest.mark.parametrize("language,accepted,boosted", [
    ("unknown", False, False),
    ("fr", True, True),
    ("fr", False, False),  # conversation-prior result: not decided by this message
])
async def test_boost_only_for_accepted_language(language, accepted, boosted):
    step = _make_step()
    step._apply_language_boost = MagicMock(side_effect=lambda docs, *_: docs)
    context = ProcessingContext(message="bonjour tout le monde", adapter_name="qa")
    context.detected_language = language
    context.language_detection_meta = {"accepted": accepted}
    context.metadata["last_detected_language_confidence"] = 0.95

    await step.process(context)

    assert step._apply_language_boost.called is boosted


def _boost(step, doc_language, user_language):
    docs = [{"content": "d", "confidence": 0.5, "metadata": {"language": doc_language}}]
    return step._apply_language_boost(docs, user_language, 0.9)[0]


def test_document_language_tag_is_normalized_before_matching():
    step = _make_step({"language_detection": {"retrieval_min_confidence": 0.7}})
    assert _boost(step, "zh-Hant", "zh")["metadata"]["language_matched"] is True
    assert _boost(step, "iw", "he")["metadata"]["language_matched"] is True
    # 'fil' used to truncate to 'fi' and match Finnish
    assert _boost(step, "fil", "fi")["metadata"]["language_matched"] is False


@pytest.mark.parametrize("doc_language", ["xx-invalid", "en--US", "en-@", "en-abcdefghi"])
def test_unrecognized_document_language_is_neither_boosted_nor_penalized(doc_language):
    step = _make_step({"language_detection": {"retrieval_min_confidence": 0.7}})
    doc = _boost(step, doc_language, "en")
    assert doc["confidence"] == 0.5
    assert "language_matched" not in doc["metadata"]
