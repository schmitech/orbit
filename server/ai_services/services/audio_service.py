"""
Audio service interface and base implementations.

This module defines the common interface for all audio services,
providing a unified API for text-to-speech (TTS) and speech-to-text (STT)
regardless of the underlying provider.
"""

from abc import abstractmethod
from typing import Dict, Any, Optional, Union
import logging
from io import BytesIO

from ..base import ProviderAIService, ServiceType


class AudioService(ProviderAIService):
    """
    Base class for all audio services.

    This class defines the common interface that all audio service
    implementations must follow, regardless of provider (OpenAI, Google,
    Anthropic, Ollama, Cohere, etc.).

    Key Methods:
        - text_to_speech: Convert text to speech audio
        - speech_to_text: Convert speech audio to text
        - transcribe: Transcribe audio to text (alias for speech_to_text)
        - translate: Translate audio from one language to another

    Configuration Support:
        - Configurable audio models via config
        - Support for multiple audio formats
        - Language and voice customization
    """

    # Class attribute for service type
    service_type = ServiceType.AUDIO

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the audio service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'openai', 'google')
        """
        super().__init__(config, ServiceType.AUDIO, provider_name)

    @abstractmethod
    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Convert text to speech audio.

        This method generates audio from text using the configured TTS model.

        Args:
            text: Text to convert to speech
            voice: Optional voice identifier (provider-specific)
            format: Optional audio format (e.g., 'mp3', 'wav', 'opus')
            **kwargs: Additional provider-specific parameters

        Returns:
            Audio data as bytes

        Example:
            >>> service = OpenAIAudioService(config)
            >>> await service.initialize()
            >>> audio = await service.text_to_speech("Hello, world!", voice="alloy")
            >>> with open("output.mp3", "wb") as f:
            ...     f.write(audio)
        """
        pass

    @abstractmethod
    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Convert speech audio to text.

        This method transcribes audio to text using the configured STT model.

        Args:
            audio: Audio data (file path or bytes)
            language: Optional language code (e.g., 'en-US', 'fr-FR')
            **kwargs: Additional provider-specific parameters

        Returns:
            Transcribed text

        Example:
            >>> service = OpenAIAudioService(config)
            >>> await service.initialize()
            >>> text = await service.speech_to_text("audio.wav", language="en-US")
            >>> print(text)
            "Hello, world!"
        """
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Transcribe audio to text.

        This is an alias for speech_to_text, providing a more explicit
        interface for transcription tasks.

        Args:
            audio: Audio data (file path or bytes)
            language: Optional language code (e.g., 'en-US', 'fr-FR')
            **kwargs: Additional provider-specific parameters

        Returns:
            Transcribed text

        Example:
            >>> text = await service.transcribe("recording.mp3", language="en-US")
        """
        pass

    @abstractmethod
    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """
        Translate audio from one language to another.

        This method transcribes audio in the source language and translates
        it to the target language.

        Args:
            audio: Audio data (file path or bytes)
            source_language: Optional source language code (auto-detect if not provided)
            target_language: Target language code (default: 'en')
            **kwargs: Additional provider-specific parameters

        Returns:
            Translated text in target language

        Example:
            >>> service = OpenAIAudioService(config)
            >>> await service.initialize()
            >>> translated = await service.translate(
            ...     "french_audio.wav",
            ...     source_language="fr-FR",
            ...     target_language="en"
            ... )
            >>> print(translated)
            "Hello, how are you?"
        """
        pass

    def _prepare_audio(self, audio: Union[str, bytes]) -> bytes:
        """
        Prepare audio for processing.

        Args:
            audio: Audio data in various formats

        Returns:
            Audio as bytes
        """
        if isinstance(audio, str):
            # Assume it's a file path
            with open(audio, 'rb') as f:
                return f.read()
        elif isinstance(audio, bytes):
            return audio
        else:
            raise ValueError(f"Unsupported audio type: {type(audio)}")

    def _get_audio_format(self, audio: Union[str, bytes]) -> str:
        """
        Get audio format from file extension or content.

        Args:
            audio: Audio data or file path

        Returns:
            Audio format string (e.g., 'mp3', 'wav', 'opus')
        """
        if isinstance(audio, str):
            # Extract extension from file path
            ext = audio.split('.')[-1].lower()
            format_map = {
                'mp3': 'mp3',
                'wav': 'wav',
                'opus': 'opus',
                'ogg': 'ogg',
                'flac': 'flac',
                'm4a': 'm4a',
                'aac': 'aac',
            }
            return format_map.get(ext, 'mp3')  # Default to mp3
        else:
            # Default format for bytes
            return 'mp3'

    def _validate_audio_format(self, format: str) -> bool:
        """
        Validate audio format is supported.

        Args:
            format: Audio format string

        Returns:
            True if format is supported, False otherwise
        """
        supported_formats = ['mp3', 'wav', 'opus', 'ogg', 'flac', 'm4a', 'aac']
        return format.lower() in supported_formats


class AudioResult:
    """
    Structured result for audio operations.

    This class provides a standardized way to return audio results
    with metadata.
    """

    def __init__(
        self,
        text: Optional[str] = None,
        audio: Optional[bytes] = None,
        language: Optional[str] = None,
        format: Optional[str] = None,
        provider: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize audio result.

        Args:
            text: Transcribed or translated text (for STT operations)
            audio: Generated audio data (for TTS operations)
            language: Detected or specified language
            format: Audio format
            provider: Provider name
            metadata: Optional metadata
        """
        self.text = text
        self.audio = audio
        self.language = language
        self.format = format
        self.provider = provider
        self.metadata = metadata or {}

    def __str__(self) -> str:
        """Return the text content if available."""
        return self.text or ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'provider': self.provider,
            'metadata': self.metadata
        }
        if self.text is not None:
            result['text'] = self.text
        if self.audio is not None:
            result['audio'] = f"<{len(self.audio)} bytes>"
            result['audio_size'] = len(self.audio)
        if self.language is not None:
            result['language'] = self.language
        if self.format is not None:
            result['format'] = self.format
        return result


# Helper function for service creation
def create_audio_service(
    provider: str,
    config: Dict[str, Any]
) -> AudioService:
    """
    Factory function to create an audio service.

    This is a convenience function that will use the AIServiceFactory
    once services are registered.

    Args:
        provider: Provider name (e.g., 'openai', 'google')
        config: Configuration dictionary

    Returns:
        Audio service instance

    Example:
        >>> service = create_audio_service('openai', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.AUDIO,
        provider,
        config
    )

