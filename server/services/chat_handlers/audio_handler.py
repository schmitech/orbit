"""
Audio Handler

Manages text-to-speech audio generation with support for both
single and streaming audio generation.
"""

import logging
from typing import Dict, Any, Optional, Tuple
import asyncio

logger = logging.getLogger(__name__)

# Optional CUDA imports for GPU monitoring
try:
    import torch
    CUDA_AVAILABLE = torch.cuda.is_available() if torch is not None else False
except ImportError:
    CUDA_AVAILABLE = False
    torch = None


class AudioHandler:
    """Handles text-to-speech audio generation."""

    def __init__(
        self,
        config: Dict[str, Any],
        adapter_manager=None
    ):
        """
        Initialize the audio handler.

        Args:
            config: Application configuration
            adapter_manager: Optional adapter manager for getting provider settings
        """
        self.config = config
        self.adapter_manager = adapter_manager

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

        # GPU-related configuration
        self.enable_gpu_monitoring = CUDA_AVAILABLE
        self.gpu_error_retry_count = 2  # Retry GPU errors up to 2 times

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

    def _is_gpu_error(self, error: Exception) -> bool:
        """
        Check if an error is GPU/CUDA related.

        Args:
            error: Exception to check

        Returns:
            True if error is GPU-related
        """
        error_str = str(error).lower()
        gpu_keywords = [
            'cuda', 'gpu', 'out of memory', 'oom', 'cudnn',
            'device-side assert', 'cuda error', 'cublas'
        ]
        return any(keyword in error_str for keyword in gpu_keywords)

    def _log_gpu_memory(self, context: str = ""):
        """
        Log GPU memory usage if monitoring is enabled.

        Args:
            context: Context string for the log message
        """
        if not self.enable_gpu_monitoring or not CUDA_AVAILABLE:
            return

        try:
            allocated = torch.cuda.memory_allocated(0) / 1024**2
            reserved = torch.cuda.memory_reserved(0) / 1024**2
            max_allocated = torch.cuda.max_memory_allocated(0) / 1024**2
            logger.debug(
                f"GPU Memory {context} - "
                f"Allocated: {allocated:.2f} MB, "
                f"Reserved: {reserved:.2f} MB, "
                f"Peak: {max_allocated:.2f} MB"
            )
        except Exception:
            pass  # Silently fail if GPU monitoring fails

    async def _get_audio_service(self, provider: str):
        """
        Get or create an audio service for the given provider.

        Args:
            provider: Audio provider name

        Returns:
            Audio service instance
        """
        if provider in self._audio_services:
            service = self._audio_services[provider]
            # Verify service is still healthy (especially for GPU services)
            if hasattr(service, 'connection_verified'):
                if not service.connection_verified:
                    logger.warning(f"Audio service {provider} connection not verified, reinitializing")
                    if hasattr(service, 'initialize'):
                        await service.initialize()
            return service

        # Import audio service factory
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType
        from ai_services.registry import register_all_services

        # Ensure services are registered
        register_all_services(self.config)

        # Create audio service
        try:
            audio_service = AIServiceFactory.create_service(
                ServiceType.AUDIO,
                provider,
                self.config
            )
        except ValueError as e:
            # This happens when sound is globally disabled or provider is not registered
            logger.warning(f"Failed to create audio service for provider '{provider}': {str(e)}")
            return None

        if not audio_service:
            logger.warning(f"Failed to create audio service for provider: {provider}")
            return None

        # Initialize service if needed
        if hasattr(audio_service, 'initialize'):
            try:
                await audio_service.initialize()
                self._log_gpu_memory(f"after initializing {provider}")
            except Exception as e:
                if self._is_gpu_error(e):
                    logger.error(f"GPU error during {provider} initialization: {str(e)}")
                    # Try to clear GPU cache and retry once
                    if CUDA_AVAILABLE:
                        torch.cuda.empty_cache()
                        try:
                            await audio_service.initialize()
                            self._log_gpu_memory(f"after retry initializing {provider}")
                        except Exception as retry_error:
                            logger.error(f"Failed to initialize {provider} after GPU cleanup: {str(retry_error)}")
                            return None
                else:
                    logger.error(f"Failed to initialize audio service {provider}: {str(e)}")
                    return None

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

        # Retry logic for GPU errors
        last_error = None
        for attempt in range(self.gpu_error_retry_count + 1):
            try:
                self._log_gpu_memory(f"before audio generation (attempt {attempt + 1})")

                # Generate audio
                audio_data = await audio_service.text_to_speech(
                    text=processed_text,
                    voice=tts_voice,
                    format=None  # Use default format
                )

                self._log_gpu_memory("after audio generation")

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

                logger.debug(f"Generated audio: {len(audio_data)} bytes, format: {audio_format}")

                return audio_data, audio_format

            except Exception as e:
                last_error = e
                is_gpu_error = self._is_gpu_error(e)

                if is_gpu_error and attempt < self.gpu_error_retry_count:
                    logger.warning(
                        f"GPU error during audio generation (attempt {attempt + 1}/{self.gpu_error_retry_count + 1}): {str(e)}"
                    )
                    # Clear GPU cache and wait before retry
                    if CUDA_AVAILABLE:
                        torch.cuda.empty_cache()
                        # Small delay to let GPU recover
                        await asyncio.sleep(0.5)
                    continue
                else:
                    # Non-GPU error or max retries reached
                    logger.error(
                        f"Error generating audio: {str(e)}",
                        exc_info=not is_gpu_error  # Full traceback for non-GPU errors
                    )
                    break

        # All retries exhausted
        if last_error:
            if self._is_gpu_error(last_error):
                logger.error(
                    f"GPU error after {self.gpu_error_retry_count + 1} attempts: {str(last_error)}. "
                    f"Consider reducing batch size or text length."
                )
            else:
                logger.error(f"Failed to generate audio after retries: {str(last_error)}")

        return None, None

    async def cleanup(self):
        """
        Clean up audio services and release GPU resources.

        This should be called when the handler is no longer needed
        to properly release GPU memory and connections.
        """
        logger.debug("Cleaning up audio handler resources")

        # Close all cached audio services
        for provider, service in self._audio_services.items():
            try:
                if hasattr(service, 'close'):
                    await service.close()
                    logger.debug(f"Closed audio service: {provider}")
            except Exception as e:
                logger.warning(f"Error closing audio service {provider}: {str(e)}")

        # Clear the cache
        self._audio_services.clear()

        # Clear GPU cache if available
        if CUDA_AVAILABLE:
            try:
                torch.cuda.empty_cache()
                self._log_gpu_memory("after cleanup")
            except Exception:
                pass

        logger.debug("Audio handler cleanup completed")
