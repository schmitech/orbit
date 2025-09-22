"""
Customer order domain-specific strategy.

This strategy now extends GenericDomainStrategy and uses configuration-driven
semantic extraction instead of hardcoded logic.
"""

import re
from typing import Dict, Any, Optional
from .generic import GenericDomainStrategy


class CustomerOrderStrategy(GenericDomainStrategy):
    """Strategy for customer order and e-commerce domains.

    This class now primarily relies on the GenericDomainStrategy's semantic
    extraction capabilities, with minimal domain-specific overrides.
    """

    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        # Add e-commerce specific names to the generic ones
        names = super().get_domain_names()
        if 'customer_order' not in names:
            names.insert(0, 'customer_order')
        if 'e-commerce' not in names:
            names.insert(1, 'e-commerce')
        return names
    
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate boost specific to customer order domain.

        This now delegates most work to the parent GenericDomainStrategy,
        only adding specific disambiguation logic for person names vs cities.
        """
        # Get base boost from generic strategy
        boost = super().calculate_domain_boost(template_info, query, domain_config)

        template = template_info.get('template', {})
        template_id = template.get('id', '')
        query_lower = query.lower()

        # Handle person name vs city disambiguation (domain-specific logic)
        if 'customer_name' in template_id:
            # Check if it's likely a person name context
            if self._is_person_name_context(query_lower):
                boost += 0.3
        elif 'customer_city' in template_id:
            # Check if it's likely a city context
            if self._is_city_context(query_lower):
                boost += 0.3
            # Penalize if it looks more like a person name
            if self._is_person_name_context(query_lower) and not self._is_city_context(query_lower):
                boost -= 0.2

        return boost
    
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return pattern matchers, extending the generic ones."""
        # Get base matchers from parent
        matchers = super().get_pattern_matchers()

        # Add e-commerce specific disambiguation matchers
        matchers['person_name_context'] = self._is_person_name_context
        matchers['city_context'] = self._is_city_context

        return matchers
    
    def _is_person_name_context(self, text: str) -> bool:
        """Check if text is in a person name context.

        This is a simplified version that leverages semantic extraction
        from the parent class and adds e-commerce specific disambiguation.
        """
        # Skip if it has clear city/location indicators
        location_phrases = ['customers in', 'users in', 'clients in', 'buyers in',
                          'orders from the', 'located in', 'city of']
        if any(phrase in text for phrase in location_phrases):
            return False

        # Check for titles (strong person indicators)
        titles = ['mr', 'mrs', 'ms', 'dr', 'prof']
        if any(f'{title}.' in text or f'{title} ' in text for title in titles):
            return True

        # Check for possessive patterns (e.g., "John's order")
        if re.search(r"\w+'s\s+(order|purchase|transaction|account)", text):
            return True

        # Check for "from NAME NAME" pattern where NAME isn't a time word
        from_pattern = r'from\s+(\w+)\s+(\w+)'
        match = re.search(from_pattern, text)
        if match:
            word1, word2 = match.groups()
            time_words = ['last', 'next', 'this', 'past', 'the', 'previous']
            if word1 not in time_words and word2 not in time_words:
                return True

        return False

    def _is_city_context(self, text: str) -> bool:
        """Check if text is in a city/location context."""
        # City/location indicators
        city_indicators = [
            'city', 'location', 'located', 'region', 'area',
            'customers in', 'customers from', 'users in', 'buyers in',
            'from the city', 'in the city', 'located in'
        ]

        if any(indicator in text for indicator in city_indicators):
            return True

        # Geographic qualifiers
        geo_terms = ['downtown', 'north', 'south', 'east', 'west',
                    'metro', 'greater', 'suburban', 'urban']
        if any(term in text for term in geo_terms):
            return True

        return False

    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        """
        Extract domain-specific parameters.

        Most extraction is now handled by the parent GenericDomainStrategy.
        This method only handles special cases that require e-commerce specific logic.
        """
        # First try the generic extractors
        result = super().extract_domain_parameters(query, param, domain_config)
        if result is not None:
            return result

        # Handle any remaining e-commerce specific edge cases
        param_name = param.get('name', '').lower()

        # Special handling for multiple order IDs if not caught by generic extractor
        if 'order_ids' in param_name and not result:
            # The generic multiple_ids extractor should handle this, but keep as fallback
            return self._extract_multiple_ids(query, 'order')

        return None

    def get_semantic_extractors(self) -> Dict[str, callable]:
        """
        Get semantic extractors.

        This now returns the parent's extractors since they handle
        all e-commerce cases through the enhanced generic extractors.
        """
        return super().get_semantic_extractors()

    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """
        Get field priority for e-commerce summaries.

        Uses the parent's priority system but can override specific fields
        for e-commerce if needed.
        """
        # First check parent's priority
        priority = super().get_summary_field_priority(field_name, field_config)

        # E-commerce specific overrides (if the generic priority is too low)
        if priority < 50:
            ecommerce_priorities = {
                'order_id': 100,
                'customer_name': 90,
                'total': 85,
                'payment_method': 70,
                'shipping_address': 60,
            }

            if field_name in ecommerce_priorities:
                return ecommerce_priorities[field_name]

        return priority
