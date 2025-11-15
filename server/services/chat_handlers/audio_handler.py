"""
Audio Handler

Manages text-to-speech audio generation with support for both
single and streaming audio generation.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class AudioHandler:
    """Handles text-to-speech audio generation."""

    def __init__(
        self,
        config: Dict[str, Any],
        adapter_manager=None,
        verbose: bool = False
    ):
        """
        Initialize the audio handler.

        Args:
            config: Application configuration
            adapter_manager: Optional adapter manager for getting provider settings
            verbose: Enable verbose logging
        """
        self.config = config
        self.adapter_manager = adapter_manager
        self.verbose = verbose

        # Extract TTS limits from config
        sound_config = config.get('sound', {})
        self.tts_limits = sound_config.get('tts_limits', {})
        self.max_text_length = self.tts_limits.get('max_text_length', 4096)
        self.max_audio_size_mb = self.tts_limits.get('max_audio_size_mb', 5)
        self.truncate_text = self.tts_limits.get('truncate_text', True)
        self.warn_on_truncate = self.tts_limits.get('warn_on_truncate', True)

        # Default audio provider from global config
        self.default_provider = sound_config.get('provider', 'openai')

        # Cache for audio services to avoid repeated creation
        self._audio_services = {}

    def _truncate_text(self, text: str) -> Optional[str]:
        """
        Truncate text to fit within TTS limits.

        Args:
            text: Text to potentially truncate

        Returns:
            Truncated text or None if text exceeds limit and truncation is disabled
        """
        original_length = len(text)

        if original_length <= self.max_text_length:
            return text

        if not self.truncate_text:
            logger.warning(
                f"TTS text length ({original_length}) exceeds limit ({self.max_text_length}), "
                f"skipping audio generation"
            )
            return None

        # Truncate text at sentence boundary if possible
        truncated = text[:self.max_text_length]

        # Try to end at a sentence boundary
        last_period = truncated.rfind('.')
        last_question = truncated.rfind('?')
        last_exclaim = truncated.rfind('!')
        last_sentence_end = max(last_period, last_question, last_exclaim)

        if last_sentence_end > self.max_text_length * 0.8:  # At least 80% of allowed length
            truncated = truncated[:last_sentence_end + 1]

        if self.warn_on_truncate:
            logger.warning(
                f"TTS text truncated from {original_length} to {len(truncated)} chars "
                f"(limit: {self.max_text_length})"
            )

        return truncated

    def _get_audio_provider(self, adapter_name: str) -> str:
        """
        Get the audio provider for the given adapter.

        Args:
            adapter_name: The adapter name

        Returns:
            Audio provider name
        """
        if adapter_name and self.adapter_manager:
            adapter_config = self.adapter_manager.get_adapter_config(adapter_name)
            if adapter_config:
                provider = adapter_config.get('audio_provider')
                if provider:
                    return provider

        return self.default_provider

    async def _get_audio_service(self, provider: str):
        """
        Get or create an audio service for the given provider.

        Args:
            provider: Audio provider name

        Returns:
            Audio service instance
        """
        if provider in self._audio_services:
            return self._audio_services[provider]

        # Import audio service factory
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType
        from ai_services.registry import register_all_services

        # Ensure services are registered
        register_all_services(self.config)

        # Create audio service
        audio_service = AIServiceFactory.create_service(
            ServiceType.AUDIO,
            provider,
            self.config
        )

        if not audio_service:
            logger.warning(f"Failed to create audio service for provider: {provider}")
            return None

        # Initialize service if needed
        if hasattr(audio_service, 'initialize'):
            await audio_service.initialize()

        # Cache the service
        self._audio_services[provider] = audio_service
        return audio_service

    def _get_audio_format(self, provider: str) -> str:
        """
        Get the audio format for the given provider.

        Args:
            provider: Audio provider name

        Returns:
            Audio format string
        """
        sounds_config = self.config.get('sounds', {})
        provider_config = sounds_config.get(provider, {})
        return provider_config.get('tts_format', 'mp3')

    async def generate_audio(
        self,
        text: str,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate audio from text using the adapter's audio provider.

        Args:
            text: Text to convert to speech
            adapter_name: Adapter name to get audio provider from
            tts_voice: Optional voice to use for TTS
            language: Optional language code

        Returns:
            Tuple of (audio_data, audio_format) or (None, None) if generation fails
        """
        try:
            # Apply text length limit
            processed_text = self._truncate_text(text)
            if processed_text is None:
                return None, None

            # Get audio provider
            provider = self._get_audio_provider(adapter_name)
            if not provider:
                logger.warning("No audio provider configured")
                return None, None

            # Get audio service
            audio_service = await self._get_audio_service(provider)
            if not audio_service:
                return None, None

            # Generate audio
            audio_data = await audio_service.text_to_speech(
                text=processed_text,
                voice=tts_voice,
                format=None  # Use default format
            )

            # Check audio size limit
            max_audio_size_bytes = self.max_audio_size_mb * 1024 * 1024
            if len(audio_data) > max_audio_size_bytes:
                logger.warning(
                    f"Generated audio size ({len(audio_data) / 1024 / 1024:.2f}MB) exceeds "
                    f"limit ({self.max_audio_size_mb}MB), skipping audio"
                )
                return None, None

            # Get audio format
            audio_format = self._get_audio_format(provider)

            if self.verbose:
                logger.info(f"Generated audio: {len(audio_data)} bytes, format: {audio_format}")

            return audio_data, audio_format

        except Exception as e:
            logger.error(f"Error generating audio: {str(e)}", exc_info=True)
            return None, None
