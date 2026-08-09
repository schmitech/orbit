"""
Round-trip detection — given an adapter entry already on disk, guess which
AdapterSpec (and variant) produced it, and recover the answers that would
regenerate it.

The create form is otherwise write-only: once an adapter exists, editing it
means raw YAML. This lets "Edit in form" work, but only when it can prove the
round trip is lossless — an adapter matched to the wrong spec, or one with
hand-edits the form can't represent (comments, extra keys, values outside a
question's shape), must degrade to the YAML editor rather than silently
dropping something on save.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

import yaml

from .renderer import render_adapter
from .specs import SPEC_REGISTRY, AdapterSpec
from .validator import validate_answers

# Every template emits this tuple at the top level (validator.py:REQUIRED_FIELDS
# plus `adapter`), so it is the first, cheap filter.
_BASE_KEYS = ("type", "datasource", "adapter", "implementation")


def _base_tuple(spec: AdapterSpec, variant: Optional[str]) -> Tuple[Any, ...]:
    fixed = dict(spec.fixed)
    if variant is not None:
        fixed.update(spec.variants[variant].get("fixed", {}))
    return tuple(fixed.get(k) for k in _BASE_KEYS)


# Specs whose variants can't be told apart by the base tuple alone (every
# variant renders the same type/datasource/adapter/implementation) need an
# explicit resolver that reads the one field the template does vary.
def _resolve_variant_doc_generator(entry: Dict[str, Any]) -> Optional[str]:
    return entry.get("document_format")


def _resolve_variant_web_search_external(entry: Dict[str, Any]) -> Optional[str]:
    return (entry.get("web_search") or {}).get("provider")


_VARIANT_RESOLVERS: Dict[str, Callable[[Dict[str, Any]], Optional[str]]] = {
    "doc-generator": _resolve_variant_doc_generator,
    "web-search-external": _resolve_variant_web_search_external,
}


def detect_spec_and_variant(entry: Dict[str, Any]) -> Optional[Tuple[AdapterSpec, Optional[str]]]:
    """Best guess at the (spec, variant) that would render this entry.

    Returns None when no spec's fixed tuple matches, or when more than one
    plausibly does and there's no way to break the tie — refusing beats
    guessing wrong and silently mangling an edit.
    """
    matches = []
    for spec in SPEC_REGISTRY.values():
        if not spec.variant_field:
            candidate_variants = [None]
        elif spec.key in _VARIANT_RESOLVERS:
            resolved = _VARIANT_RESOLVERS[spec.key](entry)
            candidate_variants = [resolved] if resolved in spec.variants else []
        else:
            # No resolver needed: each variant's fixed tuple is already unique
            # (e.g. media-generator's `type` differs per variant), so a plain
            # scan finds the right one without any extra field lookup.
            candidate_variants = spec.variant_values()

        for variant in candidate_variants:
            if _base_tuple(spec, variant) == tuple(entry.get(k) for k in _BASE_KEYS):
                matches.append((spec, variant))

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # The only known tie: passthrough and web-search-native share their
        # entire fixed tuple. `capabilities.web_search: true` is the one field
        # web-search-native's template emits that passthrough's never does.
        keys = {m[0].key for m in matches}
        if keys == {"passthrough", "web-search-native"}:
            is_native = bool((entry.get("capabilities") or {}).get("web_search"))
            for spec, variant in matches:
                if (spec.key == "web-search-native") == is_native:
                    return (spec, variant)
    return None


# Field overrides for answers that land somewhere other than entry[field],
# entry["capabilities"][field], or entry["config"][field] (the three spots
# extract_answers checks by default).
def _media_provider_override(entry: Dict[str, Any], spec: AdapterSpec, variant: Optional[str]) -> Any:
    if not variant:
        return None
    provider_field = spec.variants[variant].get("fixed", {}).get("provider_field")
    return entry.get(provider_field) if provider_field else None


_FIELD_OVERRIDES: Dict[Tuple[str, str], Callable[[Dict[str, Any], AdapterSpec, Optional[str]], Any]] = {
    ("media-generator", "media_provider"): _media_provider_override,
    ("web-search-external", "result_count"): lambda e, s, v: (e.get("web_search") or {}).get("result_count"),
    ("web-search-external", "api_key"): lambda e, s, v: (e.get("web_search") or {}).get("api_key"),
    ("web-search-external", "query_url"): lambda e, s, v: (e.get("web_search") or {}).get("query_url"),
    ("web-search-external", "search_engine_id"): lambda e, s, v: (e.get("web_search") or {}).get("search_engine_id"),
}


def extract_answers(spec: AdapterSpec, variant: Optional[str], entry: Dict[str, Any]) -> Dict[str, Any]:
    """Recover an `answers` dict for `spec` from an already-rendered entry."""
    capabilities = entry.get("capabilities") or {}
    config = entry.get("config") or {}
    answers: Dict[str, Any] = {}

    for q in spec.questions:
        override = _FIELD_OVERRIDES.get((spec.key, q.field))
        if override:
            value = override(entry, spec, variant)
        elif q.field in entry:
            value = entry[q.field]
        elif q.field in capabilities:
            value = capabilities[q.field]
        elif q.field in config:
            value = config[q.field]
        elif q.type == "list":
            # Not found anywhere the loop above checked: every template only
            # ever emits a list field when it's non-empty (`{% if field %}`),
            # so absence means "answered blank", not "use the spec default".
            value = []
        elif q.type == "bool":
            # Same reasoning: guarded bool fields (mcp_tools, enable_audio_transcription,
            # ...) are only written when true, so absence means false, not the
            # spec's suggested default.
            value = False
        else:
            # Guarded optional str/int fields (rewrite_model, media_provider, ...)
            # are only written when answered, so absence means "left blank".
            value = None

        answers[q.field] = value

    if spec.variant_field:
        # Authoritative — some variant fields (media_type) never appear
        # literally in the rendered output, so this is not always redundant
        # with the loop above.
        answers[spec.variant_field] = variant

    return answers


def detect_editable_spec(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Full round-trip check: detect spec/variant, extract answers, re-render,
    and confirm the re-render matches the entry on disk before calling it safe
    to edit through the form.

    Returns `{"editable": True, "spec": ..., "variant": ..., "answers": ...}`
    or `{"editable": False, "reason": ...}`.
    """
    match = detect_spec_and_variant(entry)
    if not match:
        return {
            "editable": False,
            "reason": "This adapter wasn't generated by a known adapter family; edit it as YAML.",
        }
    spec, variant = match
    answers = extract_answers(spec, variant, entry)

    errors = validate_answers(spec, answers)
    if errors:
        return {
            "editable": False,
            "reason": "Extracted answers failed validation (" + "; ".join(errors) + "); edit as YAML.",
        }

    try:
        rendered = render_adapter(spec, answers)
        rendered_entries = (yaml.safe_load(rendered) or {}).get("adapters") or []
    except Exception as exc:  # noqa: BLE001 - any render/parse failure means "not editable"
        return {"editable": False, "reason": f"Could not re-render for comparison: {exc}"}

    if len(rendered_entries) != 1 or rendered_entries[0] != entry:
        return {
            "editable": False,
            "reason": "This adapter has hand-edits (comments, extra fields, or values) the form "
                      "can't represent without dropping them; edit it as YAML to keep them.",
        }

    return {"editable": True, "spec": spec.key, "variant": variant, "answers": answers}
