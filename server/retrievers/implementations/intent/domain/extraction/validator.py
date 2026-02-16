"""
Validator for extracted parameter values
"""

import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from ...domain import DomainConfig

logger = logging.getLogger(__name__)


class Validator:
    """Validates extracted parameter values against domain rules"""

    def __init__(self, domain_config: DomainConfig):
        """Initialize validator with domain configuration"""
        self.domain_config = domain_config

    def validate(self, value: Any, entity_name: str, field_name: str) -> tuple[bool, Optional[str]]:
        """
        Validate a value for a specific field.

        Returns:
            Tuple of (is_valid, error_message)
        """
        field = self.domain_config.get_field(entity_name, field_name)
        if not field:
            return True, None  # No field config means no validation

        # Check data type
        if not self._validate_type(value, field.data_type):
            return False, f"Invalid type for {field_name}: expected {field.data_type}"

        # Check validation rules
        if field.validation_rules:
            return self._validate_rules(value, field.validation_rules, field_name)

        return True, None

    def _validate_type(self, value: Any, data_type: str) -> bool:
        """Validate value matches expected data type"""
        if value is None:
            return True  # None is valid for optional fields

        type_validators = {
            'integer': lambda v: isinstance(v, int) or (isinstance(v, str) and v.isdigit()),
            'decimal': lambda v: isinstance(v, (int, float)),
            'string': lambda v: isinstance(v, str),
            'boolean': lambda v: isinstance(v, bool),
            'date': lambda v: self._is_valid_date(v),
            'datetime': lambda v: self._is_valid_datetime(v),
            'email': lambda v: self._is_valid_email(v),
            'phone': lambda v: self._is_valid_phone(v),
        }

        validator = type_validators.get(data_type, lambda v: True)
        return validator(value)

    def _validate_rules(self, value: Any, rules: Dict[str, Any], field_name: str) -> tuple[bool, Optional[str]]:
        """Validate value against specific rules"""
        # Check min/max for numeric values
        if 'min' in rules and isinstance(value, (int, float)):
            if value < rules['min']:
                return False, f"{field_name} must be at least {rules['min']}"

        if 'max' in rules and isinstance(value, (int, float)):
            if value > rules['max']:
                return False, f"{field_name} must be at most {rules['max']}"

        # Check length for strings
        if 'min_length' in rules and isinstance(value, str):
            if len(value) < rules['min_length']:
                return False, f"{field_name} must be at least {rules['min_length']} characters"

        if 'max_length' in rules and isinstance(value, str):
            if len(value) > rules['max_length']:
                return False, f"{field_name} must be at most {rules['max_length']} characters"

        # Check pattern matching
        if 'pattern' in rules and isinstance(value, str):
            pattern = re.compile(rules['pattern'])
            if not pattern.match(value):
                pattern_desc = rules.get('pattern_description', 'required format')
                return False, f"{field_name} does not match {pattern_desc}"

        # Check allowed values (enum)
        if 'allowed_values' in rules:
            if value not in rules['allowed_values']:
                allowed = ', '.join(str(v) for v in rules['allowed_values'])
                return False, f"{field_name} must be one of: {allowed}"

        # Check required
        if rules.get('required', False) and value is None:
            return False, f"{field_name} is required"

        # Custom validation function
        if 'custom' in rules:
            try:
                custom_valid = rules['custom'](value)
                if not custom_valid:
                    return False, f"{field_name} failed custom validation"
            except Exception as e:
                logger.error(f"Custom validation error for {field_name}: {e}")
                return False, f"{field_name} validation error"

        return True, None

    def _is_valid_date(self, value: Any) -> bool:
        """Check if value is a valid date"""
        if isinstance(value, date):
            return True

        if isinstance(value, str):
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return True
            except ValueError:
                pass

        return False

    def _is_valid_datetime(self, value: Any) -> bool:
        """Check if value is a valid datetime"""
        if isinstance(value, datetime):
            return True

        if isinstance(value, str):
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    datetime.strptime(value, fmt)
                    return True
                except ValueError:
                    continue

        return False

    def _is_valid_email(self, value: Any) -> bool:
        """Check if value is a valid email"""
        if not isinstance(value, str):
            return False

        email_pattern = re.compile(
            r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
        )
        return bool(email_pattern.match(value))

    def _is_valid_phone(self, value: Any) -> bool:
        """Check if value is a valid phone number"""
        if not isinstance(value, str):
            return False

        # Remove common separators
        clean_phone = re.sub(r'[\s\-\(\)\.]', '', value)

        # Check if it's all digits (optionally with leading +)
        if clean_phone.startswith('+'):
            clean_phone = clean_phone[1:]

        return clean_phone.isdigit() and 10 <= len(clean_phone) <= 15

    def validate_all(self, parameters: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate all parameters.

        Returns:
            Dictionary of field names to error messages (empty if all valid)
        """
        errors = {}

        for key, value in parameters.items():
            if '.' in key:
                entity_name, field_name = key.split('.', 1)
                is_valid, error_msg = self.validate(value, entity_name, field_name)

                if not is_valid and error_msg:
                    if field_name not in errors:
                        errors[field_name] = []
                    errors[field_name].append(error_msg)

        return errors

    def sanitize(self, value: Any, entity_name: str, field_name: str) -> Any:
        """Sanitize and normalize a value for a field"""
        field = self.domain_config.get_field(entity_name, field_name)
        if not field:
            return value

        # Sanitize based on data type
        if field.data_type == 'string':
            if isinstance(value, str):
                # Remove leading/trailing whitespace
                value = value.strip()

                # Apply max length if specified
                if field.validation_rules.get('max_length'):
                    max_len = field.validation_rules['max_length']
                    value = value[:max_len]

        elif field.data_type == 'email' and isinstance(value, str):
            # Normalize email to lowercase
            value = value.lower().strip()

        elif field.data_type == 'phone' and isinstance(value, str):
            # Normalize phone number format
            value = re.sub(r'[\s\-\(\)\.]', '', value)

        return value