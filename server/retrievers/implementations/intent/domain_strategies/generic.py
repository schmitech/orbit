"""Generic domain strategy leveraging semantic metadata and extraction hints."""

import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from ..domain import DomainConfig, FieldConfig
from .base import DomainStrategy

logger = logging.getLogger(__name__)


class GenericDomainStrategy(DomainStrategy):
    """Domain strategy that relies on semantic metadata instead of custom logic."""

    def __init__(self, domain_config: Optional[Any] = None):
        if isinstance(domain_config, DomainConfig):
            self.domain_config = domain_config
        else:
            self.domain_config = DomainConfig(domain_config or {})

        self.semantic_extractors: Dict[str, Callable[[str, Dict[str, Any]], Optional[Any]]] = {}
        self._build_semantic_extractors()

    def get_domain_names(self) -> list:
        names = []
        if self.domain_config.domain_name:
            names.append(self.domain_config.domain_name)
        if getattr(self.domain_config, "domain_type", None):
            names.append(self.domain_config.domain_type)
        names.append("generic")
        # Preserve order but remove duplicates
        seen = set()
        ordered = []
        for name in names:
            if name and name not in seen:
                ordered.append(name)
                seen.add(name)
        return ordered

    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate boost based on vocabulary matching and semantic tags."""
        boost = 0.0
        template = template_info.get('template', {})
        query_lower = query.lower()

        # Check semantic tags
        semantic_tags = template.get('semantic_tags', {})
        if semantic_tags:
            # Check action verbs from vocabulary
            action = semantic_tags.get('action')
            if action and hasattr(self.domain_config, 'vocabulary'):
                action_verbs = self.domain_config.vocabulary.get('action_verbs', {})
                if action in action_verbs:
                    for verb in action_verbs[action]:
                        if verb.lower() in query_lower:
                            boost += 0.2
                            break

            # Check entity mentions
            primary_entity = semantic_tags.get('primary_entity')
            if primary_entity:
                # Check entity synonyms
                synonyms = self.domain_config.get_entity_synonyms(primary_entity)
                if any(syn.lower() in query_lower for syn in [primary_entity] + synonyms):
                    boost += 0.1

        # Check for field-specific patterns using extraction hints
        params = template.get('parameters', [])
        for param in params:
            semantic_type = param.get('semantic_type')
            if semantic_type and semantic_type in self.semantic_extractors:
                # Try to extract - if successful, boost the template
                extractor = self.semantic_extractors[semantic_type]
                if extractor(query, param) is not None:
                    boost += 0.15

        return boost

    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return semantic extractors that operate as pattern matchers."""
        # Also include vocabulary-based matchers
        matchers = dict(self.semantic_extractors)

        # Add vocabulary-based pattern matchers
        if hasattr(self.domain_config, 'vocabulary'):
            vocabulary = self.domain_config.vocabulary

            # Add entity matchers
            for entity_name in self.domain_config.entities.keys():
                matchers[f'{entity_name}_pattern'] = lambda q, en=entity_name: self._check_entity_pattern(q, en)

            # Add action matchers
            for action in vocabulary.get('action_verbs', {}).keys():
                matchers[f'{action}_action'] = lambda q, a=action: self._check_action_pattern(q, a)

        return matchers

    def _check_entity_pattern(self, query: str, entity_name: str) -> bool:
        """Check if query mentions an entity or its synonyms."""
        query_lower = query.lower()
        synonyms = self.domain_config.get_entity_synonyms(entity_name)
        return any(term.lower() in query_lower for term in [entity_name] + synonyms)

    def _check_action_pattern(self, query: str, action: str) -> bool:
        """Check if query contains action verbs from vocabulary."""
        if not hasattr(self.domain_config, 'vocabulary'):
            return False

        action_verbs = self.domain_config.vocabulary.get('action_verbs', {}).get(action, [])
        query_lower = query.lower()
        return any(verb.lower() in query_lower for verb in action_verbs)

    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        if not param:
            return None

        param_type = param.get("type") or param.get("data_type", "string")
        entity_name = param.get("entity")
        field_name = param.get("field")

        field_config: Optional[FieldConfig] = None
        if entity_name and field_name and hasattr(self.domain_config, "get_field"):
            field_config = self.domain_config.get_field(entity_name, field_name)

        semantic_type = (
            param.get("semantic_type")
            or (field_config.semantic_type if field_config and field_config.semantic_type else None)
        )

        if semantic_type:
            extractor = self.semantic_extractors.get(semantic_type)
            if extractor:
                value = extractor(query, param)
                if value is not None:
                    return value

        if field_config and field_config.extraction_pattern:
            value = self._extract_with_pattern(query, field_config.extraction_pattern, param_type)
            if value is not None:
                return value

        hints = param.get("extraction_hints") or (
            field_config.extraction_hints if field_config and field_config.extraction_hints else {}
        )
        if hints:
            value = self._extract_with_hints(query, hints, param_type)
            if value is not None:
                return value

        return None

    def get_semantic_extractors(self) -> Dict[str, Callable[[str, Dict[str, Any]], Optional[Any]]]:
        return self.semantic_extractors

    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        if field_config and getattr(field_config, "summary_priority", None) is not None:
            return int(field_config.summary_priority)

        if field_config and getattr(field_config, "semantic_type", None):
            semantic = field_config.semantic_type.lower()
            default_priorities = {
                "identifier": 90,
                "name": 85,
                "status": 80,
                "amount": 75,
                "total": 75,
                "date": 70,
                "email": 65,
                "description": 60,
            }
            for key, priority in default_priorities.items():
                if key in semantic:
                    return priority

        field_lower = field_name.lower()
        if "id" in field_lower:
            return 50
        if "name" in field_lower:
            return 45
        if "date" in field_lower or "time" in field_lower:
            return 35
        if "status" in field_lower:
            return 30

        return 0

    def _build_semantic_extractors(self) -> None:
        """Build semantic extractors from configuration and add built-in extractors."""
        # Add built-in extractors for common semantic types
        self.semantic_extractors.update(self._get_builtin_extractors())

        # Override with domain-specific extractors from config
        if not getattr(self.domain_config, "semantic_types", None):
            return

        for semantic_type, config in self.domain_config.semantic_types.items():
            extractor = self._create_pattern_extractor(config)
            if extractor:
                self.semantic_extractors[semantic_type] = extractor

    def _extract_with_pattern(self, query: str, pattern: str, param_type: str) -> Optional[Any]:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:  # pragma: no cover - defensive guard
            logger.debug("Invalid extraction pattern '%s' skipped", pattern)
            return None

        match = compiled.search(query)
        if not match:
            return None

        value_str = match.group(1) if match.groups() else match.group(0)
        return self._parse_value(value_str, param_type)

    def _extract_with_hints(self, query: str, hints: Dict[str, Any], param_type: str) -> Optional[Any]:
        query_lower = query.lower()

        for regex_pattern in hints.get("regex_patterns", []):
            try:
                regex = re.compile(regex_pattern, re.IGNORECASE)
            except re.error:
                logger.debug("Invalid hint regex '%s' skipped", regex_pattern)
                continue
            match = regex.search(query)
            if match:
                group_index = hints.get("value_group", 1)
                try:
                    value_str = match.group(group_index)
                except IndexError:
                    value_str = match.group(0)
                return self._parse_value(value_str, param_type)

        for pattern in hints.get("patterns", []):
            regex = re.compile(rf"\b{re.escape(pattern)}\b\s*[:=]?\s*([^\s,]+)", re.IGNORECASE)
            match = regex.search(query)
            if match:
                return self._parse_value(match.group(1), param_type)

        if hints.get("look_for_quotes"):
            quoted = re.search(r'"([^"]+)"', query)
            if not quoted:
                quoted = re.search(r"'([^']+)'", query)
            if quoted:
                value_str = quoted.group(1)
                parsed = self._parse_value(value_str, param_type)
                if parsed is not None:
                    return parsed

        if hints.get("capitalization_required"):
            capitalized = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", query)
            if capitalized:
                parsed = self._parse_value(capitalized.group(1), param_type)
                if parsed is not None:
                    return parsed

        if hints.get("numeric_required"):
            numeric = re.search(r"\b\d+[\d,]*\b", query)
            if numeric:
                return self._parse_value(numeric.group(0), param_type)

        if hints.get("relative_terms"):
            for term in hints["relative_terms"]:
                if term.lower() in query_lower:
                    return term

        if hints.get("formats"):
            for formatted_value in self._extract_formatted_values(query, hints["formats"]):
                parsed = self._parse_value(formatted_value, param_type)
                if parsed is not None:
                    return parsed

        return None

    def _extract_formatted_values(self, query: str, formats: Any) -> list:
        results = []
        if not formats:
            return results

        date_patterns = {
            "YYYY-MM-DD": r"\b\d{4}-\d{2}-\d{2}\b",
            "DD-MM-YYYY": r"\b\d{2}-\d{2}-\d{4}\b",
            "MM/DD/YYYY": r"\b\d{2}/\d{2}/\d{4}\b",
            "Month DD, YYYY": r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
        }

        for fmt in formats:
            pattern = date_patterns.get(fmt)
            if pattern:
                matches = re.findall(pattern, query)
                results.extend(matches)
        return results

    def _create_pattern_extractor(self, config: Dict[str, Any]) -> Optional[Callable[[str, Dict[str, Any]], Optional[Any]]]:
        if not isinstance(config, dict):
            return None

        simple_patterns = config.get("patterns", []) or []
        regex_patterns = config.get("regex_patterns", []) or []
        value_group = config.get("value_group") or config.get("capture_group", 1)

        compiled_regex = []
        for pattern in regex_patterns:
            try:
                compiled_regex.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                logger.debug("Invalid semantic regex '%s' skipped", pattern)

        def extractor(query: str, param: Dict[str, Any]) -> Optional[Any]:
            param_type = param.get("type") or param.get("data_type", "string")

            for regex in compiled_regex:
                match = regex.search(query)
                if match:
                    try:
                        value_str = match.group(value_group)
                    except IndexError:
                        value_str = match.group(0)
                    return self._parse_value(value_str, param_type)

            for pattern in simple_patterns:
                regex = re.compile(rf"\b{re.escape(pattern)}\b\s*[:=]?\s*([^\s,]+)", re.IGNORECASE)
                match = regex.search(query)
                if match:
                    return self._parse_value(match.group(1), param_type)

            return None

        return extractor

    def _parse_value(self, value_str: str, param_type: str) -> Optional[Any]:
        if value_str is None:
            return None

        value_str = value_str.strip()
        if not value_str:
            return None

        param_type = (param_type or "string").lower()

        try:
            if param_type in {"integer", "int"}:
                clean = value_str.replace(",", "").replace("$", "")
                return int(clean)
            if param_type in {"decimal", "float", "number"}:
                clean = value_str.replace(",", "").replace("$", "")
                return float(clean)
            if param_type in {"date", "datetime"}:
                parsed_date = self._parse_date(value_str)
                return parsed_date or value_str
            if param_type == "boolean":
                lower = value_str.lower()
                if lower in {"true", "yes", "1", "active", "enabled"}:
                    return True
                if lower in {"false", "no", "0", "inactive", "disabled"}:
                    return False
                return None
            clean_value = value_str.strip()
            if len(clean_value) >= 2 and clean_value[0] == clean_value[-1] and clean_value[0] in {'"', "'"}:
                clean_value = clean_value[1:-1]
            return clean_value
        except (ValueError, TypeError):  # pragma: no cover - defensive
            return None

    def _parse_date(self, value: str) -> Optional[str]:
        formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%B %d %Y",
            "%b %d %Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        cleaned = re.sub(r"(st|nd|rd|th)", "", value.replace(",", ""), flags=re.IGNORECASE)
        for fmt in formats:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _get_builtin_extractors(self) -> Dict[str, Callable[[str, Dict[str, Any]], Optional[Any]]]:
        """Return built-in semantic extractors for common types."""
        return {
            # Identifier patterns
            "identifier": self._extract_identifier,
            "order_identifier": self._extract_order_identifier,
            "customer_identifier": self._extract_customer_identifier,

            # Monetary patterns
            "monetary_amount": self._extract_monetary_amount,
            "transaction_amount": self._extract_monetary_amount,

            # Time patterns
            "time_period_days": self._extract_time_period_days,
            "date_value": self._extract_date_value,
            "date_range": self._extract_date_range,

            # Person/entity patterns
            "person_name": self._extract_person_name,
            "email_address": self._extract_email,
            "phone_number": self._extract_phone,

            # Location patterns
            "city_name": self._extract_city,
            "country_name": self._extract_country,

            # Status/enum patterns
            "status_value": self._extract_status_value,
            "enum_value": self._extract_enum_value,

            # Quantity patterns
            "quantity": self._extract_quantity,
            "percentage": self._extract_percentage,
        }

    def _extract_identifier(self, query: str, param: Dict[str, Any]) -> Optional[Any]:
        """Extract generic identifier (numeric ID)."""
        param_name = param.get('name', '').lower()
        param_type = param.get('type') or param.get('data_type', 'string')

        # Look for patterns like "ID 123", "#123", "number 123"
        patterns = [
            r'(?:id|number|#)\s*(\d+)',
            r'\b(\d{4,})\b',  # Any 4+ digit number
        ]

        for pattern in patterns:
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

    def _extract_order_identifier(self, query: str, param: Dict[str, Any]) -> Optional[Any]:
        """Extract order-specific identifiers."""
        param_type = param.get('type') or param.get('data_type', 'string')

        # Check if looking for multiple IDs
        if 'ids' in param.get('name', '').lower():
            return self._extract_multiple_ids(query, 'order')

        patterns = [
            r'order\s+(?:number\s+|#\s*|id\s+)?(\d+)',
            r'#\s*(\d+)',
            r'(?:order|id|number)\s+(\d+)',
            r'\b(\d{4,})\b',
        ]

        for pattern in patterns:
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

    def _extract_customer_identifier(self, query: str, param: Dict[str, Any]) -> Optional[Any]:
        """Extract customer-specific identifiers."""
        param_type = param.get('type') or param.get('data_type', 'string')

        patterns = [
            r'customer\s+(?:number\s+|#\s*|id\s+)?(\d+)',
            r'customer\s*(\d{3,})',
            r'customer_id\s*(\d+)',
        ]

        for pattern in patterns:
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

    def _extract_monetary_amount(self, query: str, param: Dict[str, Any]) -> Optional[Any]:
        """Extract monetary amounts."""
        param_type = param.get('type') or param.get('data_type', 'string')

        patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $500, $1,000.50
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?|usd)',  # 500 dollars
            r'(?:above|below|over|under|than|exceeds?|less than|greater than)\s+\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\b(?!\s*days?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    if param_type in {'integer', 'int'}:
                        return int(float(amount_str))
                    return float(amount_str)
                except ValueError:
                    continue
        return None

    def _extract_time_period_days(self, query: str, param: Dict[str, Any]) -> Optional[int]:
        """Extract time periods in days."""
        # Specific day patterns
        days_patterns = [
            r'(?:last|past|previous|within)\s+(\d+)\s+days?',
            r'(\d+)\s+days?\s+(?:ago|back)',
            r'(?:in|within)\s+(?:the\s+)?(?:last|past)\s+(\d+)\s+days?',
        ]

        for pattern in days_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Special time period words
        time_mappings = {
            'today': 1,
            'yesterday': 1,
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
        }

        query_lower = query.lower()
        for period, days in time_mappings.items():
            if period in query_lower:
                return days

        return None

    def _extract_date_value(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract specific date values."""
        # Look for explicit date formats
        date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',  # YYYY-MM-DD
            r'\b(\d{2}/\d{2}/\d{4})\b',  # MM/DD/YYYY
            r'\b(\d{2}-\d{2}-\d{4})\b',  # DD-MM-YYYY
            r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return self._parse_date(match.group(1))

        # Handle relative dates
        from datetime import datetime, timedelta
        today = datetime.now()

        relative_mappings = {
            'today': today,
            'yesterday': today - timedelta(days=1),
            'tomorrow': today + timedelta(days=1),
        }

        query_lower = query.lower()
        for term, date in relative_mappings.items():
            if term in query_lower:
                return date.strftime('%Y-%m-%d')

        return None

    def _extract_date_range(self, query: str, param: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Extract date ranges."""
        # Look for "from DATE to DATE" patterns
        range_pattern = r'(?:from|between)\s+(.*?)\s+(?:to|and|through)\s+(.*?)(?:\s|$)'
        match = re.search(range_pattern, query, re.IGNORECASE)

        if match:
            start_str = match.group(1)
            end_str = match.group(2)

            # Try to parse both dates
            start_date = self._extract_date_value(start_str, {})
            end_date = self._extract_date_value(end_str, {})

            if start_date and end_date:
                return {'start': start_date, 'end': end_date}

        return None

    def _extract_person_name(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract person names."""
        # Check for quoted names first
        quoted = re.search(r'["\']([^"\'\']+)["\']', query)
        if quoted:
            name = quoted.group(1)
            # Basic validation: should have at least 2 parts for a full name
            if ' ' in name:
                return name

        # Look for capitalized consecutive words
        capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', query)
        if capitalized:
            # Filter out common non-name patterns
            for name in capitalized:
                if not any(skip in name.lower() for skip in ['new york', 'san francisco', 'los angeles']):
                    return name

        # Look for patterns with titles
        title_pattern = r'\b(?:mr|mrs|ms|dr|prof)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        match = re.search(title_pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

        # Look for "from NAME NAME" pattern
        from_pattern = r'from\s+([A-Z][a-z]+\s+[A-Z][a-z]+)'
        match = re.search(from_pattern, query)
        if match:
            return match.group(1)

        return None

    def _extract_email(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract email addresses."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, query)
        if match:
            return match.group(0)
        return None

    def _extract_phone(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract phone numbers."""
        phone_patterns = [
            r'\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b',  # 123-456-7890
            r'\b\((\d{3})\)\s?(\d{3})[-.\s]?(\d{4})\b',  # (123) 456-7890
            r'\b(\d{10})\b',  # 1234567890
        ]

        for pattern in phone_patterns:
            match = re.search(pattern, query)
            if match:
                if len(match.groups()) > 1:
                    # Reconstruct from groups
                    return ''.join(match.groups())
                return match.group(1)
        return None

    def _extract_city(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract city names."""
        # Look for city indicators
        city_patterns = [
            r'(?:in|from|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)(?:\s+city)?',
            r'city\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'located\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]

        for pattern in city_patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1)

        return None

    def _extract_country(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract country names."""
        # This would ideally use a country list
        # For now, just look for capitalized words after "country" or common patterns
        country_patterns = [
            r'country\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'from\s+([A-Z][a-z]+)\s+(?:customers?|orders?|users?)',
        ]

        for pattern in country_patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1)

        return None

    def _extract_status_value(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract status values based on field configuration."""
        # Get entity and field info
        entity_name = param.get('entity')
        field_name = param.get('field')

        if entity_name and field_name:
            field_config = self.domain_config.get_field(entity_name, field_name)
            if field_config and hasattr(field_config, 'enum_values') and field_config.enum_values:
                query_lower = query.lower()
                for status in field_config.enum_values:
                    if status.lower() in query_lower:
                        return status

        # Generic status patterns
        common_statuses = ['pending', 'active', 'completed', 'cancelled', 'failed',
                          'processing', 'shipped', 'delivered', 'approved', 'rejected']
        query_lower = query.lower()
        for status in common_statuses:
            if status in query_lower:
                return status

        return None

    def _extract_enum_value(self, query: str, param: Dict[str, Any]) -> Optional[str]:
        """Extract enum values from configured options."""
        # Similar to status but more generic
        return self._extract_status_value(query, param)

    def _extract_quantity(self, query: str, param: Dict[str, Any]) -> Optional[Any]:
        """Extract quantity values."""
        param_type = param.get('type') or param.get('data_type', 'string')

        patterns = [
            r'(\d+)\s*(?:units?|pieces?|items?|qty)',
            r'quantity\s+(?:of\s+)?(\d+)',
            r'(\d+)\s+(?:in\s+)?(?:stock|inventory|available)',
        ]

        for pattern in patterns:
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

    def _extract_percentage(self, query: str, param: Dict[str, Any]) -> Optional[float]:
        """Extract percentage values."""
        patterns = [
            r'(\d+(?:\.\d+)?)\s*%',  # 50%, 12.5%
            r'(\d+(?:\.\d+)?)\s*percent',  # 50 percent
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _extract_multiple_ids(self, query: str, entity_type: str) -> Optional[str]:
        """Extract multiple IDs (comma-separated or ranges)."""
        # Look for comma-separated IDs
        ids_pattern = rf'{entity_type}s?\s+(\d+(?:\s*,\s*\d+)+)'
        match = re.search(ids_pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).replace(' ', '')

        # Check for ranges
        range_patterns = [
            r'(\d+)\s+(?:to|through|-)\s+(\d+)',
            r'between\s+(\d+)\s+and\s+(\d+)',
        ]

        for pattern in range_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                start, end = match.groups()
                start_int = int(start)
                end_int = int(end)
                if end_int - start_int <= 100:  # Limit range size
                    ids = ','.join(str(i) for i in range(start_int, end_int + 1))
                    return ids
                return f"{start},{end}"  # Just return endpoints for large ranges

        # Check for single ID to return as string
        single_pattern = rf'{entity_type}\s+(?:number\s+|#\s*|id\s+)?(\d+)'
        match = re.search(single_pattern, query, re.IGNORECASE)
        if match:
            return str(match.group(1))

        return None
