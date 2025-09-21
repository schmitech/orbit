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
        """Generic strategy does not apply custom boosts."""
        return 0.0

    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return semantic extractors that operate as pattern matchers."""
        return self.semantic_extractors

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
