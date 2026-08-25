"""
Intent No-Match Step

Short-circuits LLM inference when an intent retriever's context-retrieval
result is a "no match" sentinel doc (no template matched, no candidate
cleared the confidence threshold, or parameter extraction failed) and the
adapter requires grounded answers (retrieval_behavior == ALWAYS). Without
this, the sentinel doc is formatted like ordinary retrieved context and
handed to LLMInferenceStep, which is then free to answer from the model's
general knowledge instead of admitting it has no matching data.

Uses the same block-and-respond pattern as IntentClarificationStep: set
context.response to the sentinel message and call context.set_error(...,
block=True) so the pipeline stops before LLMInferenceStep and the message
is streamed back as-is.
"""

from __future__ import annotations

import logging

from ..base import PipelineStep, ProcessingContext
from adapters.capabilities import get_capability_registry, RetrievalBehavior

logger = logging.getLogger(__name__)

NO_MATCH_ERRORS = {
    "no_matching_template",
    "below_threshold",
    "parameter_extraction_failed",
}


class IntentNoMatchStep(PipelineStep):
    """Detects a "no match" sentinel doc on the top retrieved document and
    turns it into the final response, when the adapter requires grounded
    (retrieval_behavior ALWAYS) answers."""

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked or context.has_error():
            return False
        if not context.retrieved_docs:
            return False
        metadata = context.retrieved_docs[0].get("metadata") or {}
        if metadata.get("error") not in NO_MATCH_ERRORS:
            return False
        # Skill routing can swap context.adapter_name while retrieval still runs
        # against the original adapter (see ContextRetrievalStep._resolve_retrieval_adapter),
        # so the sentinel doc's capabilities must be looked up the same way — otherwise a
        # skill with retrieval_behavior NONE/no capabilities masks the original adapter's
        # no-match response and lets the LLM answer from general knowledge.
        capabilities = get_capability_registry().get(context.original_adapter_name or context.adapter_name)
        return bool(capabilities) and capabilities.retrieval_behavior == RetrievalBehavior.ALWAYS

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        doc = context.retrieved_docs[0]
        message = doc.get("content", "")
        context.metadata["intent_no_match"] = doc.get("metadata")
        context.response = message
        context.set_error(message, block=True)
        logger.debug("Intent no-match short-circuit: %s", (doc.get("metadata") or {}).get("error"))
        return context
