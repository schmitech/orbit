"""
Domain-specific reranking strategies for template matching
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import re


class RerankingStrategy(ABC):
    """Base class for domain-specific reranking strategies"""
    
    @abstractmethod
    def calculate_boost(self, template_info: Dict, query: str) -> float:
        """Calculate boost score for a template based on domain rules"""
        pass
    
    @abstractmethod
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return domain-specific pattern matchers"""
        pass


class CustomerOrderRerankingStrategy(RerankingStrategy):
    """Reranking strategy for customer order domain"""
    
    def __init__(self, domain_config: Optional[Dict[str, Any]] = None):
        self.domain_config = domain_config or {}
        self.vocabulary = self.domain_config.get('vocabulary', {})
        
    def calculate_boost(self, template_info: Dict, query: str) -> float:
        """Calculate boost for customer order domain"""
        template = template_info['template']
        query_lower = query.lower()
        boost = 0.0
        
        # Handle person name vs city disambiguation
        template_id = template.get('id', '')
        if 'customer_name' in template_id:
            if self._contains_person_name_pattern(query_lower):
                boost += 0.3
        elif 'customer_city' in template_id:
            if self._contains_city_pattern(query_lower):
                boost += 0.3
            if self._contains_person_name_pattern(query_lower):
                boost -= 0.2
        
        return boost
    
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return customer order specific patterns"""
        return {
            'person_name': self._contains_person_name_pattern,
            'city': self._contains_city_pattern,
            'order_status': self._contains_order_status_pattern,
            'payment_method': self._contains_payment_method_pattern
        }
    
    def _contains_person_name_pattern(self, text: str) -> bool:
        """Check if text likely contains a person name"""
        person_indicators = [
            'customer', 'person', 'user', 'client', 'buyer',
            'mr', 'mrs', 'ms', 'dr', 'prof'
        ]
        
        for indicator in person_indicators:
            if indicator in text:
                return True
        
        # Check for patterns like "from [Name] [Name]"
        if re.search(r'from\s+\w+\s+\w+', text):
            if not any(city_word in text for city_word in ['city', 'in', 'located', 'from the']):
                return True
        
        # Check for possessive patterns
        if re.search(r"\w+'s\s+(order|purchase|transaction)", text):
            return True
        
        return False
    
    def _contains_city_pattern(self, text: str) -> bool:
        """Check if text likely contains a city name"""
        city_indicators = [
            'city', 'location', 'from the', 'in ', 'located in',
            'customers in', 'customers from', 'from customers in'
        ]
        
        for indicator in city_indicators:
            if indicator in text:
                return True
        
        geo_terms = ['downtown', 'north', 'south', 'east', 'west', 'metro', 'greater']
        for term in geo_terms:
            if term in text:
                return True
        
        return False
    
    def _contains_order_status_pattern(self, text: str) -> bool:
        """Check if text contains order status terms"""
        if 'enum_values' in self.domain_config:
            status_values = self.domain_config.get('fields', {}).get('order', {}).get('status', {}).get('enum_values', [])
            return any(status.lower() in text for status in status_values)
        return False
    
    def _contains_payment_method_pattern(self, text: str) -> bool:
        """Check if text contains payment method terms"""
        if 'enum_values' in self.domain_config:
            payment_values = self.domain_config.get('fields', {}).get('order', {}).get('payment_method', {}).get('enum_values', [])
            return any(payment.lower().replace('_', ' ') in text for payment in payment_values)
        return False


class RerankingStrategyFactory:
    """Factory for creating domain-specific reranking strategies"""
    
    _strategies = {
        'customer_order': CustomerOrderRerankingStrategy,
        'e-commerce': CustomerOrderRerankingStrategy,
    }
    
    @classmethod
    def register_strategy(cls, domain_name: str, strategy_class: type):
        """Register a new domain strategy"""
        cls._strategies[domain_name.lower()] = strategy_class
    
    @classmethod
    def create_strategy(cls, domain_name: str, domain_config: Optional[Dict[str, Any]] = None) -> RerankingStrategy:
        """Create a strategy for the given domain"""
        strategy_class = cls._strategies.get(domain_name.lower())
        if not strategy_class:
            raise ValueError(f"No strategy registered for domain: {domain_name}")
        return strategy_class(domain_config)