"""
xAI (Grok) audio service implementation.

Provides speech-to-text through xAI's multipart /stt endpoint. xAI does not
currently expose text-to-speech or audio translation through this service.
"""

import mimetypes
import os
import wave
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import httpx

from ...connection import RetryHandler
from ...errors import raise_sanitized
from ...services import AudioService


class XAIAudioService(AudioService):
    """xAI audio service for Grok speech-to-text."""

    DEFAULT_API_BASE = "https://api.x.ai/v1"
    DEFAULT_STT_ENDPOINT = "/stt"
    DEFAULT_STT_MODEL = "grok-stt"
    DEFAULT_RAW_SAMPLE_RATE = 24000

    RAW_AUDIO_FORMATS = {"pcm", "mulaw", "alaw"}
    SUPPORTED_LANGUAGE_CODES = {
        "ar", "cs", "da", "nl", "en", "fil", "fr", "de", "hi", "id",
        "it", "ja", "ko", "mk", "ms", "fa", "pl", "pt", "ro", "ru",
        "es", "sv", "th", "tr", "vi",
    }
    MIME_TYPES = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "opus": "audio/opus",
        "flac": "audio/flac",
        "aac": "audio/aac",
        "mp4": "audio/mp4",
        "m4a": "audio/mp4",
        "mkv": "video/x-matroska",
        "pcm": "application/octet-stream",
        "mulaw": "application/octet-stream",
        "alaw": "application/octet-stream",
    }

    def __init__(self, config: Dict[str, Any]):
        """Initialize the xAI audio service."""
        super().__init__(config, "xai")

        provider_config = self._extract_provider_config()
        self.api_key = self._resolve_api_key("XAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "xAI API key is required. Set XAI_API_KEY environment variable "
                "or provide it in stt_providers.xai.api_key."
            )

        self.base_url = (
            provider_config.get("api_base")
            or provider_config.get("base_url")
            or self.DEFAULT_API_BASE
        )
        self.endpoint = provider_config.get("endpoint", self.DEFAULT_STT_ENDPOINT)

        # The xAI STT endpoint does not require a model parameter. Keep this
        # label for cache keys, logs, and parity with other STT providers.
        self.stt_model = provider_config.get("stt_model", self.DEFAULT_STT_MODEL)
        self.model = self.stt_model

        self.language = provider_config.get("language")
        self.format_text = provider_config.get("format", False)
        self.multichannel = provider_config.get("multichannel", False)
        self.channels = provider_config.get("channels")
        self.diarize = provider_config.get("diarize", False)
        self.filler_words = provider_config.get("filler_words", False)
        self.keyterms = provider_config.get(
            "keyterms",
            provider_config.get("keyterm"),
        )
        self.audio_format = provider_config.get("audio_format")
        self.sample_rate = provider_config.get("sample_rate")

        timeout_config = self._get_timeout_config()
        self.timeout = httpx.Timeout(
            timeout_config["total"] / 1000,
            connect=timeout_config["connect"] / 1000,
        )

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config["max_retries"],
            initial_wait_ms=retry_config["initial_wait_ms"],
            max_wait_ms=retry_config["max_wait_ms"],
            exponential_base=retry_config["exponential_base"],
            enabled=retry_config["enabled"],
        )

    async def initialize(self) -> bool:
        """Initialize the HTTP client."""
        if self.initialized:
            return True

        try:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            self.initialized = True
            self.logger.debug("Initialized xAI audio service for speech-to-text")
            return True
        except Exception as e:
            self.logger.error("Failed to initialize xAI audio service: %s", e)
            return False

    async def close(self) -> None:
        """Close the xAI HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        """Verify the xAI API key against the models endpoint."""
        if not self.initialized:
            if not await self.initialize():
                return False

        try:
            response = await self.client.get("/models")
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error("xAI audio connection verification failed: %s", e)
            return False

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """xAI STT does not provide text-to-speech."""
        raise NotImplementedError(
            "xAI audio currently supports speech-to-text only. "
            "Use another audio provider for text-to-speech."
        )

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Convert speech audio to text using xAI Grok STT."""
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize xAI audio service")

        options = self._extract_stt_options(language, kwargs)
        files = self._build_multipart_parts(audio, options)

        async def _transcribe() -> str:
            response = await self.client.post(self.endpoint, files=files)
            response.raise_for_status()
            return self._extract_transcript(response.json())

        try:
            return await self.retry_handler.execute_with_retry(
                _transcribe,
                error_message="xAI speech-to-text failed",
            )
        except ValueError:
            raise
        except Exception as e:
            self.logger.error("xAI speech-to-text failed: %s", e)
            raise_sanitized(e, provider="xai", operation="speech-to-text")

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Transcribe audio to text."""
        return await self.speech_to_text(audio, language, **kwargs)

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """xAI STT does not provide audio translation."""
        raise NotImplementedError(
            "xAI audio currently supports transcription only. "
            "Use another audio provider for audio translation."
        )

    def _extract_stt_options(
        self,
        language: Optional[str],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract xAI STT options from call-time kwargs and defaults."""
        options = {
            "language": self._normalize_language_code(language or self.language),
            "format": self.format_text,
            "multichannel": self.multichannel,
            "channels": self.channels,
            "diarize": self.diarize,
            "keyterms": self.keyterms,
            "filler_words": self.filler_words,
            "audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "filename": None,
            "mime_type": None,
            "url": None,
            "extra_fields": {},
        }

        options["url"] = kwargs.pop("url", None)
        options["filename"] = kwargs.pop("filename", None)
        options["mime_type"] = kwargs.pop("mime_type", None)

        format_value = kwargs.pop("format_text", None)
        legacy_format_value = kwargs.pop("format", None)
        audio_format = kwargs.pop("audio_format", None)

        if format_value is not None:
            options["format"] = format_value
        elif isinstance(legacy_format_value, bool):
            options["format"] = legacy_format_value
        elif isinstance(legacy_format_value, str) and legacy_format_value.lower() in {"true", "false"}:
            options["format"] = legacy_format_value.lower() == "true"
        elif legacy_format_value and not audio_format:
            # Preserve compatibility with existing audio services where
            # format="wav" means the input audio format.
            audio_format = legacy_format_value

        if audio_format:
            options["audio_format"] = str(audio_format).lower()

        for field in (
            "sample_rate",
            "multichannel",
            "channels",
            "diarize",
            "keyterm",
            "keyterms",
            "filler_words",
        ):
            if field in kwargs:
                options[field] = kwargs.pop(field)

        if options.get("keyterm") is not None:
            options["keyterms"] = options.pop("keyterm")

        if self._as_bool(options["format"]) and not options["language"]:
            raise ValueError("xAI STT format=true requires a language code")

        options["extra_fields"] = kwargs
        return options

    def _build_multipart_parts(
        self,
        audio: Union[str, bytes],
        options: Dict[str, Any],
    ) -> List[Tuple[str, Any]]:
        """Build ordered multipart fields with file last, as required by xAI."""
        parts: List[Tuple[str, Any]] = []

        url = options.get("url")
        if isinstance(audio, str) and self._is_url(audio):
            url = audio

        if url:
            self._append_form_field(parts, "url", url)
        else:
            audio_data, filename, mime_type, raw_format = self._prepare_file_part(
                audio,
                filename=options.get("filename"),
                mime_type=options.get("mime_type"),
                audio_format=options.get("audio_format"),
                sample_rate=options.get("sample_rate"),
            )

            if raw_format:
                self._append_form_field(parts, "audio_format", raw_format)
                self._append_form_field(parts, "sample_rate", options.get("sample_rate"))

        self._append_form_field(parts, "language", options.get("language"))
        self._append_form_field(parts, "format", options.get("format"))
        self._append_form_field(parts, "multichannel", options.get("multichannel"))
        self._append_form_field(parts, "channels", options.get("channels"))
        self._append_form_field(parts, "diarize", options.get("diarize"))
        self._append_keyterms(parts, options.get("keyterms"))
        self._append_form_field(parts, "filler_words", options.get("filler_words"))

        for field, value in options.get("extra_fields", {}).items():
            self._append_form_field(parts, field, value)

        if not url:
            # xAI requires the file parameter after all other multipart fields.
            parts.append(("file", (filename, audio_data, mime_type)))

        return parts

    def _prepare_file_part(
        self,
        audio: Union[str, bytes],
        filename: Optional[str],
        mime_type: Optional[str],
        audio_format: Optional[str],
        sample_rate: Optional[int],
    ) -> Tuple[bytes, str, str, Optional[str]]:
        """Prepare an audio file part and raw audio metadata if needed."""
        audio_data = self._prepare_audio(audio)

        if isinstance(audio, str):
            filename = filename or os.path.basename(audio)

        audio_format = (audio_format or "").lower() or None
        if audio_format in self.RAW_AUDIO_FORMATS:
            if not sample_rate:
                raise ValueError(
                    "xAI STT raw audio requires sample_rate when "
                    "audio_format is pcm, mulaw, or alaw"
                )
            filename = filename or f"audio.{audio_format}"
            mime_type = mime_type or self.MIME_TYPES[audio_format]
            return audio_data, filename, mime_type, audio_format

        inferred_format = (
            audio_format
            or self._format_from_filename(filename)
            or self._format_from_mime_type(mime_type)
            or self._detect_audio_format(audio_data)
        )

        if not inferred_format:
            wrap_rate = sample_rate or self.DEFAULT_RAW_SAMPLE_RATE
            audio_data = self._wrap_in_wav(audio_data, sample_rate=wrap_rate)
            inferred_format = "wav"

        filename = filename or f"audio.{inferred_format}"
        mime_type = mime_type or self.MIME_TYPES.get(
            inferred_format,
            mimetypes.guess_type(filename)[0] or "application/octet-stream",
        )
        return audio_data, filename, mime_type, None

    def _extract_transcript(self, result: Dict[str, Any]) -> str:
        """Extract transcript text from an xAI STT response."""
        text = result.get("text")
        if isinstance(text, str):
            return text

        channels = result.get("channels")
        if isinstance(channels, list):
            channel_texts = [
                channel.get("text", "")
                for channel in channels
                if isinstance(channel, dict) and channel.get("text")
            ]
            if channel_texts:
                return "\n".join(channel_texts)

        return ""

    def _append_form_field(
        self,
        parts: List[Tuple[str, Any]],
        name: str,
        value: Any,
    ) -> None:
        """Append a multipart text field if a value is present."""
        if value is None:
            return

        if isinstance(value, bool):
            field_value = "true" if value else "false"
        else:
            field_value = str(value)

        parts.append((name, (None, field_value)))

    def _append_keyterms(self, parts: List[Tuple[str, Any]], keyterms: Any) -> None:
        """Append xAI keyterm fields, repeating the field for multiple terms."""
        if keyterms is None:
            return

        if isinstance(keyterms, str):
            terms = [keyterms]
        else:
            terms = list(keyterms)

        for term in terms:
            self._append_form_field(parts, "keyterm", term)

    def _normalize_language_code(self, language: Optional[str]) -> Optional[str]:
        """Normalize locale-style language values to xAI language codes."""
        if not language:
            return None

        language_code = str(language).lower()
        if language_code in self.SUPPORTED_LANGUAGE_CODES:
            return language_code

        base_code = language_code.replace("_", "-").split("-", 1)[0]
        if base_code in self.SUPPORTED_LANGUAGE_CODES:
            return base_code

        return language

    def _is_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return bool(value)

    def _format_from_filename(self, filename: Optional[str]) -> Optional[str]:
        if not filename or "." not in filename:
            return None

        extension = filename.rsplit(".", 1)[-1].lower()
        if extension in self.MIME_TYPES:
            return extension
        return None

    def _format_from_mime_type(self, mime_type: Optional[str]) -> Optional[str]:
        if not mime_type:
            return None

        normalized = mime_type.lower().split(";", 1)[0].strip()
        mime_map = {
            "audio/wav": "wav",
            "audio/wave": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/ogg": "ogg",
            "audio/opus": "opus",
            "audio/flac": "flac",
            "audio/aac": "aac",
            "audio/mp4": "m4a",
            "video/mp4": "mp4",
            "audio/x-m4a": "m4a",
            "video/x-matroska": "mkv",
            "audio/x-matroska": "mkv",
        }
        return mime_map.get(normalized)

    def _detect_audio_format(self, audio_data: bytes) -> Optional[str]:
        if len(audio_data) > 12 and audio_data[:4] == b"RIFF" and audio_data[8:12] == b"WAVE":
            return "wav"
        if len(audio_data) > 3 and (
            audio_data[:3] == b"ID3"
            or (audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0)
        ):
            return "mp3"
        if len(audio_data) > 4 and audio_data[:4] == b"fLaC":
            return "flac"
        if len(audio_data) > 4 and audio_data[:4] == b"OggS":
            return "ogg"
        if len(audio_data) > 4 and audio_data[:4] == b"\x1a\x45\xdf\xa3":
            return "mkv"
        if len(audio_data) > 8 and audio_data[4:8] == b"ftyp":
            brand = audio_data[8:12].lower()
            if brand in {b"m4a ", b"m4b ", b"m4p "}:
                return "m4a"
            return "mp4"
        return None

    def _wrap_in_wav(self, pcm_bytes: bytes, sample_rate: int) -> bytes:
        """Wrap raw 16-bit mono PCM bytes in a WAV container."""
        wav_buffer = BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        wav_buffer.seek(0)
        return wav_buffer.read()
