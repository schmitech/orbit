"""
Validator — mirrors what ORBIT's adapter loader actually enforces, reusing the
real capability parser rather than reinventing a schema.

Sources of truth:
  - server/adapters/registry.py:261 — required fields: type, datasource, adapter, implementation
  - server/adapters/capabilities.py — AdapterCapabilities.from_config raises on bad enums
  - server/inference/pipeline/steps/_utils.py — types that don't need an inference provider
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


def validate_structure(entry: Dict[str, Any]) -> List[str]:
    """Validate a single adapter entry (a dict). Returns a list of error strings (empty = valid)."""
    errors: List[str] = []

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


def validate_yaml_text(text: str) -> List[str]:
    """Validate a rendered YAML file (must have `adapters:` as a list of valid entries)."""
    errors: List[str] = []
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


def validate_providers(entry: Dict[str, Any], enabled_providers: Optional[set]) -> List[str]:
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
