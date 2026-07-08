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

        text = context.message
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
