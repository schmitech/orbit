"""Shared domain-aware component wiring for intent retrievers."""

from retrievers.implementations.intent.domain.extraction import DomainParameterExtractor
from retrievers.implementations.intent.domain.response import DomainResponseGenerator
from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry
from retrievers.implementations.intent.domain import DomainConfig
from retrievers.implementations.intent.template_reranker import TemplateReranker
from retrievers.implementations.intent.template_processor import TemplateProcessor


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
