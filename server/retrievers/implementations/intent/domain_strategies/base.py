"""
Base class for domain-specific strategies
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class DomainStrategy(ABC):
    """Base class for domain-specific pattern matching and boosting logic"""
    
    @abstractmethod
    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        pass
    
    @abstractmethod
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate domain-specific boost for a template"""
        pass
    
    @abstractmethod
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return domain-specific pattern matching functions"""
        pass