"""
Pydantic schema for intent templates.

Templates are pre-approved, hand-written YAML — that's the entire premise of
ORBIT's "no free-form text-to-SQL" claim. But nothing previously verified that
the YAML actually conforms to one shape: `semantic_tags` vs. `semantic_type`,
`allowed_values` vs. `enum`, a missing `version`, two incompatible Firecrawl
template shapes — all of that currently loads silently. `extra="forbid"` on
`TemplateSpec`/`ParameterSpec` is what turns "silently loads" into "flagged at
load time": any field not in the schema below is schema drift by definition,
whether it's a typo, a copy-pasted field from a different backend, or a
genuinely new shape nobody's told this module about yet.

This schema is deliberately permissive about *which* fields a template has —
every backend-specific payload field (sql_template, mongodb_query, query_dsl,
graphql_template, endpoint_template, ...) is optional, since a given template
only ever uses one backend's shape. It is deliberately strict about *only*
allowing fields it knows about, via extra="forbid".

Field set below was derived from a survey of every template file under
examples/intent-templates/ (not from documentation), so it reflects what
templates actually look like today, not an idealized shape.
"""

from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParameterSpec(BaseModel):
    """A single template parameter definition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str = "string"
    required: bool = False
    default: Optional[Any] = None
    description: Optional[str] = None
    allowed_values: Optional[list[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    aliases: Optional[list[str]] = None
    example: Optional[Any] = None
    location: Optional[str] = None  # HTTP-family: "path" | "query" | "body" | "header"
    format: Optional[str] = None
    graphql_type: Optional[str] = None
    validation_hint: Optional[str] = None


class TemplateSpec(BaseModel):
    """A single intent template, across all backends (SQL/HTTP/Mongo/ES/GraphQL/Firecrawl/agent)."""

    model_config = ConfigDict(extra="forbid")

    # Identity and matching
    id: str
    version: str = "0.0.0"
    description: str = ""
    nl_examples: list[str] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)
    semantic_tags: Optional[dict[str, Any]] = None
    semantic_type: Optional[str] = None
    category: Optional[str] = None
    complexity: Optional[str] = None
    approved: bool = False

    # Parameters
    parameters: list[ParameterSpec] = Field(default_factory=list)

    # Result shaping
    result_format: Optional[str] = None
    response_mapping: Optional[dict[str, Any]] = None
    display_fields: Optional[list[Any]] = None

    # Cross-adapter composite templates
    cross_adapter: Optional[bool] = None
    target_adapters: Optional[list[Union[str, dict[str, Any]]]] = None
    merge_strategy: Optional[str] = None
    partial_results: Optional[bool] = None

    # Provenance
    created_at: Optional[str] = None
    created_by: Optional[str] = None

    # --- Backend-specific payloads (each optional; a template uses exactly one) ---

    # SQL
    sql: Optional[str] = None
    sql_template: Optional[str] = None

    # HTTP / REST
    http_method: Optional[str] = None
    endpoint: Optional[str] = None
    endpoint_template: Optional[str] = None
    endpoint_type: Optional[str] = None
    headers: Optional[dict[str, Any]] = None
    query_params: Optional[dict[str, Any]] = None
    request_body: Optional[Union[str, dict[str, Any]]] = None
    timeout: Optional[float] = None

    # MongoDB
    database: Optional[str] = None
    collection: Optional[str] = None
    query_type: Optional[str] = None
    mongodb_query: Optional[Any] = None

    # Elasticsearch
    index: Optional[str] = None
    query_dsl: Optional[Any] = None

    # GraphQL
    graphql_type: Optional[str] = None
    operation_name: Optional[str] = None
    graphql_template: Optional[str] = None

    # Firecrawl / web
    url_mapping: Optional[dict[str, Any]] = None
    formats: Optional[list[str]] = None

    # Agent / tool-calling
    tool_type: Optional[str] = None
    function_schema: Optional[dict[str, Any]] = None
    execution: Optional[Any] = None

    @field_validator("semantic_tags", mode="before")
    @classmethod
    def _coerce_semantic_tags(cls, value: Any) -> Any:
        """Normalize a list of single-key mappings into one merged dict — a
        drift some templates exhibit instead of a single semantic_tags dict."""
        if isinstance(value, list):
            merged: dict[str, Any] = {}
            for item in value:
                if isinstance(item, dict):
                    merged.update(item)
            return merged
        return value
