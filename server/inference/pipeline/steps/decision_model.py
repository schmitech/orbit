"""
Decision Model Step

Runs a "System One" decision model (Jev-style: nimble, tev1, TypeSafe jev-latest)
when the adapter is of type 'decision_model'. Replaces LLMInferenceStep for such
adapters: the model returns typed answers (choice / noul / score) with
probabilities instead of generated text.

The adapter's `config.questions` define the decision. The user message becomes
the state (`{state_key: message}`), or the message may be a JSON object
`{"state": {...}, "questions": {...}}`; its questions are only honored when
`config.allow_question_override` is true.
"""

import json
import logging
from typing import Any, Optional

from ..base import PipelineStep, ProcessingContext
from ._utils import get_adapter_type, record_media_generation_usage

logger = logging.getLogger(__name__)

QUESTION_TYPES = ("choice", "noul", "score")


def validate_questions(questions: Any) -> Optional[str]:
    """Return an error message if the question definitions are invalid, else None."""
    if not isinstance(questions, dict) or not questions:
        return "Decision questions must be a non-empty mapping of question name to definition."
    for name, spec in questions.items():
        if not isinstance(name, str) or not name.strip():
            return "Decision question names must be non-empty strings."
        if not isinstance(spec, dict):
            return f"Decision question '{name}' must be an object."
        qtype = spec.get("type")
        if qtype not in QUESTION_TYPES:
            return f"Decision question '{name}' has invalid type {qtype!r}; expected one of {', '.join(QUESTION_TYPES)}."
        instructions = spec.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            return f"Decision question '{name}' requires non-empty 'instructions'."
        criteria = spec.get("criteria")
        if qtype == "choice" and (not isinstance(criteria, dict) or not criteria):
            return f"Choice question '{name}' requires a non-empty 'criteria' mapping of option to description."
        if qtype == "score" and (not isinstance(criteria, list) or len(criteria) < 2):
            return f"Score question '{name}' requires a 'criteria' list of at least 2 ordered levels."
    return None


class DecisionModelStep(PipelineStep):
    """
    Answer typed decision questions about the user's input.

    Executes only for adapters whose 'type' is 'decision_model'. Stores the full
    provider result in context.decision and the answers JSON in context.response.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return get_adapter_type(self.container, context.adapter_name) == 'decision_model'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        adapter_config = self._get_adapter_config(context.adapter_name)
        decision_config = adapter_config.get('config') or {}

        state, questions = self._parse_input(context.message, decision_config)
        error = validate_questions(questions)
        if error:
            context.set_error(error)
            return context

        config = self.container.get_or_none('config') or {}
        provider = (
            context.runtime_provider
            or adapter_config.get('decision_provider')
            or config.get('decision', {}).get('provider')
        )
        if not provider:
            context.set_error("No decision provider is configured for this adapter.")
            return context

        try:
            service = await self.container.get('adapter_manager').get_decision_service(
                provider, context.adapter_name,
            )
        except Exception as e:
            logger.exception(f"Failed to load decision provider '{provider}'")
            context.set_error(f"Decision provider '{provider}' is unavailable: {e}")
            return context

        model = context.runtime_model_name or adapter_config.get('model')
        try:
            result = await service.decide(state, questions, model=model)
        except Exception as e:
            logger.exception("Decision model failed")
            context.set_error(f"Decision model failed: {e}")
            return context

        context.decision = result
        context.response = json.dumps(result.get("answers", {}), indent=2)
        context.runtime_provider = provider
        context.runtime_model_name = result.get("model") or model or getattr(service, "model", None)

        usage = result.get("usage") or {}
        token_usage = None
        if usage.get("input_tokens") is not None or usage.get("output_tokens") is not None:
            token_usage = {
                "reported": True,
                "prompt_tokens": usage.get("input_tokens") or 0,
                "completion_tokens": usage.get("output_tokens") or 0,
            }
        record_media_generation_usage(
            self.container, context, provider, context.runtime_model_name,
            call_type="decision", token_usage=token_usage,
        )
        return context

    def _get_adapter_config(self, adapter_name: Optional[str]) -> dict[str, Any]:
        if not adapter_name or not self.container.has('adapter_manager'):
            return {}
        return self.container.get('adapter_manager').get_adapter_config(adapter_name) or {}

    def _parse_input(self, message: str, decision_config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        """Return (state, questions) for this request."""
        questions = decision_config.get('questions')
        state_key = decision_config.get('state_key') or 'input'

        payload = None
        stripped = (message or "").strip()
        if stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None

        if isinstance(payload, dict) and isinstance(payload.get("state"), dict):
            if "questions" in payload:
                if decision_config.get('allow_question_override'):
                    questions = payload["questions"]
                else:
                    logger.warning("Ignoring request-supplied decision questions: allow_question_override is off")
            return payload["state"], questions

        return {state_key: message}, questions
