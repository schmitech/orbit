"""
Enricher — the "hybrid" AI, tightly scoped.

Given a family and a one-line natural-language description, it fills only the
*soft* fields (skill_description, routing_examples). It never touches the tuple,
enums, or providers — those stay deterministic in the spec.

Reuses the same ORBIT-native plumbing as utils/templates/template_generator.py:
UnifiedProviderFactory to build a client, and the "return ONLY JSON" extraction
pattern.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional

# server/ is the import root (inference == server/inference).
from inference.pipeline.providers.unified_provider_factory import UnifiedProviderFactory

from .specs import AdapterSpec

_PROMPT = """You are helping author an ORBIT adapter config. This adapter is a "{title}": {description}

The operator describes what it should do as:
"{user_description}"

Produce concise skill metadata for auto-routing. Return ONLY a JSON object with exactly these keys:
{{
  "skill_description": "<one clear sentence describing the skill>",
  "routing_examples": ["<short user phrase>", "... 4 to 6 total, lowercase, no trailing punctuation"]
}}
Return the JSON object and nothing else."""


def _extract_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(match.group(0))


async def enrich_soft_fields(
    spec: AdapterSpec,
    user_description: str,
    *,
    provider: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Return {"skill_description": str, "routing_examples": list[str]} for the given spec,
    limited to the soft fields the spec actually declares.
    """
    client = UnifiedProviderFactory.create_provider_by_name(provider, config or {})
    if hasattr(client, "initialize"):
        maybe = client.initialize()
        if asyncio.iscoroutine(maybe):
            await maybe

    prompt = _PROMPT.format(
        title=spec.title,
        description=spec.description,
        user_description=user_description,
    )
    raw = await client.generate(prompt)
    data = _extract_json(raw)

    soft = set(spec.soft_fields())
    result: Dict[str, Any] = {}
    if "skill_description" in soft and data.get("skill_description"):
        result["skill_description"] = str(data["skill_description"]).strip()
    if "routing_examples" in soft and isinstance(data.get("routing_examples"), list):
        result["routing_examples"] = [str(p).strip() for p in data["routing_examples"] if str(p).strip()]
    return result
