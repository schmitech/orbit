"""
Base class for domain-specific strategies
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class DomainStrategy(ABC):
    """Base class for domain-specific pattern matching and boosting logic"""

    @abstractmethod
    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        pass

    @abstractmethod
    def calculate_domain_boost(self, template_info: dict, query: str, domain_config: dict) -> float:
        """Calculate domain-specific boost for a template"""
        pass

    @abstractmethod
    def get_pattern_matchers(self) -> dict[str, Any]:
        """Return domain-specific pattern matching functions"""
        pass

    @abstractmethod
    def extract_domain_parameters(self, query: str, param: dict, domain_config: Any) -> Optional[Any]:
        """
        Extract domain-specific parameters that require special logic.

        Args:
            query: User's query text
            param: Parameter definition from template
            domain_config: DomainConfig instance

        Returns:
            Extracted value or None if not found
        """
        pass

    @abstractmethod
    def get_semantic_extractors(self) -> dict[str, callable]:
        """
        Return semantic type extractors for this domain.

        Returns:
            Dict mapping semantic types to extraction functions
        """
        pass

    @abstractmethod
    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """
        Get priority for including field in summaries.

        Returns:
            Priority score (higher = more important), or 0 if not relevant
        """
        pass