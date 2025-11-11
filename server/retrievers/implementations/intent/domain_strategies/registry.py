"""Domain strategy registry for managing and loading domain-specific strategies."""

import logging
from typing import Any, Dict, Optional, Type

from .base import DomainStrategy
from .generic import GenericDomainStrategy

logger = logging.getLogger(__name__)


class DomainStrategyRegistry:
    """Registry for domain-specific strategies."""

    _builtin_strategies = []  # All domains now use GenericDomainStrategy with YAML config
    _custom_strategies: Dict[str, Type[DomainStrategy]] = {}

    @classmethod
    def get_strategy(
        cls,
        domain_name: Optional[str],
        domain_config: Optional[Any] = None,
    ) -> Optional[DomainStrategy]:
        """Return a strategy instance for the supplied domain or a generic fallback."""

        domain_lower = (domain_name or "").lower()
        domain_type = None
        if domain_config is not None:
            if hasattr(domain_config, "domain_type"):
                domain_type = getattr(domain_config, "domain_type")
            elif isinstance(domain_config, dict):
                domain_type = domain_config.get("domain_type")
        domain_type_lower = domain_type.lower() if domain_type else None

        for strategy_class in cls._builtin_strategies:
            strategy = strategy_class()
            handled_names = {name.lower() for name in strategy.get_domain_names()}
            if domain_lower and domain_lower in handled_names:
                logger.info("Using %s for domain '%s'", strategy_class.__name__, domain_name)
                return strategy
            if domain_type_lower and domain_type_lower in handled_names:
                logger.info(
                    "Using %s for domain type '%s' (domain '%s')",
                    strategy_class.__name__,
                    domain_type,
                    domain_name,
                )
                return strategy

        if domain_lower in cls._custom_strategies:
            strategy_class = cls._custom_strategies[domain_lower]
            logger.info("Using custom %s for domain '%s'", strategy_class.__name__, domain_name)
            return strategy_class()

        if domain_type_lower and domain_type_lower in cls._custom_strategies:
            strategy_class = cls._custom_strategies[domain_type_lower]
            logger.info(
                "Using custom %s for domain type '%s' (domain '%s')",
                strategy_class.__name__,
                domain_type,
                domain_name,
            )
            return strategy_class()

        if domain_config is not None:
            logger.info(
                "Falling back to GenericDomainStrategy for domain '%s' (type '%s')",
                domain_name or getattr(domain_config, "domain_name", "unknown"),
                domain_type or "unknown",
            )
            return GenericDomainStrategy(domain_config)

        if domain_name:
            logger.debug("No strategy found for domain '%s' and no domain configuration provided", domain_name)
        else:
            logger.debug("No domain name provided; strategy lookup skipped")
        return None

    @classmethod
    def register_strategy(cls, domain_name: str, strategy_class: Type[DomainStrategy]):
        """Register a custom domain strategy."""
        if not issubclass(strategy_class, DomainStrategy):
            raise ValueError(f"{strategy_class} must inherit from DomainStrategy")

        cls._custom_strategies[domain_name.lower()] = strategy_class
        logger.info("Registered %s for domain '%s'", strategy_class.__name__, domain_name)

    @classmethod
    def list_available_domains(cls) -> list:
        """List all registered domain identifiers."""
        domains = set()

        for strategy_class in cls._builtin_strategies:
            strategy = strategy_class()
            domains.update(strategy.get_domain_names())

        domains.update(cls._custom_strategies.keys())
        domains.add("generic")

        return sorted(domains)
