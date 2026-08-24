"""
Intent Clarification Step

Short-circuits LLM inference when an intent retriever's context-retrieval
result asks a clarifying question (disambiguation or missing-parameter
slot-fill) instead of returning an answer — Phase 5 of
docs/roadmap/intent-template-retrieval.md.

Uses the same block-and-respond pattern as FetchStep: set context.response
to the user-facing text and call context.set_error(..., block=True) so the
pipeline stops before LLMInferenceStep and the question is streamed back
as-is.
"""

from __future__ import annotations

import logging

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)


class IntentClarificationStep(PipelineStep):
    """Detects `metadata.intent_action == "clarify"` on the top retrieved
    document and turns it into the final response."""

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked or context.has_error():
            return False
        if not context.retrieved_docs:
            return False
        metadata = context.retrieved_docs[0].get("metadata") or {}
        return metadata.get("intent_action") == "clarify"

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        doc = context.retrieved_docs[0]
        question = doc.get("content", "")
        context.metadata["intent_clarification"] = doc.get("metadata")
        context.response = question
        context.set_error(question, block=True)
        logger.debug("Intent clarification requested: %s", (doc.get("metadata") or {}).get("clarify_kind"))
        return context
