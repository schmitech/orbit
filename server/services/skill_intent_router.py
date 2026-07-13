"""
Skill Intent Router

Automatically infers which skill (if any) a plain natural-language turn wants,
so a client can trigger a skill without explicitly sending ``skill=<name>``
(the OrbitChat ``/`` picker). The inferred skill name is fed into the existing
``RequestContextBuilder.build_context(skill=...)`` path, so it reuses the same
allowlist check, adapter swap, provider resolution, and pipeline step gating —
no pipeline or generation-step changes.

Two-stage hybrid detection:

  1. **Embedding pre-filter** (cheap, recall-oriented) — cosine-match the query
     against each candidate skill's phrase set; keep candidates above a
     permissive threshold. If none match, return ``None`` WITHOUT any LLM call
     (this keeps ordinary conversational turns cheap).
  2. **LLM confirm** (precise) — one small constrained call disambiguates the
     surviving candidate(s) and guards against false positives (e.g. negation,
     "spreadsheet" vs "pdf").

Only skills whose backing adapter is a generation type (image/video/document/
audio), a ``fetch`` adapter, or a ``web_search`` adapter participate. Retrieval
and mcp-agent skills are excluded (initial scope).

Gated by two switches (both required), checked by the caller
(``PipelineChatService._auto_skill_routing_enabled``):

  - global:  ``skill_routing.auto_detect``       (config)
  - adapter: ``capabilities.auto_skill_routing``  (consumer adapter)

See ``docs/adapters/auto-skill-intent-detection.md``.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _cosine(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity between two vectors; 0.0 when either is a zero vector."""
    a = np.asarray(v1, dtype=float)
    b = np.asarray(v2, dtype=float)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SkillIntentRouter:
    """Hybrid (embedding pre-filter → LLM confirm) skill intent detector."""

    # Backing-adapter types eligible for auto-routing (artifact/tool producers).
    ROUTABLE_ADAPTER_TYPES = {
        "image_generation",
        "video_generation",
        "document_generation",
        "audio_generation",
        "fetch",
    }

    def __init__(self, config: Dict[str, Any], adapter_manager):
        self.config = config or {}
        self.adapter_manager = adapter_manager

        routing_cfg = (self.config.get("skill_routing") or {})
        self.embedding_threshold = float(routing_cfg.get("embedding_threshold", 0.35))
        self.router_provider = routing_cfg.get("router_provider")
        self.router_model = routing_cfg.get("router_model")
        self.history_turns = int(routing_cfg.get("history_turns", 4))
        self.max_candidates = int(routing_cfg.get("max_candidates", 3))
        self.confirm_max_tokens = int(routing_cfg.get("confirm_max_tokens", 12))

        # Embedding clients cached per provider (an adapter may override the
        # global embedding provider, so more than one can be in play).
        self._embedding_clients: Dict[str, Any] = {}
        # Phrase-embedding cache keyed by (provider, frozenset of candidate skill
        # names): embeddings differ by provider, so the provider is part of the key.
        self._phrase_cache: Dict[tuple, Dict[str, List[List[float]]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect(
        self,
        message: str,
        context_messages: Optional[List[Dict[str, Any]]],
        adapter_name: str,
    ) -> Optional[str]:
        """Return the inferred skill name for this turn, or ``None``.

        Never raises: any internal failure degrades to ``None`` (normal chat).
        """
        if not message or not message.strip():
            return None

        candidates = self._candidate_skills(adapter_name)
        if not candidates:
            return None

        # Stage 1 — embedding pre-filter (no LLM call on a miss).
        try:
            survivors = await self._prefilter(message, candidates, adapter_name)
        except Exception as e:
            logger.warning("Skill-intent embedding pre-filter failed: %s", e)
            return None
        if not survivors:
            return None

        # Stage 2 — LLM confirm.
        try:
            return await self._confirm(message, context_messages, survivors, adapter_name)
        except Exception as e:
            logger.warning("Skill-intent confirm step failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Candidate resolution
    # ------------------------------------------------------------------

    def _candidate_skills(self, adapter_name: str) -> List[Dict[str, Any]]:
        """Routable skills the adapter is allowed to use, with their match phrases."""
        adapter_config = self.adapter_manager.get_adapter_config(adapter_name) or {}
        available = (adapter_config.get("capabilities", {}) or {}).get("available_skills") or []
        if not available:
            return []
        available_set = set(available)

        candidates: List[Dict[str, Any]] = []
        for skill in self.adapter_manager.get_all_skills():
            name = skill.get("name")
            if not name or name not in available_set:
                continue
            if not skill.get("enabled", True):
                continue
            backing = skill.get("adapter_name")
            if not self._is_routable(backing):
                continue
            description = skill.get("description", "") or ""
            candidates.append({
                "name": name,
                "description": description,
                "phrases": self._phrases_for(name, description, backing),
            })
        return candidates

    def _is_routable(self, backing_adapter_name: Optional[str]) -> bool:
        """True if the skill's backing adapter is in scope for auto-routing."""
        if not backing_adapter_name:
            return False
        cfg = self.adapter_manager.get_adapter_config(backing_adapter_name) or {}
        if cfg.get("type") in self.ROUTABLE_ADAPTER_TYPES:
            return True
        # web-search ships as a passthrough adapter carrying web_search: true.
        if (cfg.get("capabilities", {}) or {}).get("web_search"):
            return True
        return False

    def _phrases_for(
        self, skill_name: str, description: str, backing_adapter_name: Optional[str]
    ) -> List[str]:
        """Phrase set embedded for the pre-filter: name + description + optional overrides."""
        cfg = self.adapter_manager.get_adapter_config(backing_adapter_name) or {}
        overrides = (cfg.get("capabilities", {}) or {}).get("routing_examples") or []
        phrases: List[str] = [skill_name]
        if description:
            phrases.append(description)
        phrases.extend(str(p) for p in overrides if p)
        return phrases

    # ------------------------------------------------------------------
    # Stage 1 — embedding pre-filter
    # ------------------------------------------------------------------

    async def _prefilter(
        self, message: str, candidates: List[Dict[str, Any]], adapter_name: str
    ) -> List[Dict[str, Any]]:
        provider = self._resolve_embedding_provider(adapter_name)
        if not provider:
            logger.warning(
                "No embedding provider (adapter embedding_provider or global "
                "embedding.provider) configured; skill-intent routing disabled"
            )
            return []
        client = await self._get_embedding_client(provider)
        if client is None:
            return []

        key = (provider, frozenset(c["name"] for c in candidates))
        phrase_index = self._phrase_cache.get(key)
        if phrase_index is None:
            phrase_index = await self._build_phrase_index(client, candidates)
            self._phrase_cache[key] = phrase_index

        query_vec = await client.embed_query(message)

        scored: List[tuple] = []
        for cand in candidates:
            vecs = phrase_index.get(cand["name"]) or []
            best = max((_cosine(query_vec, v) for v in vecs), default=0.0)
            if best >= self.embedding_threshold:
                scored.append((best, cand))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [cand for _, cand in scored[: self.max_candidates]]

    async def _build_phrase_index(
        self, client, candidates: List[Dict[str, Any]]
    ) -> Dict[str, List[List[float]]]:
        index: Dict[str, List[List[float]]] = {}
        for cand in candidates:
            phrases = cand["phrases"]
            index[cand["name"]] = await client.embed_documents(phrases) if phrases else []
        return index

    def _resolve_embedding_provider(self, adapter_name: str) -> Optional[str]:
        """Adapter's embedding_provider override if set, else the global default.

        Keeping routing in the same embedding space as the adapter's own file-RAG
        avoids surprises when an admin points the adapter at a non-default provider.
        """
        cfg = self.adapter_manager.get_adapter_config(adapter_name) or {}
        return cfg.get("embedding_provider") or (self.config.get("embedding") or {}).get("provider")

    async def _get_embedding_client(self, provider: str):
        client = self._embedding_clients.get(provider)
        if client is not None:
            return client
        client = await self.adapter_manager.get_overridden_embedding(provider)
        if client is not None and not getattr(client, "initialized", False):
            try:
                await client.initialize()
            except Exception as e:
                logger.warning("Embedding init failed for skill-intent routing: %s", e)
                return None
        self._embedding_clients[provider] = client
        return client

    # ------------------------------------------------------------------
    # Stage 2 — LLM confirm
    # ------------------------------------------------------------------

    async def _confirm(
        self,
        message: str,
        context_messages: Optional[List[Dict[str, Any]]],
        candidates: List[Dict[str, Any]],
        adapter_name: str,
    ) -> Optional[str]:
        provider = await self._resolve_confirm_provider(adapter_name)
        if provider is None:
            logger.warning("No provider available for skill-intent confirm step")
            return None

        prompt = self._build_confirm_prompt(message, context_messages, candidates)
        raw = await provider.generate(prompt, max_tokens=self.confirm_max_tokens, temperature=0.0)
        return self._parse_choice(raw, candidates)

    async def _resolve_confirm_provider(self, adapter_name: str):
        """Prefer the configured router_provider; fall back to the adapter's own provider."""
        if self.router_provider:
            return await self.adapter_manager.get_overridden_provider(
                self.router_provider,
                adapter_name,
                explicit_model_override=self.router_model,
            )
        cfg = self.adapter_manager.get_adapter_config(adapter_name) or {}
        inference_provider = cfg.get("inference_provider")
        if inference_provider:
            return await self.adapter_manager.get_overridden_provider(inference_provider, adapter_name)
        return None

    def _build_confirm_prompt(
        self,
        message: str,
        context_messages: Optional[List[Dict[str, Any]]],
        candidates: List[Dict[str, Any]],
    ) -> str:
        history = ""
        if context_messages:
            recent = context_messages[-(self.history_turns * 2):]
            lines = []
            for m in recent:
                role = (m.get("role") or "user").title()
                content = (m.get("content") or "").strip()
                if content:
                    lines.append(f"{role}: {content}")
            if lines:
                history = "Recent conversation:\n" + "\n".join(lines) + "\n\n"

        options = "\n".join(f"- {c['name']}: {c['description']}" for c in candidates)
        names = ", ".join(c["name"] for c in candidates)

        return (
            "You are a router that decides whether the user's latest message is a request to "
            "invoke a specialized tool (a \"skill\"), and if so which one.\n\n"
            f"{history}"
            f"User's latest message:\n{message}\n\n"
            f"Available skills:\n{options}\n\n"
            "Rules:\n"
            f"- Reply with EXACTLY ONE skill name from this list if the message is clearly asking to "
            f"produce that output: {names}.\n"
            "- Reply with NONE if the message is an ordinary question or conversation, or if you are "
            "unsure.\n"
            "- Output only the skill name or NONE. Do not explain.\n\n"
            "Answer:"
        )

    def _parse_choice(
        self, raw: Optional[str], candidates: List[Dict[str, Any]]
    ) -> Optional[str]:
        if not raw:
            return None
        text = raw.strip().strip("\"'`. ")
        if not text:
            return None
        first_line = text.splitlines()[0].strip().strip("\"'`. ")
        lowered = first_line.lower()
        if not lowered or lowered == "none":
            return None

        by_name = {c["name"].lower(): c["name"] for c in candidates}
        if lowered in by_name:
            return by_name[lowered]
        # Tolerate the model wrapping the name in a short phrase.
        for lname, original in by_name.items():
            if lname in lowered:
                return original
        return None
