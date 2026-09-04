"""Shared domain-aware component wiring for intent retrievers."""

from typing import Any

from retrievers.implementations.intent.domain.extraction import DomainParameterExtractor
from retrievers.implementations.intent.domain.response import DomainResponseGenerator
from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry
from retrievers.implementations.intent.domain import DomainConfig
from retrievers.implementations.intent.template_reranker import TemplateReranker
from retrievers.implementations.intent.template_processor import TemplateProcessor
from services.metrics_service import get_metrics_service_instance
from services.template_misses import record_miss

# Maps a get_relevant_context() result's metadata["error"] to a metrics
# outcome label. A missing/unrecognized error with no template_id present
# means the caller returned early (e.g. cancellation) and nothing is recorded.
_ERROR_TO_OUTCOME = {
    "no_matching_template": "no_match",
    "below_threshold": "below_threshold",
    "parameter_extraction_failed": "param_validation_failed",
    "datasource_unavailable": "datasource_unavailable",
    "adapter_not_found": "error",
    "cross_adapter_all_failed": "error",
}


def record_intent_telemetry(retriever: Any, query: str, result: list[dict[str, Any]]) -> None:
    """Report the outcome of one get_relevant_context() call to metrics and,
    for no-match/below-threshold/param-failure outcomes, the misses store.

    A single free function (rather than a mixin method) so every intent
    retriever variant — including ones that don't share a common base class,
    like CompositeIntentRetriever — can call it from wherever their own
    get_relevant_context() terminates, without needing to inherit a shared
    wrapper.
    """
    if not result:
        return
    entry = result[0]
    metadata = entry.get("metadata") or {}
    error = metadata.get("error")
    template_id = metadata.get("template_id")
    confidence = entry.get("confidence")
    adapter = getattr(retriever, "audit_adapter_name", None) or retriever.__class__.__name__
    confidence_threshold = getattr(retriever, "confidence_threshold", None)

    intent_action = metadata.get("intent_action")

    if error:
        outcome = _ERROR_TO_OUTCOME.get(error, "error")
    elif template_id:
        outcome = "executed"
    elif intent_action == "clarify":
        outcome = f"clarify_{metadata.get('clarify_kind', 'unknown')}"
    else:
        return

    metrics = get_metrics_service_instance()
    if metrics:
        metrics.record_intent_outcome(adapter, template_id, outcome, confidence=confidence)
        if outcome == "executed":
            rows = metadata.get("result_count")
            if isinstance(rows, int):
                metrics.record_intent_rows_returned(adapter, template_id, rows)

    if outcome in ("no_match", "below_threshold", "param_validation_failed"):
        record_miss(
            adapter=adapter,
            query=query,
            reason=outcome,
            candidates=metadata.get("candidates", []),
            threshold=confidence_threshold if confidence_threshold is not None else 0.0,
        )


class IntentDomainComponentsMixin:
    """Build domain-aware helpers used by SQL and HTTP intent retrievers."""

    def _rebuild_domain_components(self) -> None:
        """Rebuild domain-aware helpers from the current domain adapter."""
        domain_config = self.domain_adapter.get_domain_config()

        if isinstance(domain_config, dict):
            domain_config = DomainConfig(domain_config)

        domain_strategy = DomainStrategyRegistry.get_strategy(
            domain_config.domain_name,
            domain_config,
        )

        self.parameter_extractor = DomainParameterExtractor(
            self.inference_client,
            domain_config,
            domain_strategy,
        )
        self.response_generator = DomainResponseGenerator(domain_config, domain_strategy)
        self.template_reranker = TemplateReranker(domain_config, domain_strategy)
        self.template_processor = TemplateProcessor(domain_config)
