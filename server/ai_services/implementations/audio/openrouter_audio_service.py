"""
OpenRouter audio service implementation using the native OpenRouter SDK.

Provides both speech-to-text and text-to-speech via OpenRouter's
transcription and speech endpoints.

API Documentation:
    https://openrouter.ai/docs/api/api-reference/stt/create-transcription
    https://openrouter.ai/docs/api/api-reference/tts/create-speech
"""

import base64
import os
from typing import Any, Dict, Optional, Union

from openrouter import OpenRouter
from openrouter.components.sttinputaudio import STTInputAudio
from openrouter.utils.retries import BackoffStrategy, RetryConfig

from ...connection import RetryHandler
from ...errors import raise_sanitized
from ...providers.usage_reporting import UsageReportingMixin
from ...services import AudioService

# RetryHandler already governs retries/backoff; disable the SDK's own retry
# loop so a single execute_with_retry attempt maps to a single HTTP request.
_NO_SDK_RETRIES = RetryConfig(
    strategy="none",
    backoff=BackoffStrategy(initial_interval=1, max_interval=1, exponent=1.0, max_elapsed_time=1),
    retry_connection_errors=False,
)

# SDK request kwargs beyond input_audio/model/language/response_format that
# create_transcription_async accepts and should be forwarded when callers
# supply them, rather than silently dropped.
_FORWARDED_REQUEST_OPTIONS = ("provider", "temperature", "timestamp_granularities")

_MIME_TYPE_FORMATS = {
    "audio/wav": "wav",
    "audio/wave": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
    "audio/aac": "aac",
    "audio/x-aac": "aac",
}

_SPEECH_FORMATS = {"mp3", "pcm"}


class OpenRouterAudioService(UsageReportingMixin, AudioService):
    """OpenRouter audio service for speech-to-text and text-to-speech."""

    DEFAULT_STT_MODEL = "openai/whisper-large-v3"
    DEFAULT_TTS_MODEL = "mistralai/voxtral-mini-tts-2603"
    DEFAULT_TTS_FORMAT = "mp3"

    SUPPORTED_FORMATS = {"wav", "mp3", "flac", "m4a", "ogg", "webm", "aac"}

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "openrouter")

        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. Set OPENROUTER_API_KEY environment variable "
                "or provide it in stt_providers.openrouter.api_key."
            )

        self.stt_model = provider_config.get("stt_model") or self.DEFAULT_STT_MODEL
        self.model = self.stt_model
        self.language = provider_config.get("language")
        self.response_format = provider_config.get("response_format")

        self.tts_model = provider_config.get("tts_model") or self.DEFAULT_TTS_MODEL
        self.tts_voice = provider_config.get("tts_voice")
        self.tts_format = provider_config.get("tts_format") or self.DEFAULT_TTS_FORMAT
        self.tts_speed = provider_config.get("tts_speed")

        timeout_config = self._get_timeout_config()
        self._timeout_ms = timeout_config["total"]

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config["max_retries"],
            initial_wait_ms=retry_config["initial_wait_ms"],
            max_wait_ms=retry_config["max_wait_ms"],
            exponential_base=retry_config["exponential_base"],
            enabled=retry_config["enabled"],
        )
        self.client: Optional[OpenRouter] = None

    async def initialize(self) -> bool:
        if self.initialized:
            return True

        try:
            self.client = OpenRouter(
                api_key=self.api_key,
                timeout_ms=self._timeout_ms,
                retry_config=_NO_SDK_RETRIES,
            )
            self.initialized = True
            self.logger.debug(f"Initialized OpenRouter audio service (STT) with model {self.stt_model}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenRouter audio service: {e}")
            return False

    async def close(self) -> None:
        if self.client is not None:
            async_client = self.client.sdk_configuration.async_client
            if async_client is not None and not self.client.sdk_configuration.async_client_supplied:
                await async_client.aclose()
            self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.api_key or len(self.api_key) < 10:
            self.logger.error("Invalid OpenRouter API key")
            return False
        return True

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        usage_sink: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize OpenRouter audio service")

        # Transport-only hints consumed here; never forwarded to the SDK call.
        audio_format = kwargs.pop("audio_format", None) or kwargs.pop("format", None)
        filename = kwargs.pop("filename", None)
        mime_type = kwargs.pop("mime_type", None)

        audio_data, audio_format = self._prepare_audio_format(audio, audio_format, filename, mime_type)
        lang = language or kwargs.pop("language", None) or self.language
        model = kwargs.pop("model", None) or self.stt_model
        response_format = kwargs.pop("response_format", None) or self.response_format

        params = {
            "input_audio": STTInputAudio(data=base64.b64encode(audio_data).decode(), format=audio_format),
            "model": model,
            "language": lang,
            "response_format": response_format,
        }
        for option in _FORWARDED_REQUEST_OPTIONS:
            if option in kwargs:
                params[option] = kwargs.pop(option)
        params = {k: v for k, v in params.items() if v is not None}

        async def _transcribe() -> str:
            response = await self.client.stt.create_transcription_async(**params)

            usage = getattr(response, "usage", None)
            seconds = getattr(usage, "seconds", None) if usage is not None else None
            if seconds is not None:
                self._report_media_usage(usage_sink, "audio_seconds", seconds)

            return response.text or ""

        try:
            return await self.retry_handler.execute_with_retry(
                _transcribe,
                error_message="OpenRouter speech-to-text failed",
            )
        except ValueError:
            raise
        except Exception as e:
            self.logger.error(f"OpenRouter speech-to-text failed: {e}")
            raise_sanitized(e, provider="openrouter", operation="speech-to-text")

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        usage_sink: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        return await self.speech_to_text(audio, language, usage_sink=usage_sink, **kwargs)

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize OpenRouter audio service")

        tts_format = (format or kwargs.pop("response_format", None) or self.tts_format).lower()
        if tts_format not in _SPEECH_FORMATS:
            raise ValueError(
                f"Unsupported OpenRouter TTS format '{tts_format}'. Supported formats: {sorted(_SPEECH_FORMATS)}."
            )

        model = kwargs.pop("model", None) or self.tts_model
        tts_voice = voice or kwargs.pop("voice", None) or self.tts_voice
        speed = kwargs.pop("speed", None) or self.tts_speed

        params = {
            "input": text,
            "model": model,
            "response_format": tts_format,
            "voice": tts_voice,
            "speed": speed,
        }
        if "provider" in kwargs:
            params["provider"] = kwargs.pop("provider")
        params = {k: v for k, v in params.items() if v is not None}

        async def _speak() -> bytes:
            response = await self.client.tts.create_speech_async(**params)
            return await response.aread()

        try:
            return await self.retry_handler.execute_with_retry(
                _speak,
                error_message="OpenRouter text-to-speech failed",
            )
        except ValueError:
            raise
        except Exception as e:
            self.logger.error(f"OpenRouter text-to-speech failed: {e}")
            raise_sanitized(e, provider="openrouter", operation="text-to-speech")

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs,
    ) -> str:
        raise NotImplementedError(
            "OpenRouter audio transcription does not support translation. "
            "Use another provider for audio translation."
        )

    def _prepare_audio_format(
        self,
        audio: Union[str, bytes],
        audio_format: Optional[str],
        filename: Optional[str],
        mime_type: Optional[str] = None,
    ) -> tuple:
        audio_data = self._prepare_audio(audio)

        if isinstance(audio, str):
            filename = filename or os.path.basename(audio)

        if not audio_format and filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
            if ext in self.SUPPORTED_FORMATS:
                audio_format = ext

        if not audio_format and mime_type:
            normalized_mime = mime_type.lower().split(";", 1)[0].strip()
            audio_format = _MIME_TYPE_FORMATS.get(normalized_mime)

        if not audio_format:
            audio_format = self._detect_format(audio_data)

        if not audio_format:
            raise ValueError(
                "Could not determine the audio format for OpenRouter speech-to-text. "
                "Pass a filename with a recognized extension, a recognized mime_type, "
                "or an explicit audio_format (wav, mp3, flac, m4a, ogg, webm, aac)."
            )

        return audio_data, audio_format.lower()

    def _detect_format(self, data: bytes) -> Optional[str]:
        if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return "wav"
        if len(data) > 3 and data[:3] == b"ID3":
            return "mp3"
        if len(data) > 1 and data[0] == 0xFF:
            # ADTS AAC sync (0xFFF, layer bits always 00) must be checked
            # before the broader MP3 frame-sync test below, since a raw ADTS
            # header (e.g. 0xFF 0xF1) also satisfies the MP3 mask.
            if (data[1] & 0xF6) == 0xF0:
                return "aac"
            if (data[1] & 0xE0) == 0xE0 and (data[1] & 0x06) != 0:
                return "mp3"
        if len(data) > 4 and data[:4] == b"fLaC":
            return "flac"
        if len(data) > 4 and data[:4] == b"OggS":
            return "ogg"
        if len(data) > 4 and data[:4] == b"\x1a\x45\xdf\xa3":
            return "webm"
        if len(data) > 8 and data[4:8] == b"ftyp":
            return "m4a"
        return None
