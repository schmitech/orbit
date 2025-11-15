"""
OpenAI audio service implementation using unified architecture.

This implementation provides audio capabilities using OpenAI's Whisper API
for speech-to-text and TTS-1 API for text-to-speech.
"""

from typing import Dict, Any, Optional, Union
from io import BytesIO

from ..base import ServiceType
from ..providers import OpenAIBaseService
from ..services import AudioService


class OpenAIAudioService(AudioService, OpenAIBaseService):
    """
    OpenAI audio service using unified architecture.

    Supports:
    - Speech-to-text using Whisper API
    - Text-to-speech using TTS-1 API
    - Audio transcription
    - Audio translation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the OpenAI audio service."""
        # Initialize via OpenAIBaseService first
        OpenAIBaseService.__init__(self, config, ServiceType.AUDIO, "openai")
        
        # Get audio-specific configuration
        provider_config = self._extract_provider_config()
        self.stt_model = provider_config.get('stt_model', 'whisper-1')
        self.tts_model = provider_config.get('tts_model', 'tts-1')
        self.tts_voice = provider_config.get('tts_voice', 'alloy')
        self.tts_format = provider_config.get('tts_format', 'mp3')

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Convert text to speech audio using OpenAI TTS-1."""
        if not self.initialized:
            await self.initialize()

        try:
            # Use provided voice or default from config
            tts_voice = voice or self.tts_voice
            
            # Use provided format or default from config
            tts_format = format or self.tts_format
            
            # Validate format
            if not self._validate_audio_format(tts_format):
                raise ValueError(f"Unsupported audio format: {tts_format}")

            # Call OpenAI TTS API
            response = await self.client.audio.speech.create(
                model=self.tts_model,
                voice=tts_voice,
                input=text,
                response_format=tts_format,
                **kwargs
            )

            # Read audio data from HttpxBinaryResponseContent
            # The response object has a .read() method or .content attribute
            if hasattr(response, 'read'):
                # Async read method
                audio_data = await response.aread() if hasattr(response, 'aread') else response.read()
            elif hasattr(response, 'content'):
                # Direct content access
                audio_data = response.content
            elif hasattr(response, 'iter_bytes'):
                # Sync iterator
                audio_data = b"".join(response.iter_bytes())
            else:
                # Fallback: try to convert to bytes
                audio_data = bytes(response)

            return audio_data

        except Exception as e:
            self._handle_openai_error(e, "text-to-speech")
            raise

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Convert speech audio to text using OpenAI Whisper."""
        if not self.initialized:
            await self.initialize()

        try:
            # Prepare audio data
            audio_data = self._prepare_audio(audio)
            
            # Get audio format
            audio_format = self._get_audio_format(audio) if isinstance(audio, str) else 'mp3'

            # Create file-like object for OpenAI API
            audio_file = BytesIO(audio_data)
            audio_file.name = f"audio.{audio_format}"

            # Call OpenAI Whisper API
            transcript = await self.client.audio.transcriptions.create(
                model=self.stt_model,
                file=audio_file,
                language=language,
                **kwargs
            )

            return transcript.text

        except Exception as e:
            self._handle_openai_error(e, "speech-to-text")
            raise

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Transcribe audio to text (alias for speech_to_text)."""
        return await self.speech_to_text(audio, language, **kwargs)

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """Translate audio from one language to another using OpenAI Whisper."""
        if not self.initialized:
            await self.initialize()

        try:
            # Prepare audio data
            audio_data = self._prepare_audio(audio)
            
            # Get audio format
            audio_format = self._get_audio_format(audio) if isinstance(audio, str) else 'mp3'

            # Create file-like object for OpenAI API
            audio_file = BytesIO(audio_data)
            audio_file.name = f"audio.{audio_format}"

            # OpenAI Whisper translation API translates to English by default
            # If target_language is not English, we'll need to transcribe first then translate
            if target_language.lower() in ['en', 'english']:
                # Use translation API directly
                translation = await self.client.audio.translations.create(
                    model=self.stt_model,
                    file=audio_file,
                    **kwargs
                )
                return translation.text
            else:
                # Transcribe first, then use text translation (would need inference service)
                # For now, we'll transcribe and return the text
                # In a full implementation, you'd call an inference service for translation
                transcript = await self.speech_to_text(audio, source_language, **kwargs)
                # Note: Text translation would require an inference service
                # This is a limitation of OpenAI's audio API
                return transcript

        except Exception as e:
            self._handle_openai_error(e, "audio translation")
            raise

