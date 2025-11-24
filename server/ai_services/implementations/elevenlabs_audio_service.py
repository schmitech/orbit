"""
ElevenLabs audio service implementation using unified architecture.

This implementation provides high-quality text-to-speech using ElevenLabs API.
ElevenLabs is known for natural-sounding voices and multilingual support.
"""

from typing import Dict, Any, Optional, Union
import aiohttp
import logging

from ..base import ProviderAIService, ServiceType
from ..services import AudioService



logger = logging.getLogger(__name__)
class ElevenLabsAudioService(AudioService, ProviderAIService):
    """
    ElevenLabs audio service using unified architecture.

    Supports:
    - High-quality text-to-speech with natural voices
    - Multilingual support
    - Voice cloning and customization
    - Multiple output formats

    Note: ElevenLabs is primarily a TTS service. STT is not supported.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the ElevenLabs audio service."""
        # Initialize base class
        ProviderAIService.__init__(self, config, ServiceType.AUDIO, "elevenlabs")

        # Get audio-specific configuration
        provider_config = self._extract_provider_config()

        # API configuration - use base class method for API key resolution
        self.api_key = self._resolve_api_key("ELEVENLABS_API_KEY", "api_key")
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key is required. Set ELEVENLABS_API_KEY environment "
                "variable or provide in configuration."
            )
        self.api_base = provider_config.get('api_base', 'https://api.elevenlabs.io/v1')

        # TTS configuration
        self.tts_model = provider_config.get('tts_model', 'eleven_multilingual_v2')
        self.tts_voice = provider_config.get('tts_voice', 'EXAVITQu4vr4xnSDxMaL')
        self.tts_format = provider_config.get('tts_format', 'mp3_44100_128')
        self.tts_stability = provider_config.get('tts_stability', 0.5)
        self.tts_similarity_boost = provider_config.get('tts_similarity_boost', 0.75)
        self.tts_style = provider_config.get('tts_style', 0.0)
        self.tts_use_speaker_boost = provider_config.get('tts_use_speaker_boost', True)

        # STT not supported
        self.stt_model = None

        # Session for HTTP requests
        self._session = None

        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> bool:
        """Initialize the ElevenLabs audio service."""
        try:
            if self.initialized:
                return True

            # API key should already be validated in __init__, but double-check
            if not self.api_key:
                raise ValueError(
                    "ElevenLabs API key is required. "
                    "Set ELEVENLABS_API_KEY environment variable or provide in configuration."
                )

            # Create aiohttp session
            self._session = aiohttp.ClientSession(
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json"
                }
            )

            self.initialized = True
            logger.info(f"ElevenLabs audio service initialized with model: {self.tts_model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ElevenLabs audio service: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the ElevenLabs audio service and release resources."""
        if self._session:
            await self._session.close()
            self._session = None

        self.initialized = False

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Convert text to speech audio using ElevenLabs.

        Args:
            text: Text to convert to speech
            voice: Optional voice ID (defaults to configured voice)
            format: Optional output format (defaults to configured format)
            **kwargs: Additional parameters:
                - model: Override default model
                - stability: Voice stability (0.0-1.0)
                - similarity_boost: Clarity enhancement (0.0-1.0)
                - style: Style exaggeration (0.0-1.0, v2 models only)
                - use_speaker_boost: Enable speaker boost

        Returns:
            Audio data as bytes
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Use provided voice or default
            voice_id = voice or self.tts_voice

            # Use provided model or default
            model = kwargs.get('model', self.tts_model)

            # Build voice settings
            voice_settings = {
                "stability": kwargs.get('stability', self.tts_stability),
                "similarity_boost": kwargs.get('similarity_boost', self.tts_similarity_boost),
            }

            # Add style for v2 models
            if 'v2' in model.lower():
                voice_settings["style"] = kwargs.get('style', self.tts_style)
                voice_settings["use_speaker_boost"] = kwargs.get('use_speaker_boost', self.tts_use_speaker_boost)

            # Build request payload
            payload = {
                "text": text,
                "model_id": model,
                "voice_settings": voice_settings
            }

            # Determine output format
            output_format = format or self.tts_format

            # Make API request
            url = f"{self.api_base}/text-to-speech/{voice_id}"

            # Add output format as query parameter
            params = {
                "output_format": output_format
            }

            async with self._session.post(url, json=payload, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"ElevenLabs API error ({response.status}): {error_text}")

                audio_data = await response.read()
                return audio_data

        except Exception as e:
            logger.error(f"ElevenLabs TTS error: {str(e)}")
            raise

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Speech-to-text is not supported by ElevenLabs.

        ElevenLabs is a text-to-speech service and does not provide STT capabilities.
        """
        raise NotImplementedError(
            "ElevenLabs doesn't support speech-to-text. "
            "ElevenLabs is a text-to-speech (TTS) service only. "
            "Use OpenAI, Google, or Ollama for speech-to-text functionality."
        )

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Transcription is not supported by ElevenLabs.

        ElevenLabs is a text-to-speech service and does not provide transcription.
        """
        raise NotImplementedError(
            "ElevenLabs doesn't support audio transcription. "
            "ElevenLabs is a text-to-speech (TTS) service only. "
            "Use OpenAI, Google, or Ollama for transcription."
        )

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """
        Audio translation is not supported by ElevenLabs.

        ElevenLabs is a text-to-speech service and does not provide translation.
        """
        raise NotImplementedError(
            "ElevenLabs doesn't support audio translation. "
            "ElevenLabs is a text-to-speech (TTS) service only. "
            "Use OpenAI or Google for audio translation."
        )

    async def verify_connection(self) -> bool:
        """
        Verify connection to ElevenLabs API.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            if not self.initialized:
                await self.initialize()

            # Make a simple API call to verify connection
            url = f"{self.api_base}/voices"

            async with self._session.get(url) as response:
                return response.status == 200

        except Exception as e:
            logger.error(f"ElevenLabs connection verification failed: {str(e)}")
            return False

    async def list_voices(self) -> Dict[str, Any]:
        """
        List available voices from ElevenLabs.

        Returns:
            Dictionary containing available voices
        """
        if not self.initialized:
            await self.initialize()

        try:
            url = f"{self.api_base}/voices"

            async with self._session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Failed to list voices ({response.status}): {error_text}")

                return await response.json()

        except Exception as e:
            logger.error(f"Failed to list ElevenLabs voices: {str(e)}")
            raise

    async def get_voice_info(self, voice_id: str) -> Dict[str, Any]:
        """
        Get information about a specific voice.

        Args:
            voice_id: The ID of the voice

        Returns:
            Dictionary containing voice information
        """
        if not self.initialized:
            await self.initialize()

        try:
            url = f"{self.api_base}/voices/{voice_id}"

            async with self._session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Failed to get voice info ({response.status}): {error_text}")

                return await response.json()

        except Exception as e:
            logger.error(f"Failed to get ElevenLabs voice info: {str(e)}")
            raise
