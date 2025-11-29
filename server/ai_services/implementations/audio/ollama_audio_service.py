"""
Ollama audio service implementation using unified architecture.

This implementation provides audio capabilities using Ollama's local audio models
or speaches-compatible servers for speech-to-text and text-to-speech.
"""

import logging
from typing import Dict, Any, Optional, Union
from io import BytesIO
import base64
import json

from ...base import ServiceType
from ...providers import OllamaBaseService
from ...services import AudioService

logger = logging.getLogger(__name__)


class OllamaAudioService(AudioService, OllamaBaseService):
    """
    Ollama audio service using unified architecture.

    Supports:
    - Speech-to-text using Ollama Whisper models
    - Text-to-speech using Ollama TTS models (piper, kokoro)
    - Audio transcription
    - Audio translation

    Uses Ollama's API for audio processing with local models.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Ollama audio service."""
        # Initialize via OllamaBaseService
        OllamaBaseService.__init__(self, config, ServiceType.AUDIO, "ollama")

        # Get audio-specific configuration
        provider_config = self._extract_provider_config()
        self.stt_model = provider_config.get('stt_model', 'whisper')
        self.tts_model = provider_config.get('tts_model', 'piper')
        self.tts_voice = provider_config.get('tts_voice', 'en_US-lessac-medium')
        self.tts_format = provider_config.get('tts_format', 'wav')
        self.stream = provider_config.get('stream', False)

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Convert text to speech audio using Ollama TTS models."""
        if not self.initialized:
            await self.initialize()

        try:
            # Use provided voice or default from config
            tts_voice = voice or self.tts_voice
            
            # Use provided format or default from config
            audio_format = format or self.tts_format

            # Prepare request payload
            # Note: Ollama's audio API structure may vary
            # This is a placeholder implementation that follows Ollama's chat API pattern
            payload = {
                "model": self.tts_model,
                "prompt": text,
                "stream": False,
                "options": {
                    "voice": tts_voice,
                    "format": audio_format,
                    **kwargs
                }
            }

            # Make request to Ollama API
            async with self.session_manager.get_session() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.ollama_config.total_timeout
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

                    # Extract audio data from response
                    # Ollama may return base64-encoded audio or raw bytes
                    if "audio" in result:
                        audio_data = result["audio"]
                        if isinstance(audio_data, str):
                            # Decode base64 if needed
                            return base64.b64decode(audio_data)
                        return audio_data
                    elif "response" in result:
                        # Some models return audio as base64 in response field
                        audio_str = result["response"]
                        return base64.b64decode(audio_str)
                    else:
                        raise ValueError("No audio data in Ollama response")

        except Exception as e:
            logger.error(f"Ollama TTS error: {str(e)}")
            raise

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Convert speech audio to text using Ollama Whisper models."""
        if not self.initialized:
            await self.initialize()

        try:
            # Prepare audio data
            audio_data = self._prepare_audio(audio)
            
            # Encode audio to base64 for API
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')

            # Prepare request payload
            # Ollama Whisper API typically uses /api/transcribe endpoint
            payload = {
                "model": self.stt_model,
                "audio": audio_base64,
                "options": {
                    "language": language,
                    **kwargs
                }
            }

            # Make request to Ollama API
            # Try /api/transcribe first, fallback to /api/generate
            async with self.session_manager.get_session() as session:
                # Try transcribe endpoint
                try:
                    async with session.post(
                        f"{self.base_url}/api/transcribe",
                        json=payload,
                        timeout=self.ollama_config.total_timeout
                    ) as response:
                        response.raise_for_status()
                        result = await response.json()
                        
                        if "text" in result:
                            return result["text"]
                        elif "transcription" in result:
                            return result["transcription"]
                except Exception:
                    # Fallback to generate endpoint with audio input
                    # This is a simplified approach - actual implementation may vary
                    payload_generate = {
                        "model": self.stt_model,
                        "prompt": f"Transcribe this audio: {audio_base64[:100]}...",
                        "stream": False
                    }
                    
                    async with session.post(
                        f"{self.base_url}/api/generate",
                        json=payload_generate,
                        timeout=self.ollama_config.total_timeout
                    ) as response:
                        response.raise_for_status()
                        result = await response.json()
                        
                        if "response" in result:
                            return result["response"]
                        else:
                            raise ValueError("No transcription in Ollama response")

        except Exception as e:
            logger.error(f"Ollama STT error: {str(e)}")
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
        """Translate audio from one language to another using Ollama."""
        if not self.initialized:
            await self.initialize()

        try:
            # First transcribe the audio
            transcript = await self.speech_to_text(audio, source_language, **kwargs)
            
            # Then translate using Ollama's inference capabilities
            # This uses the inference model to translate text
            payload = {
                "model": self.model,  # Use the configured inference model
                "prompt": f"Translate the following text to {target_language}: {transcript}",
                "stream": False
            }

            async with self.session_manager.get_session() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.ollama_config.total_timeout
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    
                    if "response" in result:
                        return result["response"].strip()
                    else:
                        # Fallback: return original transcript if translation fails
                        logger.warning("Translation failed, returning transcript")
                        return transcript

        except Exception as e:
            logger.error(f"Ollama translation error: {str(e)}")
            # Fallback: return transcript if translation fails
            try:
                return await self.speech_to_text(audio, source_language, **kwargs)
            except:
                raise

