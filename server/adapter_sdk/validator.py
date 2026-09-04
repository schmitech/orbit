"""
Validator — mirrors what ORBIT's adapter loader actually enforces, reusing the
real capability parser rather than reinventing a schema.

Sources of truth:
  - server/adapters/registry.py:261 — required fields: type, datasource, adapter, implementation
  - server/adapters/capabilities.py — AdapterCapabilities.from_config raises on bad enums
  - server/inference/pipeline/steps/_utils.py — types that don't need an inference provider
"""

from __future__ import annotations

from typing import Any, Optional

import yaml

# server/ is the import root (adapters == server/adapters).
from adapters.capabilities import AdapterCapabilities

REQUIRED_FIELDS = ["type", "datasource", "adapter", "implementation"]

KNOWN_TYPES = {
    "retriever", "passthrough", "web-search", "document_generation", "image_generation",
    "video_generation", "audio_generation", "openai_realtime", "openai_realtime_translation",
    "gemini_live", "mcp_agent", "fetch",
}

KNOWN_DATASOURCES = {
    "none", "sqlite", "postgres", "mysql", "mssql", "chroma", "qdrant", "pinecone",
    "elasticsearch", "opensearch", "http", "mongodb", "duckdb", "athena",
}

# Types that skip the inference-provider requirement (steps/_utils.py:29-34).
NO_INFERENCE_PROVIDER_TYPES = {"fetch", "openai_realtime", "openai_realtime_translation", "gemini_live"}


def validate_structure(entry: dict[str, Any]) -> list[str]:
    """Validate a single adapter entry (a dict). Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    if not isinstance(entry, dict):
        return ["adapter entry is not a mapping"]

    if not entry.get("name"):
        errors.append("missing required field: name")

    for f in REQUIRED_FIELDS:
        if not entry.get(f):
            errors.append(f"missing required field: {f}")

    a_type = entry.get("type")
    if a_type and a_type not in KNOWN_TYPES:
        errors.append(f"unknown type '{a_type}'")

    ds = entry.get("datasource")
    if ds and ds not in KNOWN_DATASOURCES:
        errors.append(f"unknown datasource '{ds}'")

    # Reuse the real capability parser — it raises on invalid enum values.
    try:
        AdapterCapabilities.from_config(entry)
    except ValueError as exc:
        errors.append(f"invalid capabilities: {exc}")

    return errors


def validate_yaml_text(text: str) -> list[str]:
    """Validate a rendered YAML file (must have `adapters:` as a list of valid entries)."""
    errors: list[str] = []
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f"invalid YAML: {exc}"]

    if not isinstance(parsed, dict) or not isinstance(parsed.get("adapters"), list):
        return ["root must contain 'adapters:' as a list"]

    names = []
    for i, entry in enumerate(parsed["adapters"]):
        for err in validate_structure(entry):
            errors.append(f"adapters[{i}]: {err}")
        if isinstance(entry, dict) and entry.get("name"):
            names.append(entry["name"])

    dupes = {n for n in names if names.count(n) > 1}
    for n in dupes:
        errors.append(f"duplicate adapter name within file: {n}")

    return errors


def validate_answers(spec, answers: dict[str, Any]) -> list[str]:
    """Bound each answer by its question's limits. Returns error strings (empty = valid).

    Runs before rendering: an over-long value would otherwise pass straight through
    Jinja into the written config, so the template is not the place to catch it.
    """
    from .specs import question_limits

    errors: list[str] = []
    for q in spec.questions:
        if q.field not in answers:
            continue
        value = answers[q.field]
        if value is None:
            continue
        limits = question_limits(q)

        if q.type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{q.field}: expected a whole number")
                continue
            low, high = limits.get("min_value"), limits.get("max_value")
            if low is not None and value < low:
                errors.append(f"{q.field}: must be at least {low}")
            if high is not None and value > high:
                errors.append(f"{q.field}: must be at most {high}")
            continue

        if q.type == "list":
            if not isinstance(value, list):
                errors.append(f"{q.field}: expected a list")
                continue
            max_items = limits["max_items"]
            if len(value) > max_items:
                errors.append(f"{q.field}: at most {max_items} entries (got {len(value)})")
            max_length = limits["max_length"]
            for item in value:
                if not isinstance(item, str):
                    errors.append(f"{q.field}: entries must be text")
                    break
                if len(item) > max_length:
                    errors.append(
                        f"{q.field}: each entry is limited to {max_length} characters "
                        f"(got {len(item)})"
                    )
                    break
            continue

        if q.type == "bool":
            continue

        if not isinstance(value, str):
            errors.append(f"{q.field}: expected text")
            continue
        max_length = limits["max_length"]
        if len(value) > max_length:
            errors.append(f"{q.field}: limited to {max_length} characters (got {len(value)})")

    return errors


def validate_providers(entry: dict[str, Any], enabled_providers: Optional[set]) -> list[str]:
    """
    Optional provider check, separated so the core validator stays pure/testable.
    Pass the set of enabled provider names; pass None to skip.
    """
    if enabled_providers is None:
        return []
    a_type = entry.get("type")
    if a_type in NO_INFERENCE_PROVIDER_TYPES:
        return []
    provider = entry.get("inference_provider")
    if provider and provider not in enabled_providers:
        return [f"inference_provider '{provider}' is not enabled"]
    return []
