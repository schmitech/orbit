"""
Gemini audio service implementation using unified architecture.

This implementation provides audio capabilities using Google's Gemini API
with native multimodal support for both audio input (STT) and audio output (TTS).

Gemini 2.5+ models support native audio generation and understanding, similar
to OpenAI's GPT-4o multimodal capabilities.

Requirements:
    pip install google-genai

Note: This requires the 'google-genai' package, which is separate from
'google-generativeai'. The google-genai package provides access to Gemini's
native audio generation capabilities.
"""

from typing import Dict, Any, Optional, Union
import asyncio
import base64
import wave
from io import BytesIO

from ..base import ServiceType
from ..providers import GoogleBaseService
from ..services import AudioService


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
        # Add more mappings as needed
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
        # Initialize via GoogleBaseService first
        GoogleBaseService.__init__(self, config, ServiceType.AUDIO, "gemini")

        # Get audio-specific configuration
        provider_config = self._extract_provider_config()
        # Use gemini-2.5-flash-preview-tts for TTS (required for audio generation)
        self.stt_model = provider_config.get('stt_model', 'gemini-2.0-flash-exp')
        self.tts_model = provider_config.get('tts_model', 'gemini-2.5-flash-preview-tts')
        self.tts_voice = provider_config.get('tts_voice', 'Puck')
        self.tts_format = provider_config.get('tts_format', 'wav')
        self.transport = provider_config.get('transport', 'rest')

        # Client will be initialized lazily
        self._genai_client = None

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._genai_client is None:
            try:
                from google import genai
                import os

                # Get API key
                api_key = self._resolve_api_key("GOOGLE_API_KEY")
                if api_key:
                    os.environ["GOOGLE_API_KEY"] = api_key

                self._genai_client = genai.Client()
            except ImportError:
                raise ImportError(
                    "google-genai package is required for Gemini audio generation. "
                    "Install it with: pip install google-genai"
                )
        return self._genai_client

    def _wrap_in_wav(self, pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
        """
        Wrap raw PCM bytes in WAV format.

        Gemini returns raw 16-bit PCM audio at 24kHz sample rate.
        This method wraps it in a proper WAV container for browser compatibility.

        Args:
            pcm_bytes: Raw 16-bit PCM audio data
            sample_rate: Sample rate in Hz (default: 24000 for Gemini)

        Returns:
            WAV file as bytes
        """
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
        """
        Normalize and map voice names to valid Gemini voices.

        This method:
        1. Maps OpenAI voice names to similar Gemini voices
        2. Validates that the voice name is supported by Gemini
        3. Returns the properly capitalized voice name

        Args:
            voice: Voice name (can be OpenAI or Gemini voice)

        Returns:
            Valid Gemini voice name with proper capitalization

        Raises:
            ValueError: If voice is not supported
        """
        if not voice:
            return self.tts_voice

        # Convert to lowercase for case-insensitive comparison
        voice_lower = voice.lower()

        # Check if it's an OpenAI voice that needs mapping
        if voice_lower in self.VOICE_MAPPING:
            mapped_voice = self.VOICE_MAPPING[voice_lower]
            self.logger.info(
                f"Mapped OpenAI voice '{voice}' to Gemini voice '{mapped_voice}'"
            )
            return mapped_voice

        # Check if it's a valid Gemini voice
        if voice_lower in self.VALID_VOICES:
            # Return with proper capitalization (first letter uppercase)
            return voice_lower.capitalize()

        # Voice not recognized - log warning and use default
        self.logger.warning(
            f"Voice '{voice}' not recognized. Using default voice '{self.tts_voice}'. "
            f"Valid Gemini voices: {', '.join(sorted(self.VALID_VOICES))}"
        )
        return self.tts_voice

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
            from google import genai
            from google.genai import types

            # Get client
            client = self._get_client()

            # Normalize and map voice name
            tts_voice = self._normalize_voice_name(voice or self.tts_voice)

            # Use provided format or default from config
            audio_format = format or self.tts_format

            # Validate format
            if not self._validate_audio_format(audio_format):
                raise ValueError(f"Unsupported audio format: {audio_format}")

            # Create generation config with audio output
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

            # Generate audio - use asyncio.to_thread since the SDK is synchronous
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.tts_model,
                contents=text,
                config=config
            )

            # Extract audio data from response
            if not hasattr(response, 'candidates') or not response.candidates:
                self.logger.error("No candidates returned from Gemini")
                raise ValueError("No candidates returned from Gemini")

            candidate = response.candidates[0]

            # Check if response has audio content
            if not hasattr(candidate, 'content') or not candidate.content:
                self.logger.error("No content in candidate response")
                raise ValueError("No content in response")

            if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
                self.logger.error("No content parts in response")
                raise ValueError("No content parts in response")

            # Extract audio from the response parts
            audio_data = None
            for part in candidate.content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    # Audio is returned as inline data (raw PCM)
                    audio_data = part.inline_data.data
                    self.logger.debug(f"Successfully extracted audio data: {len(audio_data)} bytes (raw PCM)")
                    break

            if audio_data is None:
                self.logger.error("No audio content found in response parts")
                raise ValueError("No audio content in response")

            # Gemini returns raw 16-bit PCM audio at 24kHz
            # Wrap it in WAV format for browser compatibility
            if audio_format.lower() in ['wav', 'wave']:
                wav_audio = self._wrap_in_wav(audio_data, sample_rate=24000)
                self.logger.debug(f"Wrapped PCM in WAV format: {len(wav_audio)} bytes")
                return wav_audio
            else:
                # Return raw PCM for other formats
                # Note: Browser may not support raw PCM directly
                self.logger.warning(f"Returning raw PCM audio (format: {audio_format}). Browser may not support this.")
                return audio_data

        except ImportError as e:
            self.logger.error(
                "google-genai package is required for Gemini audio generation. "
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
            import google.generativeai as genai

            # Configure API
            api_key = kwargs.pop('api_key', None) or self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key, transport=self.transport)

            # Prepare audio data
            audio_data = self._prepare_audio(audio)

            # Get audio format (MIME type)
            audio_format = self._get_audio_format(audio) if isinstance(audio, str) else 'wav'
            mime_type = f"audio/{audio_format}"

            # Initialize model
            model = genai.GenerativeModel(self.stt_model)

            # Create prompt for transcription
            prompt_text = "Please transcribe this audio to text."
            if language:
                prompt_text = f"Please transcribe this audio to text in {language}."

            # Upload audio file
            # Gemini expects audio as Part with inline_data
            audio_part = {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(audio_data).decode('utf-8')
                }
            }

            # Generate content with audio input
            if self.transport == 'rest':
                response = await asyncio.to_thread(
                    model.generate_content,
                    [audio_part, prompt_text]
                )
            else:
                response = await model.generate_content_async(
                    [audio_part, prompt_text]
                )

            # Extract transcription from response
            if not response.candidates:
                raise ValueError("No candidates returned from Gemini")

            candidate = response.candidates[0]

            # Check finish reason
            if candidate.finish_reason == 2:  # SAFETY
                raise ValueError("Response blocked due to safety concerns")
            elif candidate.finish_reason == 3:  # RECITATION
                raise ValueError("Response blocked due to recitation concerns")
            elif candidate.finish_reason == 4:  # OTHER
                raise ValueError("Response blocked for other reasons")

            # Check if response has text content
            if not candidate.content or not candidate.content.parts:
                raise ValueError("No content parts in response")

            # Extract text from the first part
            first_part = candidate.content.parts[0]
            if not hasattr(first_part, 'text') or not first_part.text:
                raise ValueError("No text content in response part")

            return first_part.text

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
            import google.generativeai as genai

            # Configure API
            api_key = kwargs.pop('api_key', None) or self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key, transport=self.transport)

            # Prepare audio data
            audio_data = self._prepare_audio(audio)

            # Get audio format (MIME type)
            audio_format = self._get_audio_format(audio) if isinstance(audio, str) else 'wav'
            mime_type = f"audio/{audio_format}"

            # Initialize model
            model = genai.GenerativeModel(self.stt_model)

            # Create prompt for translation
            if source_language:
                prompt_text = f"Please transcribe this audio from {source_language} and translate it to {target_language}."
            else:
                prompt_text = f"Please transcribe this audio and translate it to {target_language}."

            # Upload audio file
            audio_part = {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(audio_data).decode('utf-8')
                }
            }

            # Generate content with audio input
            if self.transport == 'rest':
                response = await asyncio.to_thread(
                    model.generate_content,
                    [audio_part, prompt_text]
                )
            else:
                response = await model.generate_content_async(
                    [audio_part, prompt_text]
                )

            # Extract translation from response
            if not response.candidates:
                raise ValueError("No candidates returned from Gemini")

            candidate = response.candidates[0]

            # Check finish reason
            if candidate.finish_reason == 2:  # SAFETY
                raise ValueError("Response blocked due to safety concerns")
            elif candidate.finish_reason == 3:  # RECITATION
                raise ValueError("Response blocked due to recitation concerns")
            elif candidate.finish_reason == 4:  # OTHER
                raise ValueError("Response blocked for other reasons")

            # Check if response has text content
            if not candidate.content or not candidate.content.parts:
                raise ValueError("No content parts in response")

            # Extract text from the first part
            first_part = candidate.content.parts[0]
            if not hasattr(first_part, 'text') or not first_part.text:
                raise ValueError("No text content in response part")

            return first_part.text

        except Exception as e:
            self._handle_google_error(e, "audio translation")
            raise
