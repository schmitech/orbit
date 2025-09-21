"""
Customer order domain-specific strategy
"""

import re
from typing import Dict, Any, Optional
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
        if hasattr(domain_config, 'entities') and 'order' in domain_config.entities:
            # DomainConfig object
            order_entity = domain_config.entities['order']
            if 'status' in order_entity.fields:
                status_field = order_entity.fields['status']
                if hasattr(status_field, 'enum_values') and status_field.enum_values:
                    if any(status.lower() in text for status in status_field.enum_values):
                        return True
        elif isinstance(domain_config, dict) and 'fields' in domain_config:
            # Dictionary format (backward compatibility)
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
        if hasattr(domain_config, 'entities') and 'order' in domain_config.entities:
            # DomainConfig object
            order_entity = domain_config.entities['order']
            if 'payment_method' in order_entity.fields:
                payment_field = order_entity.fields['payment_method']
                if hasattr(payment_field, 'enum_values') and payment_field.enum_values:
                    if any(payment.lower().replace('_', ' ') in text for payment in payment_field.enum_values):
                        return True
        elif isinstance(domain_config, dict) and 'fields' in domain_config:
            # Dictionary format (backward compatibility)
            fields = domain_config.get('fields', {}).get('order', {})
            payment_field = fields.get('payment_method', {})
            if payment_values := payment_field.get('enum_values', []):
                if any(payment.lower().replace('_', ' ') in text for payment in payment_values):
                    return True

        return False

    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        """
        Extract domain-specific parameters for customer order domain.
        This will handle order IDs, amounts, days, and other e-commerce specific parameters.
        """
        param_name = param.get('name', '')
        param_type = param.get('type') or param.get('data_type', 'string')

        # Multiple order IDs - check this FIRST before single order_id
        if 'order_ids' in param_name.lower() or param_name == 'order_ids':
            return self._extract_order_ids(query)

        # Single Order ID extraction
        if 'order' in param_name.lower() and ('id' in param_name.lower() or 'number' in param_name.lower()):
            return self._extract_order_id(query, param_type)

        # Amount extraction
        if 'amount' in param_name.lower():
            return self._extract_amount(query, param_type)

        # Days/time period
        if 'days' in param_name.lower():
            return self._extract_days(query)

        # Customer ID extraction
        if 'customer' in param_name.lower() and 'id' in param_name.lower():
            return self._extract_customer_id(query, param_type)

        return None

    def _extract_order_id(self, query: str, param_type: str) -> Optional[Any]:
        """Extract single order ID from query"""
        order_patterns = [
            r'order\s+(?:number\s+|#\s*|id\s+)?(\d+)',  # order 12345, order #12345, order number 12345
            r'#\s*(\d+)',  # #12345
            r'(?:order|id|number)\s+(\d+)',  # various patterns
            r'\b(\d{4,})\b',  # any 4+ digit number (fallback)
        ]

        for pattern in order_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return None

    def _extract_customer_id(self, query: str, param_type: str) -> Optional[Any]:
        """Extract a customer identifier from the query"""
        customer_patterns = [
            r'customer\s+(?:number\s+|#\s*|id\s+)?(\d+)',
            r'customer\s*(\d{3,})',
            r'customer_id\s*(\d+)',
        ]

        for pattern in customer_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                value = match.group(1)
                if param_type in {'integer', 'int'}:
                    try:
                        return int(value)
                    except ValueError:
                        continue
                return value

        return None

    def _extract_order_ids(self, query: str) -> Optional[str]:
        """Extract multiple order IDs from query"""
        # Look for comma-separated IDs
        ids_pattern = r'orders?\s+(\d+(?:\s*,\s*\d+)+)'
        match = re.search(ids_pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).replace(' ', '')

        # Check for ranges
        range_patterns = [
            r'(\d+)\s+(?:to|through|-)\s+(\d+)',  # 100 to 200, 100-200
            r'between\s+(\d+)\s+and\s+(\d+)',  # between 100 and 200
        ]

        for pattern in range_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                start, end = match.groups()
                # Generate comma-separated list for the range
                start_int = int(start)
                end_int = int(end)
                if end_int - start_int <= 100:  # Limit range size
                    ids = ','.join(str(i) for i in range(start_int, end_int + 1))
                    return ids
                return f"{start},{end}"  # Just return endpoints for large ranges

        # If it's order_ids but we only found a single ID, return it as a string
        single_patterns = [
            r'order\s+(?:number\s+|#\s*|id\s+)?(\d+)',  # order 12345
            r'#\s*(\d+)',  # #12345
            r'(?:find|show|get|lookup|pull)\s+(?:order\s+)?(\d+)',  # various patterns
        ]

        for pattern in single_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return str(match.group(1))

        return None

    def _extract_amount(self, query: str, param_type: str) -> Optional[Any]:
        """Extract monetary amounts from query"""
        amount_patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $500, $1,000.50
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?|usd)',  # 500 dollars
            r'(?:above|below|over|under|than|exceeds?|less than|greater than)\s+\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\b(?!\s*days?)',  # over $500 but not "500 days"
        ]

        for pattern in amount_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    if param_type == 'integer':
                        return int(float(amount_str))
                    else:
                        return float(amount_str)
                except ValueError:
                    continue
        return None

    def _extract_days(self, query: str) -> Optional[int]:
        """Extract time periods in days from query"""
        # Look for patterns like "7 days", "last 30 days", "past week", etc.
        days_patterns = [
            r'(?:last|past|previous|within)\s+(\d+)\s+days?',  # last 7 days
            r'(\d+)\s+days?\s+(?:ago|back)',  # 7 days ago
            r'(?:in|within)\s+(?:the\s+)?(?:last|past)\s+(\d+)\s+days?',  # in the last 30 days
        ]

        for pattern in days_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Handle special time period words
        time_mappings = {
            'last week': 7,
            'past week': 7,
            'this week': 7,
            'last month': 30,
            'past month': 30,
            'this month': 30,
            'last quarter': 90,
            'past quarter': 90,
            'this quarter': 90,
            'last year': 365,
            'past year': 365,
            'this year': 365,
            'today': 1,
            'yesterday': 1,
        }

        query_lower = query.lower()
        for period, days in time_mappings.items():
            if period in query_lower:
                return days

        return None

    def get_semantic_extractors(self) -> Dict[str, callable]:
        """Return e-commerce specific semantic extractors"""
        return {
            'order_identifier': lambda q, t: self._extract_order_id(q, t),
            'monetary_amount': lambda q, t: self._extract_amount(q, t),
            'time_period_days': lambda q: self._extract_days(q),
        }

    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """Get field priority for e-commerce summaries"""
        # Direct field name priorities for e-commerce
        priorities = {
            'id': 100,
            'order_id': 100,
            'customer_name': 90,
            'name': 90,
            'total': 85,
            'amount': 85,
            'status': 80,
            'order_date': 75,
            'date': 75,
            'payment_method': 70,
            'email': 65,
            'shipping_address': 60,
            'city': 50,
            'country': 45,
        }

        # Check direct field name match
        if field_name in priorities:
            return priorities[field_name]

        # Check field name patterns
        field_lower = field_name.lower()
        if 'id' in field_lower or 'number' in field_lower:
            return 95
        if 'name' in field_lower:
            return 85
        if 'amount' in field_lower or 'total' in field_lower or 'price' in field_lower:
            return 80
        if 'date' in field_lower or 'time' in field_lower:
            return 70
        if 'status' in field_lower or 'state' in field_lower:
            return 75

        return 0
