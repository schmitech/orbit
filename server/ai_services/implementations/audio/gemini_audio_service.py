"""
Gemini audio service implementation using unified architecture.

Uses the google-genai SDK for both audio input (STT) and audio output (TTS).

Gemini 2.5+ models support native audio generation and understanding, similar
to OpenAI's GPT-4o multimodal capabilities.

Requirements:
    pip install google-genai
"""

import logging
from typing import Dict, Any, Optional, Union
import asyncio
import wave
from io import BytesIO

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import AudioService

logger = logging.getLogger(__name__)


class GeminiAudioService(AudioService, GoogleBaseService):
    """
    Gemini audio service using unified architecture.

    Supports:
    - Speech-to-text using Gemini's native audio understanding
    - Text-to-speech using Gemini's native audio generation
    - Audio transcription
    - Audio translation

    Gemini is Google's latest multimodal AI model with:
    - Native audio input processing
    - Native audio output generation
    - 30 voice options (Puck, Charon, Kore, Fenrir, Aoede, Zephyr, Leda, and more)
    - Support for various audio formats
    """

    # Voice mapping from OpenAI-style names to Gemini voices
    # This provides automatic compatibility when OpenAI voice names are used
    VOICE_MAPPING = {
        # OpenAI voices → Similar Gemini voices
        'alloy': 'Puck',        # Neutral → Bright, upbeat
        'echo': 'Charon',       # Male → Deep, authoritative
        'fable': 'Kore',        # British → Warm, friendly
        'onyx': 'Fenrir',       # Deep male → Strong, confident
        'nova': 'Aoede',        # Energetic → Melodic, expressive
        'shimmer': 'Zephyr',    # Soft female → Light, airy
        'coral': 'Leda',        # Warm → Gentle, soothing
        'sage': 'Orus',         # Steady → Firm, steady
    }

    # All valid Gemini voice names (case-insensitive)
    VALID_VOICES = {
        'puck', 'charon', 'kore', 'fenrir', 'aoede', 'zephyr', 'leda', 'orus',
        'despina', 'enceladus', 'iapetus', 'umbriel',
        'achernar', 'achird', 'algenib', 'algieba', 'alnilam',
        'autonoe', 'callirrhoe', 'erinome', 'laomedeia',
        'gacrux', 'pulcherrima', 'rasalgethi', 'sadachbia', 'sadaltager',
        'schedar', 'sulafat', 'vindemiatrix', 'zubenelgenubi'
    }

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Gemini audio service."""
        GoogleBaseService.__init__(self, config, ServiceType.AUDIO, "gemini")

        provider_config = self._extract_provider_config()
        self.stt_model = provider_config.get('stt_model', 'gemini-2.0-flash-exp')
        self.tts_model = provider_config.get('tts_model', 'gemini-2.5-flash-preview-tts')
        self.tts_voice = provider_config.get('tts_voice', 'Puck')
        self.tts_format = provider_config.get('tts_format', 'wav')

        self._genai_client = None

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._genai_client is None:
            try:
                from google import genai
                import os

                api_key = self._resolve_api_key("GOOGLE_API_KEY")
                if api_key:
                    os.environ["GOOGLE_API_KEY"] = api_key

                self._genai_client = genai.Client()
            except ImportError:
                raise ImportError(
                    "google-genai package is required for Gemini audio. "
                    "Install it with: pip install google-genai"
                )
        return self._genai_client

    def _wrap_in_wav(self, pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
        """Wrap raw PCM bytes in WAV format."""
        num_channels = 1  # Mono
        sample_width = 2  # 16-bit = 2 bytes

        wav_buffer = BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        wav_buffer.seek(0)
        return wav_buffer.read()

    def _normalize_voice_name(self, voice: str) -> str:
        """Normalize and map voice names to valid Gemini voices."""
        if not voice:
            return self.tts_voice

        voice_lower = voice.lower()

        if voice_lower in self.VOICE_MAPPING:
            mapped_voice = self.VOICE_MAPPING[voice_lower]
            logger.info(f"Mapped OpenAI voice '{voice}' to Gemini voice '{mapped_voice}'")
            return mapped_voice

        if voice_lower in self.VALID_VOICES:
            return voice_lower.capitalize()

        logger.warning(
            f"Voice '{voice}' not recognized. Using default voice '{self.tts_voice}'. "
            f"Valid Gemini voices: {', '.join(sorted(self.VALID_VOICES))}"
        )
        return self.tts_voice

    def _extract_text(self, response) -> str:
        """Extract text from a Gemini response with error checking."""
        if not response.candidates:
            raise ValueError("No candidates returned from Gemini")

        candidate = response.candidates[0]

        finish_reason = getattr(candidate, 'finish_reason', None)
        if finish_reason == 2:  # SAFETY
            raise ValueError("Response blocked due to safety concerns")
        elif finish_reason == 3:  # RECITATION
            raise ValueError("Response blocked due to recitation concerns")
        elif finish_reason == 4:  # OTHER
            raise ValueError("Response blocked for other reasons")

        if not candidate.content or not candidate.content.parts:
            raise ValueError("No content parts in response")

        first_part = candidate.content.parts[0]
        if not hasattr(first_part, 'text') or not first_part.text:
            raise ValueError("No text content in response part")

        return first_part.text

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Convert text to speech audio using Gemini's native audio generation."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.genai import types

            client = self._get_client()
            tts_voice = self._normalize_voice_name(voice or self.tts_voice)
            audio_format = format or self.tts_format

            if not self._validate_audio_format(audio_format):
                raise ValueError(f"Unsupported audio format: {audio_format}")

            config = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=tts_voice
                        )
                    )
                ),
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.tts_model,
                contents=text,
                config=config
            )

            if not hasattr(response, 'candidates') or not response.candidates:
                raise ValueError("No candidates returned from Gemini")

            candidate = response.candidates[0]

            if not hasattr(candidate, 'content') or not candidate.content:
                raise ValueError("No content in response")

            if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
                raise ValueError("No content parts in response")

            audio_data = None
            for part in candidate.content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    audio_data = part.inline_data.data
                    logger.debug(f"Successfully extracted audio data: {len(audio_data)} bytes (raw PCM)")
                    break

            if audio_data is None:
                raise ValueError("No audio content in response")

            if audio_format.lower() in ['wav', 'wave']:
                wav_audio = self._wrap_in_wav(audio_data, sample_rate=24000)
                logger.debug(f"Wrapped PCM in WAV format: {len(wav_audio)} bytes")
                return wav_audio
            else:
                logger.warning(f"Returning raw PCM audio (format: {audio_format}). Browser may not support this.")
                return audio_data

        except ImportError:
            logger.error(
                "google-genai package is required for Gemini audio. "
                "Install it with: pip install google-genai"
            )
            raise
        except Exception as e:
            self._handle_google_error(e, "text-to-speech")
            raise

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Convert speech audio to text using Gemini's native audio understanding."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.genai import types

            client = self._get_client()

            # Prepare audio data
            audio_data = self._prepare_audio(audio)

            # Get audio format (MIME type)
            if isinstance(audio, str):
                audio_format = self._get_audio_format(audio)
            else:
                logger.debug(f"Wrapping raw PCM audio ({len(audio_data)} bytes) in WAV format for Gemini STT")
                audio_data = self._wrap_in_wav(audio_data, sample_rate=24000)
                audio_format = 'wav'

            mime_type = f"audio/{audio_format}"

            # Create prompt for transcription
            prompt_text = "Please transcribe this audio to text."
            if language:
                prompt_text = f"Please transcribe this audio to text in {language}."

            # Build audio part using typed API
            audio_part = types.Part.from_bytes(data=audio_data, mime_type=mime_type)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.stt_model,
                contents=[audio_part, prompt_text],
            )

            return self._extract_text(response)

        except Exception as e:
            self._handle_google_error(e, "speech-to-text")
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
        """Translate audio from one language to another using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.genai import types

            client = self._get_client()

            # Prepare audio data
            audio_data = self._prepare_audio(audio)
            audio_format = self._get_audio_format(audio) if isinstance(audio, str) else 'wav'
            mime_type = f"audio/{audio_format}"

            # Create prompt for translation
            if source_language:
                prompt_text = f"Please transcribe this audio from {source_language} and translate it to {target_language}."
            else:
                prompt_text = f"Please transcribe this audio and translate it to {target_language}."

            audio_part = types.Part.from_bytes(data=audio_data, mime_type=mime_type)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.stt_model,
                contents=[audio_part, prompt_text],
            )

            return self._extract_text(response)

        except Exception as e:
            self._handle_google_error(e, "audio translation")
            raise
