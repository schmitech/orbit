"""
Value extractor for applying patterns and parsing user input
"""

import re
import logging
from typing import Dict, Any, Optional, List, Tuple, Pattern
from datetime import datetime, date
from ...domain import DomainConfig, FieldConfig

logger = logging.getLogger(__name__)


class ValueExtractor:
    """Extracts values from user queries using patterns"""

    def __init__(self, domain_config: DomainConfig, patterns: Dict[str, Pattern]):
        """Initialize value extractor with patterns"""
        self.domain_config = domain_config
        self.patterns = patterns

    def extract_value(self, user_query: str, entity_name: str, field_name: str,
                      data_type: str) -> Optional[Any]:
        """Extract a value for a specific field from the query"""
        pattern_key = f"{entity_name}.{field_name}"

        # Try specific pattern extraction first
        if pattern_key in self.patterns:
            value = self._extract_with_pattern(user_query, self.patterns[pattern_key], data_type)
            if value is not None:
                return value

        # Try range extraction for numeric fields
        if data_type in ['integer', 'decimal']:
            range_value = self._extract_range(user_query, entity_name, field_name, data_type)
            if range_value:
                return range_value

        # Try context-based extraction
        return self._extract_from_context(user_query, entity_name, field_name, data_type)

    def _extract_with_pattern(self, text: str, pattern: Pattern, data_type: str) -> Optional[Any]:
        """Extract value using a specific pattern"""
        match = pattern.search(text)
        if match:
            # Get the last group (usually the value)
            value_str = match.groups()[-1] if match.groups() else match.group(0)
            return self._parse_value(value_str, data_type)
        return None

    def _extract_range(self, user_query: str, entity_name: str, field_name: str,
                       data_type: str) -> Optional[Dict[str, Any]]:
        """Extract range values for numeric fields"""
        range_pattern_key = f"{entity_name}.{field_name}_range"
        if range_pattern_key not in self.patterns:
            return None

        pattern = self.patterns[range_pattern_key]
        match = pattern.search(user_query)

        if match and len(match.groups()) >= 2:
            min_val = self._parse_value(match.group(1), data_type)
            max_val = self._parse_value(match.group(2), data_type)

            if min_val is not None and max_val is not None:
                return {'min': min_val, 'max': max_val}

        return None

    def _extract_from_context(self, user_query: str, entity_name: str, field_name: str,
                               data_type: str) -> Optional[Any]:
        """Extract value from context using field synonyms and context clues"""
        field = self.domain_config.get_field(entity_name, field_name)
        if not field:
            return None

        # Get field synonyms
        field_synonyms = self.domain_config.get_field_synonyms(field_name)
        search_terms = [field_name] + field_synonyms

        for term in search_terms:
            # Look for patterns like "field_name: value" or "field_name = value"
            context_patterns = [
                rf"{term}\s*[:=]\s*([^\s,]+)",
                rf"{term}\s+(?:is|equals?|of)\s+([^\s,]+)"
            ]

            for pattern_str in context_patterns:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                match = pattern.search(user_query)
                if match:
                    value_str = match.group(1)
                    value = self._parse_value(value_str, data_type)
                    if value is not None:
                        return value

        return None

    def _parse_value(self, value_str: str, data_type: str) -> Optional[Any]:
        """Parse a string value into the appropriate data type"""
        if not value_str:
            return None

        try:
            if data_type == "integer":
                # Remove currency symbols and commas
                clean_str = value_str.replace('$', '').replace(',', '').strip()
                return int(clean_str)

            elif data_type == "decimal":
                # Remove currency symbols and commas
                clean_str = value_str.replace('$', '').replace(',', '').strip()
                return float(clean_str)

            elif data_type == "date":
                return self._parse_date(value_str)

            elif data_type == "boolean":
                return self._parse_boolean(value_str)

            else:  # string or other types
                return value_str.strip()

        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse '{value_str}' as {data_type}: {e}")
            return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string into ISO format"""
        date_formats = [
            "%Y-%m-%d",  # ISO format
            "%m/%d/%Y",  # US format
            "%m-%d-%Y",  # Alternative format
            "%d/%m/%Y",  # European format
            "%d-%m-%Y",  # Alternative European
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    def _parse_boolean(self, value_str: str) -> Optional[bool]:
        """Parse boolean values"""
        value_lower = value_str.lower().strip()
        if value_lower in ['true', 'yes', '1', 'active', 'enabled']:
            return True
        elif value_lower in ['false', 'no', '0', 'inactive', 'disabled']:
            return False
        return None

    def extract_all_values(self, user_query: str) -> Dict[str, Any]:
        """Extract all possible values from the query"""
        extracted = {}

        for entity_name, entity in self.domain_config.entities.items():
            for field_name, field in entity.fields.items():
                if field.searchable or field.filterable:
                    value = self.extract_value(
                        user_query, entity_name, field_name, field.data_type
                    )
                    if value is not None:
                        key = f"{entity_name}.{field_name}"
                        extracted[key] = value

        return extracted

    def extract_template_parameter(self, user_query: str, param: Dict) -> Optional[Any]:
        """
        Extract a template parameter that may not be tied to a domain entity.
        This handles common parameter patterns like amounts, dates, time periods, etc.
        """
        param_name = param.get('name', '')
        param_type = param.get('type') or param.get('data_type', 'string')

        # Handle order ID parameters
        if 'order' in param_name.lower() and ('id' in param_name.lower() or 'number' in param_name.lower()):
            # Look for order IDs/numbers
            order_patterns = [
                r'order\s+(?:number\s+|#\s*|id\s+)?(\d+)',  # order 12345, order #12345, order number 12345
                r'#\s*(\d+)',  # #12345
                r'(?:order|id|number)\s+(\d+)',  # various patterns
                r'\b(\d{4,})\b',  # any 4+ digit number (fallback)
            ]

            for pattern in order_patterns:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    try:
                        return int(match.group(1))
                    except ValueError:
                        continue

        # Handle multiple order IDs (or single ID for order_ids parameter)
        if 'order_ids' in param_name.lower() or (param_name == 'order_ids'):
            # Look for comma-separated IDs or ranges
            ids_patterns = [
                r'orders?\s+(\d+(?:\s*,\s*\d+)+)',  # orders 123, 456, 789
                r'(\d+)\s+(?:to|through|-)\s+(\d+)',  # 100 to 200, 100-200
                r'between\s+(\d+)\s+and\s+(\d+)',  # between 100 and 200
            ]

            # Check for comma-separated list
            for pattern in [r'orders?\s+(\d+(?:\s*,\s*\d+)+)']:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    return match.group(1).replace(' ', '')

            # Check for ranges
            for pattern in [r'(\d+)\s+(?:to|through|-)\s+(\d+)', r'between\s+(\d+)\s+and\s+(\d+)']:
                match = re.search(pattern, user_query, re.IGNORECASE)
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
            # Look for single order patterns
            single_patterns = [
                r'order\s+(?:number\s+|#\s*|id\s+)?(\d+)',  # order 12345
                r'#\s*(\d+)',  # #12345
                r'(?:find|show|get|lookup|pull)\s+(?:order\s+)?(\d+)',  # various patterns
            ]

            for pattern in single_patterns:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    # Return as string for order_ids parameter
                    return str(match.group(1))

        # Handle amount parameters (min_amount, max_amount, etc.)
        if 'amount' in param_name.lower():
            # Look for currency amounts like $500, 500 dollars, etc.
            amount_patterns = [
                r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $500, $1,000.50
                r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?|usd)',  # 500 dollars
                r'(?:above|below|over|under|than|exceeds?|less than|greater than)\s+\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\b(?!\s*days?)',  # over $500 but not "500 days"
            ]

            for pattern in amount_patterns:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    amount_str = match.group(1).replace(',', '')
                    try:
                        if param_type == 'integer':
                            return int(float(amount_str))
                        else:
                            return float(amount_str)
                    except ValueError:
                        continue

        # Handle days_back, days_inactive, etc.
        if 'days' in param_name.lower():
            # Look for patterns like "7 days", "last 30 days", "past week", etc.
            days_patterns = [
                r'(?:last|past|previous|within)\s+(\d+)\s+days?',  # last 7 days
                r'(\d+)\s+days?\s+(?:ago|back)',  # 7 days ago
                r'(?:in|within)\s+(?:the\s+)?(?:last|past)\s+(\d+)\s+days?',  # in the last 30 days
            ]

            for pattern in days_patterns:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            # Also handle special time period words
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

            # Check for time period words (more specific patterns first)
            query_lower = user_query.lower()
            for period, days in time_mappings.items():
                if period in query_lower:
                    return days

        # Handle date parameters
        if param_type == 'date':
            # Look for date patterns
            date_patterns = [
                r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
                r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
                r'(\d{2}-\d{2}-\d{4})',  # DD-MM-YYYY
                # Month names
                r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?',
            ]

            for pattern in date_patterns:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    # For simplicity, return the matched string
                    # In production, you'd parse and normalize this
                    return match.group(0)

        # Handle enum/status parameters
        if param_type == 'enum' and 'allowed_values' in param:
            allowed = param['allowed_values']
            for value in allowed:
                if value.lower() in user_query.lower():
                    return value

        # Handle generic string parameters
        if param_type == 'string':
            # For customer names, emails, etc.
            if 'email' in param_name.lower():
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                match = re.search(email_pattern, user_query)
                if match:
                    return match.group(0)

            # For names (this is a simple heuristic)
            if 'name' in param_name.lower():
                # Look for quoted names or proper nouns
                quoted_pattern = r'"([^"]+)"'
                match = re.search(quoted_pattern, user_query)
                if match:
                    return match.group(1)

                # Look for capitalized words that might be names
                # This is very basic and would need improvement
                name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
                match = re.search(name_pattern, user_query)
                if match:
                    return match.group(1)

        return None