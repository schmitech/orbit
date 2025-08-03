"""
Domain strategy registry for managing and loading domain-specific strategies
"""

import logging
from typing import Dict, Optional, Type
from .base import DomainStrategy
from .customer_order import CustomerOrderStrategy

logger = logging.getLogger(__name__)


class DomainStrategyRegistry:
    """Registry for domain-specific strategies"""
    
    # Built-in strategies
    _builtin_strategies = [
        CustomerOrderStrategy,
    ]
    
    # Custom registered strategies
    _custom_strategies: Dict[str, Type[DomainStrategy]] = {}
    
    @classmethod
    def get_strategy(cls, domain_name: str) -> Optional[DomainStrategy]:
        """Get strategy instance for a given domain"""
        if not domain_name:
            return None
        
        domain_lower = domain_name.lower()
        
        # Check built-in strategies
        for strategy_class in cls._builtin_strategies:
            strategy = strategy_class()
            if domain_lower in [d.lower() for d in strategy.get_domain_names()]:
                logger.info(f"Using {strategy_class.__name__} for domain '{domain_name}'")
                return strategy
        
        # Check custom strategies
        if domain_lower in cls._custom_strategies:
            strategy_class = cls._custom_strategies[domain_lower]
            logger.info(f"Using custom {strategy_class.__name__} for domain '{domain_name}'")
            return strategy_class()
        
        logger.debug(f"No specific strategy found for domain '{domain_name}'")
        return None
    
    @classmethod
    def register_strategy(cls, domain_name: str, strategy_class: Type[DomainStrategy]):
        """Register a custom domain strategy"""
        if not issubclass(strategy_class, DomainStrategy):
            raise ValueError(f"{strategy_class} must inherit from DomainStrategy")
        
        domain_lower = domain_name.lower()
        cls._custom_strategies[domain_lower] = strategy_class
        logger.info(f"Registered {strategy_class.__name__} for domain '{domain_name}'")
    
    @classmethod
    def list_available_domains(cls) -> list:
        """List all available domain names"""
        domains = set()
        
        # Add built-in domains
        for strategy_class in cls._builtin_strategies:
            strategy = strategy_class()
            domains.update(strategy.get_domain_names())
        
        # Add custom domains
        domains.update(cls._custom_strategies.keys())
        
        return sorted(list(domains))