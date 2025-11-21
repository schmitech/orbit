"""Utility for processing intent SQL templates with domain-specific variables."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, Optional, Tuple, Union

from .domain import DomainConfig

# Regex patterns reused for variable and conditional substitution
_VARIABLE_PATTERN = re.compile(r"{{\s*([\w\.]+)\s*}}")
_IF_PATTERN = re.compile(r"{%\s*if\s+([^%]+?)\s*%}(.*?){%\s*endif\s*%}", re.DOTALL)


class TemplateProcessor:
    """Process template metadata and SQL using domain configuration variables."""

    def __init__(self, domain_config: Union[DomainConfig, Dict[str, Any]]):
        if isinstance(domain_config, DomainConfig):
            self.domain_config = domain_config
        else:
            self.domain_config = DomainConfig(domain_config)

        self._base_context = self._build_base_context()

    def _build_base_context(self) -> Dict[str, Any]:
        """Construct reusable context derived from the domain configuration."""
        context: Dict[str, Any] = {
            "domain_name": self.domain_config.domain_name,
            "domain_type": getattr(self.domain_config, "domain_type", None),
            "entities": {},
            "tables": {},
        }

        primary_entity = self.domain_config.get_primary_entity()
        secondary_entities = self.domain_config.get_secondary_entities()

        if primary_entity:
            context["primary_entity"] = primary_entity.name
            context["primary_table"] = primary_entity.table_name
        if secondary_entities:
            context["secondary_entity"] = secondary_entities[0].name
            context["secondary_table"] = secondary_entities[0].table_name
        context["has_secondary_entity"] = bool(secondary_entities)

        for entity_name, entity in self.domain_config.entities.items():
            entity_info = {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "table_name": entity.table_name,
                "primary_key": entity.primary_key,
                "display_name": entity.display_name,
                "display_name_field": entity.display_name_field,
                "relationships": entity.relationships,
                "searchable_fields": entity.searchable_fields,
                "common_filters": entity.common_filters,
                "default_sort_field": entity.default_sort_field,
                "default_sort_order": entity.default_sort_order,
                "metadata": entity.metadata,
            }
            context["entities"][entity_name] = entity_info
            if entity.table_name:
                context["tables"][entity_name] = entity.table_name

        return context

    def get_context(self) -> Dict[str, Any]:
        """Return a copy of the base context so callers can inspect or extend it."""
        return copy.deepcopy(self._base_context)

    def render_template_structure(
        self,
        template: Dict[str, Any],
        extra_context: Optional[Dict[str, Any]] = None,
        preserve_unknown: bool = True,
    ) -> Dict[str, Any]:
        """Return a copy of the template with variables substituted recursively."""
        context = self._merge_context(extra_context)
        return self._render_structure(copy.deepcopy(template), context, preserve_unknown=preserve_unknown)

    def render_sql(
        self,
        sql_template: str,
        parameters: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
        preserve_unknown: bool = False,
    ) -> str:
        """Render SQL with domain variables and optional runtime parameters."""
        context = self._merge_context(extra_context)
        return self._render_text(
            sql_template,
            context,
            preserve_unknown=preserve_unknown,
            parameters=parameters,
        ).strip()

    # Internal helpers -------------------------------------------------

    def _merge_context(self, extra_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = self.get_context()
        if not extra_context:
            return base
        return _deep_update(base, extra_context)

    def _render_structure(
        self,
        value: Any,
        context: Dict[str, Any],
        preserve_unknown: bool,
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._render_structure(val, context, preserve_unknown)
                for key, val in value.items()
            }
        if isinstance(value, list):
            return [self._render_structure(item, context, preserve_unknown) for item in value]
        if isinstance(value, str):
            return self._render_text(value, context, preserve_unknown)
        return value

    def _render_text(
        self,
        text: str,
        context: Dict[str, Any],
        preserve_unknown: bool,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not text:
            return text

        def replace_if(match: re.Match[str]) -> str:
            condition = match.group(1).strip()
            block_content = match.group(2)
            result = self._evaluate_condition(condition, context, parameters)

            if result is None:
                return match.group(0) if preserve_unknown else ""
            return block_content if result else ""

        processed = _IF_PATTERN.sub(replace_if, text)

        def replace_var(match: re.Match[str]) -> str:
            token = match.group(1).strip()
            value, found, _ = self._resolve_variable(token, context, parameters)
            if not found:
                return match.group(0) if preserve_unknown else ""
            if value is None:
                return ""
            # JSON-encode lists and dicts to ensure valid JSON output
            if isinstance(value, (list, dict)):
                return json.dumps(value)
            return str(value)

        return _VARIABLE_PATTERN.sub(replace_var, processed)

    def _evaluate_condition(
        self,
        expression: str,
        context: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        negate = False
        expr = expression

        if expr.startswith("not "):
            negate = True
            expr = expr[4:].strip()
        elif expr.startswith("!"):
            negate = True
            expr = expr[1:].strip()

        value, found, source = self._resolve_variable(expr, context, parameters)
        if not found:
            return None

        if source == "parameter":
            truthy = value is not None and value != ""
        else:
            truthy = bool(value)

        return not truthy if negate else truthy

    def _resolve_variable(
        self,
        token: str,
        context: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, bool, str]:
        value, found = _traverse_dict(context, token)
        if found:
            return value, True, "context"

        if parameters is not None and token in parameters:
            return parameters[token], True, "parameter"

        return None, False, "unknown"


def _traverse_dict(data: Dict[str, Any], path: str) -> Tuple[Any, bool]:
    """Traverse nested dictionaries using dotted paths."""
    parts = path.split('.') if path else []
    current: Any = data

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None, False
    return current, True


def _deep_update(original: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            _deep_update(original[key], value)
        else:
            original[key] = copy.deepcopy(value)
    return original
