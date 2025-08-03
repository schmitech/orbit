"""
Customer order domain-specific strategy
"""

import re
from typing import Dict, Any
from .base import DomainStrategy


class CustomerOrderStrategy(DomainStrategy):
    """Strategy for customer order and e-commerce domains"""
    
    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        return ['customer_order', 'e-commerce']
    
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate boost specific to customer order domain"""
        template = template_info.get('template', {})
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
        
        # Check for order-specific patterns
        if 'order' in template_id or 'purchase' in template_id:
            if self._contains_order_pattern(query_lower, domain_config):
                boost += 0.2
        
        # Check for payment method patterns
        if 'payment' in template_id:
            if self._contains_payment_pattern(query_lower, domain_config):
                boost += 0.2
        
        return boost
    
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return customer order specific pattern matchers"""
        return {
            'person_name': self._contains_person_name_pattern,
            'city': self._contains_city_pattern,
            'order': self._contains_order_pattern,
            'payment': self._contains_payment_pattern
        }
    
    def _contains_person_name_pattern(self, text: str) -> bool:
        """Check if text likely contains a person name"""
        # Skip if it has clear city indicators first
        if any(city_phrase in text for city_phrase in ['customers in', 'users in', 'clients in', 'buyers in']):
            return False
            
        # Common patterns for person names (but not when followed by "in")
        person_indicators = [
            'mr', 'mrs', 'ms', 'dr', 'prof'  # Titles are strong indicators
        ]
        
        for indicator in person_indicators:
            if indicator in text:
                return True
        
        # Pattern: "from" followed by two capitalized words (names typically start with capital)
        # We check for at least one capital letter in each word to distinguish from time expressions
        words_after_from = re.findall(r'from\s+(\w+)\s+(\w+)', text)
        for word1, word2 in words_after_from:
            # Check if at least one word starts with uppercase (in original text)
            # Since we receive lowercase text, check if it's not a common time word
            time_words = ['last', 'next', 'this', 'past', 'the', 'week', 'month', 'year', 'day']
            if word1 not in time_words and word2 not in time_words:
                # Additional check: not followed by city indicators
                if not any(city_word in text for city_word in ['city', 'in the', 'located', 'from the']):
                    return True
        
        # Check for possessive patterns
        if re.search(r"\w+'s\s+(order|purchase|transaction)", text):
            return True
        
        return False
    
    def _contains_city_pattern(self, text: str) -> bool:
        """Check if text likely contains a city name"""
        # City indicators
        city_indicators = [
            'city', 'location', 'from the', 'in ', 'located in',
            'customers in', 'customers from', 'from customers in'
        ]
        
        for indicator in city_indicators:
            if indicator in text:
                return True
        
        # Check for known geographic qualifiers
        geo_terms = ['downtown', 'north', 'south', 'east', 'west', 'metro', 'greater']
        for term in geo_terms:
            if term in text:
                return True
        
        return False
    
    def _contains_order_pattern(self, text: str, domain_config: Dict) -> bool:
        """Check if text contains order-related terms"""
        order_terms = ['order', 'purchase', 'transaction', 'sale', 'invoice']
        
        # Check basic terms
        if any(term in text for term in order_terms):
            return True
        
        # Check for order status values from domain config
        fields = domain_config.get('fields', {}).get('order', {})
        status_field = fields.get('status', {})
        if status_values := status_field.get('enum_values', []):
            if any(status.lower() in text for status in status_values):
                return True
        
        return False
    
    def _contains_payment_pattern(self, text: str, domain_config: Dict) -> bool:
        """Check if text contains payment-related terms"""
        payment_terms = ['payment', 'pay', 'paid', 'credit', 'debit', 'card', 'cash']
        
        # Check basic terms
        if any(term in text for term in payment_terms):
            return True
        
        # Check for payment method values from domain config
        fields = domain_config.get('fields', {}).get('order', {})
        payment_field = fields.get('payment_method', {})
        if payment_values := payment_field.get('enum_values', []):
            if any(payment.lower().replace('_', ' ') in text for payment in payment_values):
                return True
        
        return False