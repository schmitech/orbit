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
        """Parse date string into ISO format.

        Uses domain config date_format preference to disambiguate US vs European formats.
        """
        # Check domain config for preferred date format
        date_format_preference = getattr(self.domain_config, 'date_format', 'us')

        if date_format_preference == 'european':
            date_formats = [
                "%Y-%m-%d",  # ISO format (unambiguous)
                "%d/%m/%Y",  # European format
                "%d-%m-%Y",  # Alternative European
                "%m/%d/%Y",  # US format (fallback)
                "%m-%d-%Y",  # Alternative US
            ]
        else:
            date_formats = [
                "%Y-%m-%d",  # ISO format (unambiguous)
                "%m/%d/%Y",  # US format
                "%m-%d-%Y",  # Alternative US
                "%d/%m/%Y",  # European format (fallback)
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
        semantic_type = str(param.get('semantic_type', '') or '').lower()
        param_context = " ".join(
            str(part).lower()
            for part in (
                param_name,
                param.get('description', ''),
                semantic_type,
            )
            if part
        )

        if param_type in {'integer', 'int'}:
            year_value = self._extract_year_parameter(user_query, param_context)
            if year_value is not None:
                return year_value

            numeric_value = self._extract_numeric_parameter(user_query, param_name)
            if numeric_value is not None:
                return numeric_value

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

            # For location parameters (intersection, neighbourhood, hundred_block, street, block, address)
            location_keywords = {'intersection', 'neighbourhood', 'neighborhood', 'hundred_block',
                                 'street', 'block', 'address', 'location', 'area', 'ward', 'division'}
            if param_name.lower() in location_keywords or any(kw in param_name.lower() for kw in location_keywords):
                value = self._extract_location_parameter(user_query, param_name)
                if value is not None:
                    return value

            # For type/category parameters (crime_type, occurrence_type, offence_category, etc.)
            type_keywords = {'type', 'category', 'group', 'offence', 'offense'}
            if any(kw in param_name.lower() for kw in type_keywords):
                value = self._extract_type_parameter(user_query, param)
                if value is not None:
                    return value

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

    # Common English stop words and function words that should never be extracted
    # as parameter values. Domain-agnostic — no city names, crime terms, etc.
    _STOP_WORDS = frozenset({
        'a', 'an', 'the', 'it', 'its', 'this', 'that', 'these', 'those',
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'shall', 'should', 'may', 'might', 'can', 'could',
        'here', 'there', 'where', 'when', 'how', 'what', 'which', 'who',
        'and', 'or', 'but', 'not', 'no', 'yes',
        'i', 'me', 'my', 'we', 'us', 'you', 'your', 'he', 'she', 'they', 'them',
        'all', 'some', 'any', 'each', 'every', 'both', 'most', 'many',
        'data', 'show', 'tell', 'give', 'get', 'find', 'list',
    })

    def _extract_location_parameter(self, user_query: str, param_name: str) -> Optional[str]:
        """Extract a location/place value from the query.

        Domain-agnostic — works for any location-like parameter (intersection, neighbourhood,
        region, campus, facility, etc.). Uses preposition patterns and proper-noun heuristics.
        """
        # Try quoted values first — always highest priority
        quoted = re.search(r'"([^"]+)"', user_query)
        if quoted:
            return quoted.group(1)

        # For area/region-like params, try "in <ProperNoun>" pattern first.
        # This catches "in the West End", "in Kitsilano", "in Building A", etc.
        area_keywords = {'neighbourhood', 'neighborhood', 'area', 'ward', 'region',
                         'district', 'zone', 'campus', 'facility', 'site', 'borough'}
        if any(kw in param_name.lower() for kw in area_keywords):
            # "in <Location>" — stops before year refs, punctuation, or clause boundaries
            in_pattern = (
                r'\bin\s+(?:the\s+)?'
                r'([A-Z][\w\s-]*?)'
                r'(?:\s+(?:in|from|since|during)\s+\d{4}|[?!.]'
                r'|\s+(?:over|this|last|getting|between)|$)'
            )
            match = re.search(in_pattern, user_query)
            if match:
                value = match.group(1).strip().rstrip(',')
                if len(value) >= 2 and value.lower() not in self._STOP_WORDS:
                    return value

            # "Is <ProperNoun> safe/getting/improving/worse?" — subject-position extraction
            subject_pattern = (
                r'\b(?:Is|Are|Has|Does|Did|Will)\s+'
                r'(?:the\s+)?([A-Z][\w\s-]+?)'
                r'\s+(?:safe|dangerous|getting|improving|worse|better|growing|declining|increasing|decreasing)'
            )
            match = re.search(subject_pattern, user_query)
            if match:
                value = match.group(1).strip().rstrip(',')
                if len(value) >= 2 and value.lower() not in self._STOP_WORDS:
                    return value

        # Preposition-based extraction — captures value after spatial/relational prepositions.
        # Stops before year references, clause boundaries, or punctuation.
        # Word boundary \b prevents matching inside words (e.g., "at" inside "What").
        prep_pattern = (
            r'\b(?:on|at|near|around|for|about|along)\s+'
            r'((?:the\s+)?[A-Za-z0-9][\w\s/&\'-]*?)'
            r'(?:\s+(?:in|from|since|during|between|for|this|last|over)\s+(?:\d{4}|the)|[?!.]|$)'
        )
        match = re.search(prep_pattern, user_query, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(',')
            if len(value) >= 2 and value.lower() not in self._STOP_WORDS:
                return value

        return None

    def _extract_type_parameter(self, user_query: str, param: Dict) -> Optional[str]:
        """Extract a categorical/type value from the query.

        Domain-agnostic — works for any type/category parameter. First tries to match
        example values from the parameter's description, then falls back to preposition
        patterns like 'for <value>', 'about <value>'.
        """
        # Try quoted values first
        quoted = re.search(r'"([^"]+)"', user_query)
        if quoted:
            return quoted.group(1)

        # Extract example values from parameter description if available.
        # Parses examples from patterns like "e.g., Value1, Value2" or "such as Value1, Value2"
        description = param.get('description', '')
        eg_match = re.search(r'(?:e\.g\.,?\s*|such as\s+|like\s+)(.+?)(?:\)|$)', description, re.IGNORECASE)
        if eg_match:
            examples = [ex.strip().strip('"\'') for ex in eg_match.group(1).split(',')]
            # Sort by length descending to match longer phrases first
            examples.sort(key=len, reverse=True)
            query_lower = user_query.lower()
            for example in examples:
                if example.strip() and example.lower() in query_lower:
                    return example

        # Try preposition-based extraction as fallback
        prep_pattern = (
            r'\b(?:for|about|of|track|tracking)\s+'
            r'((?:the\s+)?[A-Za-z][\w\s/$&\'-]*?)'
            r'(?:\s+(?:in|from|since|during|between|over|per|by)\s+|\s+trends?|[?!.]|$)'
        )
        match = re.search(prep_pattern, user_query, re.IGNORECASE)
        if match:
            value = match.group(1).strip().rstrip(',')
            if len(value) >= 3 and value.lower() not in self._STOP_WORDS:
                return value

        return None

    def _extract_year_parameter(self, user_query: str, param_context: str) -> Optional[int]:
        """Extract a 4-digit year for year-like integer parameters.

        Handles multi-year queries (e.g., "compare 2023 vs 2024") by assigning the
        appropriate year based on the parameter name — 'previous_year' gets the earlier
        year, 'year' gets the later year. When only one year is mentioned and the param
        is a 'previous/prior/baseline' variant, returns year - 1.
        """
        year_keywords = {
            "year",                   # English
            "annee", "année",         # French
            "ano",                    # Portuguese
            "año",                    # Spanish
            "jahr",                   # German
            "anno",                   # Italian
            "jaar",                   # Dutch
            "rok",                    # Polish / Czech
            "год", "god",             # Russian (cyrillic + transliterated)
            "år",                     # Swedish / Norwegian / Danish
            "vuosi",                  # Finnish
            "yıl",                    # Turkish
            "éve",                    # Hungarian
        }
        if not any(kw in param_context for kw in year_keywords):
            return None

        query_lower = user_query.lower()
        current_year = datetime.now().year

        # Determine if this parameter represents a "previous" or "baseline" year.
        # Check only the param name (first token of context), not the description,
        # to avoid false matches on words like "compare" in descriptions.
        param_name_part = param_context.split()[0] if param_context else ''
        previous_name_keywords = {'previous', 'prior', 'last', 'baseline', 'earlier', 'old', 'start', 'from'}
        is_previous_param = any(kw in param_name_part for kw in previous_name_keywords)

        # Check for relative year phrases
        relative_years = {
            "this year": current_year,
            "current year": current_year,
            "last year": current_year - 1,
            "previous year": current_year - 1,
            "next year": current_year + 1,
        }

        for phrase, year in relative_years.items():
            if phrase in query_lower:
                if is_previous_param and phrase in ("this year", "current year"):
                    # "this year" for a previous_year param → return prior year
                    return year - 1
                return year

        # Find all explicit years in the query
        explicit_years = re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", user_query)
        if explicit_years:
            years = sorted(set(int(y) for y in explicit_years))

            if len(years) >= 2:
                # Multiple years mentioned — assign based on param role
                return years[0] if is_previous_param else years[-1]
            else:
                # Single year mentioned
                year = years[0]
                if is_previous_param:
                    # For a "previous_year" param with only one year in query,
                    # return year - 1 so it doesn't duplicate the primary year
                    return year - 1
                return year

        return None

    def _extract_numeric_parameter(self, user_query: str, param_name: str) -> Optional[int]:
        """Extract a labeled integer value for generic numeric parameters."""
        if not param_name:
            return None

        escaped_name = re.escape(param_name.replace("_", " "))
        patterns = [
            rf"\b{escaped_name}\b\s*[:=]?\s*(-?\d+)\b",
            rf"\b{escaped_name}\b\s+(?:is|equals?|of)\s+(-?\d+)\b",
            rf"\b(?:top|limit|first|last)\s+(-?\d+)\b" if param_name.lower() in {"limit", "top_n", "count", "size"} else None,
        ]

        for pattern in patterns:
            if not pattern:
                continue
            match = re.search(pattern, user_query, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    continue

        return None
