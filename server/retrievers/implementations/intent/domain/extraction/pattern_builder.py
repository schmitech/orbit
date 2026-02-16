"""
Pattern builder for constructing regex patterns for domain fields
"""

import re
import logging
from typing import Dict, Optional, Pattern
from ...domain import DomainConfig, FieldConfig

logger = logging.getLogger(__name__)


class PatternBuilder:
    """Builds regex patterns for domain field extraction"""

    def __init__(self, domain_config: DomainConfig):
        """Initialize pattern builder with domain configuration"""
        self.domain_config = domain_config
        self.patterns: Dict[str, Pattern] = {}

    def build_patterns(self) -> Dict[str, Pattern]:
        """Build all patterns for the domain"""
        for entity_name, entity in self.domain_config.entities.items():
            for field_name, field_config in entity.fields.items():
                if self._should_create_pattern(field_config):
                    pattern_key = f"{entity_name}.{field_name}"
                    pattern = self._build_pattern_for_field(entity_name, field_config)
                    if pattern:
                        self.patterns[pattern_key] = pattern

                    # Add range pattern for numeric fields
                    if field_config.data_type in ['integer', 'decimal']:
                        range_pattern = self._build_range_pattern(field_config)
                        if range_pattern:
                            self.patterns[f"{pattern_key}_range"] = range_pattern

        return self.patterns

    def _should_create_pattern(self, field: FieldConfig) -> bool:
        """Check if a pattern should be created for this field"""
        return field.searchable or field.filterable

    def _build_pattern_for_field(self, entity_name: str, field: FieldConfig) -> Optional[Pattern]:
        """Build pattern for a specific field based on its type"""
        field_lower = field.name.lower()

        # ID fields
        if field.data_type == "integer" and "id" in field_lower:
            return self._build_id_pattern(entity_name, field)

        # Email fields
        if field.data_type == "string" and field.name == "email":
            return self._build_email_pattern()

        # Numeric fields
        if field.data_type in ["decimal", "integer"]:
            return self._build_numeric_pattern(field)

        # Date fields
        if field.data_type == "date":
            return self._build_date_pattern()

        # Phone fields
        if field.data_type == "string" and "phone" in field_lower:
            return self._build_phone_pattern()

        return None

    def _build_id_pattern(self, entity_name: str, field: FieldConfig) -> Pattern:
        """Build pattern for ID fields"""
        entity_synonyms = self.domain_config.get_entity_synonyms(entity_name)
        entity_patterns = [entity_name] + entity_synonyms

        entity_options = '|'.join(re.escape(p) for p in entity_patterns)
        pattern_str = rf"({entity_options})\s*(?:id\s*)?(?:#|number|id)?\s*(\d+)"

        return re.compile(pattern_str, re.IGNORECASE)

    def _build_email_pattern(self) -> Pattern:
        """Build pattern for email fields"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return re.compile(email_pattern, re.IGNORECASE)

    def _build_numeric_pattern(self, field: FieldConfig) -> Pattern:
        """Build pattern for numeric fields"""
        if field.data_type == "decimal":
            pattern = r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)'
        else:  # integer
            pattern = r'\$?\s*(\d{1,3}(?:,\d{3})*)'

        return re.compile(pattern, re.IGNORECASE)

    def _build_range_pattern(self, field: FieldConfig) -> Pattern:
        """Build range pattern for numeric fields"""
        if field.data_type == "decimal":
            pattern = r'between\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*and\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)'
        else:  # integer
            pattern = r'between\s*\$?\s*(\d{1,3}(?:,\d{3})*)\s*and\s*\$?\s*(\d{1,3}(?:,\d{3})*)'

        return re.compile(pattern, re.IGNORECASE)

    def _build_date_pattern(self) -> Pattern:
        """Build pattern for date fields"""
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # ISO format: 2024-01-31
            r'\d{2}/\d{2}/\d{4}',  # US format: 01/31/2024
            r'\d{2}-\d{2}-\d{4}',  # Alternative: 01-31-2024
        ]

        combined_pattern = '|'.join(f'({p})' for p in date_patterns)
        return re.compile(combined_pattern)

    def _build_phone_pattern(self) -> Pattern:
        """Build pattern for phone fields"""
        phone_patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # (123) 456-7890, 123-456-7890
            r'\+?1?\s*\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',  # +1 123 456 7890
        ]

        combined_pattern = '|'.join(f'({p})' for p in phone_patterns)
        return re.compile(combined_pattern, re.IGNORECASE)

    def get_pattern(self, entity_name: str, field_name: str) -> Optional[Pattern]:
        """Get pattern for a specific field"""
        pattern_key = f"{entity_name}.{field_name}"
        return self.patterns.get(pattern_key)

    def get_range_pattern(self, entity_name: str, field_name: str) -> Optional[Pattern]:
        """Get range pattern for a specific numeric field"""
        pattern_key = f"{entity_name}.{field_name}_range"
        return self.patterns.get(pattern_key)