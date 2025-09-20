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