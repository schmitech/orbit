"""Utility for processing intent templates with Jinja2 templating system."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, Optional, Union

from jinja2 import Environment, BaseLoader, DebugUndefined, UndefinedError

from .domain import DomainConfig

logger = logging.getLogger(__name__)


# Custom Undefined class that preserves unknown variables when preserve_unknown=True
class PreservingUndefined(DebugUndefined):
    """Undefined that preserves the original template syntax for unknown variables."""

    def __str__(self) -> str:
        return f"{{{{ {self._undefined_name} }}}}"

    def __repr__(self) -> str:
        return f"{{{{ {self._undefined_name} }}}}"

    def __bool__(self) -> bool:
        return False


class SilentUndefined(DebugUndefined):
    """Undefined that raises on access but returns False in boolean context.

    This allows `{% if variable %}` to work when variable is undefined (returns False),
    but raises an error when trying to use the undefined variable's value.
    """

    def __str__(self) -> str:
        # Raise when trying to use the value
        self._fail_with_undefined_error()

    def __repr__(self) -> str:
        self._fail_with_undefined_error()

    def __bool__(self) -> bool:
        # In boolean context (if statements), undefined is falsy
        return False

    def __iter__(self):
        # Allow iteration over undefined to return empty iterator
        return iter([])

    def __len__(self):
        return 0


# Custom filters for SQL and JSON safety
def sql_string(value: Any) -> str:
    """Escape string for SQL, returns NULL for None."""
    if value is None:
        return "NULL"
    # Handle undefined template variables - preserve the template syntax
    if isinstance(value, DebugUndefined):
        return f"{{{{ {value._undefined_name} | sql_string }}}}"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def sql_list(values: Any) -> str:
    """Convert list to SQL IN clause values."""
    if not values:
        return "NULL"
    # Handle undefined template variables - preserve the template syntax
    if isinstance(values, DebugUndefined):
        return f"{{{{ {values._undefined_name} | sql_list }}}}"
    if isinstance(values, str):
        return sql_string(values)
    return ", ".join(sql_string(v) for v in values)


def sql_identifier(value: str) -> str:
    """Escape SQL identifier (table/column names)."""
    if value is None:
        return ""
    # Handle undefined template variables - preserve the template syntax
    if isinstance(value, DebugUndefined):
        return f"{{{{ {value._undefined_name} | sql_identifier }}}}"
    # Remove any existing quotes and escape embedded quotes
    clean = str(value).replace('"', '""')
    return f'"{clean}"'


def json_filter(value: Any) -> str:
    """JSON encode value, handling undefined template variables."""
    # Handle PreservingUndefined - return the template syntax so it can be preserved
    if isinstance(value, DebugUndefined):
        # Return the original template syntax for undefined variables
        return f"{{{{ {value._undefined_name} | tojson }}}}"
    return json.dumps(value)


def joiner_filter(sep: str = ", ") -> "Joiner":
    """Create a joiner that returns separator after first call."""
    return Joiner(sep)


class Joiner:
    """Helper class for comma-separated conditional values in templates."""

    def __init__(self, sep: str = ", "):
        self.sep = sep
        self.used = False

    def __call__(self) -> str:
        if not self.used:
            self.used = True
            return ""
        return self.sep

    def __str__(self) -> str:
        if not self.used:
            self.used = True
            return ""
        return self.sep


class TemplateProcessor:
    """Process template metadata and SQL/JSON using Jinja2 with domain configuration variables."""

    def __init__(self, domain_config: Union[DomainConfig, Dict[str, Any]]):
        # Check if it's a dict (needs to be converted) or already a domain config object
        if isinstance(domain_config, dict):
            self.domain_config = DomainConfig(domain_config)
        else:
            # Already a DomainConfig or compatible object (duck typing)
            self.domain_config = domain_config

        self._base_context = self._build_base_context()

        # Create Jinja2 environment for normal rendering
        # Uses SilentUndefined: allows `{% if var %}` when var is undefined (returns False)
        # but raises when trying to use the undefined variable's value like {{ var }}
        self.env = Environment(
            loader=BaseLoader(),
            undefined=SilentUndefined,
            autoescape=False,  # Templates contain SQL/JSON, not HTML
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )

        # Create Jinja2 environment for preserve_unknown mode
        self.env_preserve = Environment(
            loader=BaseLoader(),
            undefined=PreservingUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )

        # Register custom filters on both environments
        self._register_filters(self.env)
        self._register_filters(self.env_preserve)

        # Register custom globals (functions)
        self._register_globals(self.env)
        self._register_globals(self.env_preserve)

    def _register_filters(self, env: Environment) -> None:
        """Register custom Jinja2 filters."""
        env.filters["sql_string"] = sql_string
        env.filters["sql_list"] = sql_list
        env.filters["sql_identifier"] = sql_identifier
        env.filters["json"] = json_filter
        env.filters["tojson"] = json_filter  # Alias for compatibility

    def _register_globals(self, env: Environment) -> None:
        """Register custom Jinja2 global functions."""
        env.globals["joiner"] = joiner_filter

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
        return self._render_structure(
            copy.deepcopy(template), context, preserve_unknown=preserve_unknown
        )

    def render_sql(
        self,
        sql_template: str,
        parameters: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
        preserve_unknown: bool = False,
    ) -> str:
        """Render SQL/Query DSL with domain variables and optional runtime parameters.

        Args:
            sql_template: Jinja2 template string for SQL or query DSL
            parameters: Runtime parameters to substitute into the template
            extra_context: Additional context to merge with domain context
            preserve_unknown: If True, keep unknown variables as {{ var }} in output

        Returns:
            Rendered template string with variables substituted
        """
        context = self._merge_context(extra_context)
        if parameters:
            context.update(parameters)

        rendered = self._render_text(
            sql_template,
            context,
            preserve_unknown=preserve_unknown,
        )
        return rendered.strip() if rendered else rendered

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
            return [
                self._render_structure(item, context, preserve_unknown)
                for item in value
            ]
        if isinstance(value, str):
            return self._render_text(value, context, preserve_unknown)
        return value

    def _render_text(
        self,
        text: str,
        context: Dict[str, Any],
        preserve_unknown: bool,
    ) -> str:
        """Render a text template using Jinja2."""
        if not text:
            return text

        try:
            # Choose environment based on preserve_unknown flag
            env = self.env_preserve if preserve_unknown else self.env
            template = env.from_string(text)
            rendered = template.render(**context)

            # Clean up multiple blank lines
            lines = rendered.split("\n")
            cleaned_lines = []
            prev_blank = False
            for line in lines:
                is_blank = not line.strip()
                if is_blank and prev_blank:
                    continue
                cleaned_lines.append(line)
                prev_blank = is_blank

            return "\n".join(cleaned_lines)

        except UndefinedError as e:
            if preserve_unknown:
                # This shouldn't happen with PreservingUndefined, but handle it
                logger.warning(f"Undefined variable in template: {e}")
                return text
            raise
        except Exception as e:
            logger.error(f"Error rendering template: {e}")
            if preserve_unknown:
                return text
            raise


def _deep_update(original: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            _deep_update(original[key], value)
        else:
            original[key] = copy.deepcopy(value)
    return original
