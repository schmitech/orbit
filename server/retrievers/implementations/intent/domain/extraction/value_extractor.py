"""
Value extractor for applying patterns and parsing user input
"""

import re
import logging
from typing import Dict, Any, Optional, Pattern
from datetime import datetime
from ...domain import DomainConfig

logger = logging.getLogger(__name__)


class ValueExtractor:
    """Extracts values from user queries using patterns"""

    def __init__(self, domain_config: DomainConfig, patterns: Dict[str, Pattern], domain_strategy=None):
        """Initialize value extractor with patterns and optional domain strategy"""
        self.domain_config = domain_config
        self.patterns = patterns
        self.domain_strategy = domain_strategy

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

        if self.domain_strategy and entity_name and field_name:
            param_context = self._build_field_param_context(entity_name, field_name, data_type)
            value = self.domain_strategy.extract_domain_parameters(
                user_query,
                param_context,
                self.domain_config
            )
            if value is not None:
                return value

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

    def _build_field_param_context(self, entity_name: str, field_name: str, data_type: str) -> Dict[str, Any]:
        """Build a template-like parameter definition for an entity field"""
        param_context = {
            'name': field_name,
            'entity': entity_name,
            'field': field_name,
            'type': data_type,
            'data_type': data_type,
        }

        field_config = self.domain_config.get_field(entity_name, field_name)
        if field_config:
            if field_config.semantic_type and 'semantic_type' not in param_context:
                param_context['semantic_type'] = field_config.semantic_type
            if field_config.extraction_hints and 'extraction_hints' not in param_context:
                param_context['extraction_hints'] = field_config.extraction_hints
        return param_context

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
        Extract a template parameter - delegates to domain strategy when available.
        Falls back to generic extraction for common patterns.
        """
        # First try domain strategy if available
        if self.domain_strategy:
            value = self.domain_strategy.extract_domain_parameters(
                user_query, param, self.domain_config
            )
            if value is not None:
                return value

        # Fall back to generic extraction for common types
        return self._extract_generic_parameter(user_query, param)

    def _extract_generic_parameter(self, user_query: str, param: Dict) -> Optional[Any]:
        """Generic parameter extraction for common types without domain-specific logic"""
        param_name = param.get('name', '')
        param_type = param.get('type') or param.get('data_type', 'string')

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
            # For emails
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
