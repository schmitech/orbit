"""
Model Selection Step ("auto" routing)

Runs only when the client requested model="auto" on an adapter whose
allowed_models/auto_model_selection capability makes that valid (resolved by
request_context_builder.build_context() into context.auto_select_requested /
context.model_routing_adapter_name — see docs/adapters/auto-model-selection.md).

Asks a small System One decision model a single `score` question to estimate
how much capability the turn needs, maps the answer to a routing_tier, and
sets context.runtime_provider/runtime_model_name/runtime_param_overrides from
the matching allowed_models entry so LLMInferenceStep picks it up exactly as
if the client had named that model explicitly.

This step never blocks the turn: any failure (no decision provider, service
error, low-confidence/refused/malformed answer, or no allowed_models entry
for the resolved tier) is logged and the context is returned unchanged, so
LLMInferenceStep falls through to the adapter's normal default model.
"""

import logging
import math
from typing import Any, Optional

from ..base import PipelineStep, ProcessingContext
from ._decision_support import validate_questions
from ._utils import add_usage_component

logger = logging.getLogger(__name__)

DEFAULT_CRITERIA = ["low", "medium", "high"]
DEFAULT_MIN_CONFIDENCE = 0.4
DEFAULT_INSTRUCTIONS = (
    "How much capability does this request need to answer well: a simple "
    "lookup/chat, moderate reasoning, or complex/multi-step reasoning?"
)


class ModelSelectionStep(PipelineStep):
    """Route a chat turn to an allowed_models entry via a decision model, when requested."""

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return bool(context.auto_select_requested)

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        routing_adapter_name = context.model_routing_adapter_name or context.adapter_name
        adapter_config = self._get_adapter_config(routing_adapter_name)
        allowed_models = adapter_config.get('allowed_models') or []
        tiered = {
            m['routing_tier']: m
            for m in allowed_models
            if m.get('routing_tier') and m.get('provider') and m.get('model')
        }
        if not tiered:
            logger.warning(
                f"auto_model_selection enabled for '{routing_adapter_name}' but no "
                f"allowed_models entries carry a routing_tier — falling back to default model"
            )
            return context

        auto_cfg = adapter_config.get('capabilities', {}).get('auto_model_selection') or {}
        criteria = auto_cfg.get('criteria') or DEFAULT_CRITERIA
        instructions = auto_cfg.get('instructions') or DEFAULT_INSTRUCTIONS
        min_confidence = auto_cfg.get('min_confidence', DEFAULT_MIN_CONFIDENCE)
        state_key = auto_cfg.get('state_key') or 'input'

        question = {"type": "score", "instructions": instructions, "criteria": criteria}
        error = validate_questions({"capability": question})
        if error:
            logger.warning(f"auto_model_selection question is invalid for '{routing_adapter_name}': {error}")
            return context

        config = self.container.get_or_none('config') or {}
        provider = (
            auto_cfg.get('decision_provider')
            or config.get('decision', {}).get('provider')
        )
        if not provider:
            logger.warning(f"No decision provider configured for auto_model_selection on '{routing_adapter_name}'")
            return context

        try:
            service = await self.container.get('adapter_manager').get_decision_service(
                provider, routing_adapter_name,
            )
        except Exception as e:  # noqa: BLE001 - routing is best-effort, must degrade to the default model
            logger.warning(f"Decision provider '{provider}' is unavailable for auto_model_selection: {e}")
            return context

        state = self._build_state(context, state_key, auto_cfg)
        model = auto_cfg.get('decision_model')
        try:
            result = await service.decide(state, {"capability": question}, model=model)
        except Exception as e:  # noqa: BLE001 - routing is best-effort, must degrade to the default model
            logger.warning(f"auto_model_selection decision call failed for '{routing_adapter_name}': {e}")
            return context

        usage = result.get("usage") or {}
        if usage.get("input_tokens") is not None or usage.get("output_tokens") is not None:
            prompt_tokens = usage.get("input_tokens") or 0
            completion_tokens = usage.get("output_tokens") or 0
            add_usage_component(
                context,
                {
                    "reported": True,
                    "provider": provider,
                    "model": result.get("model") or model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                source="model_routing",
            )

        tier = self._resolve_tier(result, criteria, min_confidence)
        if tier is None:
            return context

        match = tiered.get(tier)
        if not match:
            logger.warning(
                f"auto_model_selection resolved tier '{tier}' but '{routing_adapter_name}' "
                f"has no matching routing_tier entry — falling back to default model"
            )
            return context

        context.runtime_provider = match.get('provider')
        context.runtime_model_name = match.get('model')
        context.runtime_param_overrides = {
            key: match[key]
            for key in ('temperature', 'max_tokens', 'context_window', 'effort')
            if key in match and match[key] is not None
        } or None
        context.auto_selected_model = match.get('name')
        logger.debug(
            f"auto_model_selection: tier='{tier}' → '{context.auto_selected_model}' "
            f"({context.runtime_provider}/{context.runtime_model_name}) for '{routing_adapter_name}'"
        )
        return context

    def _resolve_tier(
        self, result: dict[str, Any], criteria: list, min_confidence: float,
    ) -> Optional[str]:
        answers = result.get("answers") or {}
        answer = answers.get("capability")
        if not isinstance(answer, dict) or answer.get("refused"):
            return None
        score = answer.get("score")
        confidence = answer.get("confidence")
        if (
            isinstance(score, bool) or not isinstance(score, (int, float))
            or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(score) or not math.isfinite(confidence)
        ):
            return None
        if confidence < min_confidence:
            return None
        index = round(score)
        index = max(0, min(len(criteria) - 1, index))
        return criteria[index]

    def _build_state(
        self, context: ProcessingContext, state_key: str, auto_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        state = {state_key: context.message}
        context_messages_count = auto_cfg.get('context_messages') or 0
        if context_messages_count and context.context_messages:
            recent = context.context_messages[-context_messages_count:]
            state["recent_context"] = "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')}" for m in recent
            )
        return state

    def _get_adapter_config(self, adapter_name: Optional[str]) -> dict[str, Any]:
        if not adapter_name or not self.container.has('adapter_manager'):
            return {}
        return self.container.get('adapter_manager').get_adapter_config(adapter_name) or {}
