"""
Cohere audio service placeholder implementation.

This is a placeholder implementation as Cohere doesn't currently
have native audio APIs. This service can be updated when Cohere
adds audio support.
"""

from typing import Dict, Any, Optional, Union

from ...base import ServiceType
from ...providers import CohereBaseService
from ...services import AudioService


class CohereAudioService(AudioService, CohereBaseService):
    """
    Cohere audio service placeholder.

    Note: Cohere doesn't currently have native audio APIs.
    This is a placeholder that will be implemented when audio support is added.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Cohere audio service placeholder."""
        # Initialize via CohereBaseService first
        CohereBaseService.__init__(self, config, ServiceType.AUDIO, "cohere")
        
        # Get audio-specific configuration (placeholder)
        provider_config = self._extract_provider_config()
        self.stt_model = provider_config.get('stt_model')
        self.tts_model = provider_config.get('tts_model')

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Placeholder for text-to-speech (not yet supported by Cohere)."""
        raise NotImplementedError(
            "Cohere doesn't currently support text-to-speech. "
            "This feature will be available when Cohere adds audio API support."
        )

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Placeholder for speech-to-text (not yet supported by Cohere)."""
        raise NotImplementedError(
            "Cohere doesn't currently support speech-to-text. "
            "This feature will be available when Cohere adds audio API support."
        )

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Placeholder for transcription (not yet supported by Cohere)."""
        raise NotImplementedError(
            "Cohere doesn't currently support audio transcription. "
            "This feature will be available when Cohere adds audio API support."
        )

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """Placeholder for audio translation (not yet supported by Cohere)."""
        raise NotImplementedError(
            "Cohere doesn't currently support audio translation. "
            "This feature will be available when Cohere adds audio API support."
        )

