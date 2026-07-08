"""
Audio Generation Step

Generates speech audio from the user's text when the adapter is of type
'audio_generation'. Replaces LLMInferenceStep for such adapters.

This is distinct from the return_audio/tts_voice inline chat TTS flow
(server/services/chat_handlers/audio_handler.py) — that flow augments a
normal chat reply with parallel audio; this step's adapter *is* the TTS
generation itself, producing a downloadable audio file.
"""

import base64
import logging
from typing import Optional, Dict, Any

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)


def _get_adapter_type(container, adapter_name: str) -> Optional[str]:
    """Return the adapter's 'type' field, or None if unavailable."""
    if not adapter_name or not container.has('adapter_manager'):
        return None
    try:
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            return adapter_config.get('type')
    except Exception:
        pass
    return None


class AudioGenerationStep(PipelineStep):
    """
    Generate speech audio from the user's text.

    Executes only for adapters whose 'type' is 'audio_generation'.
    Stores the result in context.generated_audio (base64),
    context.generated_audio_format, and context.generated_audio_revised_prompt.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == 'audio_generation'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        audio_service = await self._get_audio_service(context)
        if audio_service is None:
            context.set_error("No audio generation service is available for this adapter.")
            return context

        text = await self._rewrite_text(context)
        try:
            audio_bytes = await audio_service.text_to_speech(text, voice=context.tts_voice)
            context.generated_audio = base64.b64encode(audio_bytes).decode("utf-8")
            context.generated_audio_format = self._resolve_format(context)
            context.generated_audio_revised_prompt = text
            context.response = text
        except Exception as e:
            logger.error(f"Audio generation failed: {e}", exc_info=True)
            context.set_error(f"Audio generation failed: {e}")

        return context

    async def _resolve_rewrite_provider(self, context: ProcessingContext):
        """Resolve the LLM provider used to turn the request + context into spoken text.

        Priority:
        1. Explicit `rewrite_provider` field on the skill adapter config.
        2. Original (retrieval) adapter's inference provider (e.g. openai on customer-orders).
        3. Skill adapter's inference_provider.
        4. Global llm_provider fallback.
        """
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')

            if context.adapter_name:
                skill_config = adapter_manager.get_adapter_config(context.adapter_name)
                if skill_config:
                    rewrite_provider_name = skill_config.get('rewrite_provider')
                    rewrite_model = skill_config.get('rewrite_model') or None
                    if rewrite_provider_name:
                        try:
                            provider = await adapter_manager.get_overridden_provider(
                                rewrite_provider_name, context.adapter_name,
                                explicit_model_override=rewrite_model,
                            )
                            if provider:
                                logger.debug(
                                    "Using rewrite_provider '%s' (model=%r) for audio text rewrite",
                                    rewrite_provider_name, rewrite_model,
                                )
                                return provider
                        except Exception as e:
                            logger.debug(
                                "Could not resolve rewrite_provider '%s': %s",
                                rewrite_provider_name, e,
                            )

            for adapter_name in (context.original_adapter_name, context.adapter_name):
                if not adapter_name:
                    continue
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if not adapter_config:
                    continue
                inference_provider = adapter_config.get('inference_provider')
                if inference_provider:
                    try:
                        provider = await adapter_manager.get_overridden_provider(
                            inference_provider, adapter_name
                        )
                        if provider:
                            logger.debug(
                                "Using inference provider '%s' (adapter '%s') for audio text rewrite",
                                inference_provider, adapter_name,
                            )
                            return provider
                    except Exception as e:
                        logger.debug("Could not resolve provider for '%s': %s", adapter_name, e)

        return self.container.get_or_none('llm_provider')

    async def _rewrite_text(self, context: ProcessingContext) -> str:
        """Resolve the text to speak from the user's request + conversation history/context.

        A one-shot request with no conversation history and no retrieved context (e.g. a bare
        curl call) is spoken verbatim — there's nothing to resolve. When invoked as a skill mid
        conversation, the request is combined with history/context via an LLM so instructions
        like "summarize this and explain in simple terms" produce real spoken content instead of
        being read aloud literally.
        """
        if not context.context_messages and not context.formatted_context:
            return context.message

        llm_provider = await self._resolve_rewrite_provider(context)
        if not llm_provider:
            logger.warning("No llm_provider available — speaking the raw message for audio generation")
            return context.message

        config = self.container.get_or_none('config') or {}
        llm_cfg = config.get('audio_generation', {}).get('llm', {})
        max_tokens = llm_cfg.get('max_tokens', 800)
        temperature = llm_cfg.get('temperature', 0.3)
        history_limit = llm_cfg.get('history_limit', 6)

        recent_msgs = context.context_messages[-history_limit:] if context.context_messages else []
        if recent_msgs and recent_msgs[-1].get('role') == 'user' and recent_msgs[-1].get('content', '').strip() == context.message.strip():
            recent_msgs = recent_msgs[:-1]

        history = []
        for msg in recent_msgs:
            role = msg.get('role', 'user').title()
            content = msg.get('content', '')
            if role and content:
                history.append(f"{role}: {content}")

        history_text = "\n".join(history) if history else "No prior conversation."
        context_text = f"\nRetrieved Data/Context:\n{context.formatted_context}\n" if context.formatted_context else ""

        rewrite_prompt = (
            "You are preparing text to be read aloud by a text-to-speech engine.\n"
            "Your task: fulfil the user's request using the conversation history and data/context "
            "below, and output ONLY the resulting text to be spoken.\n\n"
            "Rules:\n"
            "1. If the request references prior conversation or data (e.g. 'summarize this', "
            "'explain this in simple terms', 'read this back to me'), resolve it using the "
            "history/context and produce the actual spoken content — not a restatement of the request.\n"
            "2. Write in natural, spoken sentence flow. No markdown, no headings, no bullet lists, "
            "no code blocks, no citation markers — a TTS engine will read exactly what you output.\n"
            "3. If the request is already self-contained plain text with nothing to resolve from "
            "context, return it as-is (lightly cleaned up if it contains formatting artifacts).\n"
            "4. Keep it concise — this will be heard, not read.\n"
            "5. Output ONLY the final text. No preamble, no explanation, no quotes.\n\n"
            f"Conversation History:\n{history_text}\n"
            f"{context_text}"
            f"User request: {context.message}\n"
            "Text to speak:"
        )

        try:
            rewritten = await llm_provider.generate(rewrite_prompt, max_tokens=max_tokens, temperature=temperature)
            rewritten = rewritten.strip()
            for quote in ('"', "'"):
                if rewritten.startswith(quote) and rewritten.endswith(quote) and len(rewritten) > 2:
                    rewritten = rewritten[1:-1].strip()
                    break
            if rewritten:
                logger.debug("Rewrote audio text: %r -> %r", context.message[:80], rewritten[:80])
                return rewritten
            logger.warning("Text rewrite returned empty response — speaking the raw message")
        except Exception as e:
            logger.warning(f"Failed to rewrite audio text: {e}")

        return context.message

    async def _get_audio_service(self, context: ProcessingContext):
        """Resolve the TTS audio service from config and adapter settings."""
        config = self.container.get_or_none('config') or {}
        provider = self._resolve_provider(context, config)
        if not provider:
            logger.warning("No TTS provider configured.")
            return None

        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType
        return await AIServiceFactory.create_and_initialize_service(
            ServiceType.AUDIO, provider, config, use_cache=True,
        )

    def _resolve_provider(self, context: ProcessingContext, config: Dict[str, Any]) -> Optional[str]:
        """Return the TTS provider name for this request.

        Resolution order:
        1. Adapter-level tts_provider
        2. Global tts.provider (from tts.yaml)
        """
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
                if adapter_config:
                    provider = adapter_config.get('tts_provider')
                    if provider:
                        return provider
            except Exception:
                pass

        return config.get('tts', {}).get('provider')

    def _resolve_format(self, context: ProcessingContext) -> str:
        """Return the configured audio format for the resolved provider."""
        config = self.container.get_or_none('config') or {}
        provider = self._resolve_provider(context, config)
        tts_providers_config = config.get('tts_providers', {}) or {}
        provider_config = tts_providers_config.get(provider, {}) or {}
        return provider_config.get('tts_format', 'mp3')
