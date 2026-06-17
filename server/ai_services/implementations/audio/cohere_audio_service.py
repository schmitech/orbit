"""
Cohere audio service implementation.

Provides speech-to-text via Cohere's v2 transcription API.
Endpoint: POST https://api.cohere.com/v2/audio/transcriptions
Supported formats: FLAC, MP3, MPEG, MPGA, OGG, WAV (≤25 MB)
"""

import os
from io import BytesIO
from typing import Any, Dict, Optional, Union

import httpx

from ...connection import RetryHandler
from ...errors import raise_sanitized
from ...services import AudioService


class CohereAudioService(AudioService):
    """Cohere audio service for speech-to-text transcription."""

    DEFAULT_API_BASE = "https://api.cohere.com/v2"
    DEFAULT_STT_ENDPOINT = "/audio/transcriptions"
    DEFAULT_STT_MODEL = "cohere-transcribe-03-2026"

    MIME_TYPES = {
        "flac": "audio/flac",
        "mp3": "audio/mpeg",
        "mpeg": "audio/mpeg",
        "mpga": "audio/mpeg",
        "ogg": "audio/ogg",
        "wav": "audio/wav",
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "cohere")

        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("COHERE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Cohere API key is required. Set COHERE_API_KEY environment variable "
                "or provide it in stt_providers.cohere.api_key."
            )

        self.base_url = (
            provider_config.get("api_base")
            or provider_config.get("base_url")
            or self.DEFAULT_API_BASE
        )
        self.stt_model = provider_config.get("stt_model") or self.DEFAULT_STT_MODEL
        self.model = self.stt_model
        self.language = provider_config.get("language")

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

        self.client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> bool:
        if self.initialized:
            return True
        try:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            self.initialized = True
            self.logger.info("Initialized Cohere audio service (STT)")
            return True
        except Exception as e:
            self.logger.error("Failed to initialize Cohere audio service: %s", e)
            return False

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.api_key or len(self.api_key) < 10:
            self.logger.error("Invalid Cohere API key")
            return False
        return True

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs,
    ) -> str:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Cohere audio service")

        audio_data, filename, mime_type = self._prepare_file(audio, kwargs)
        lang = language or kwargs.pop("language", None) or self.language

        async def _transcribe() -> str:
            # Cohere requires text fields to appear before the file part in the
            # multipart body. Use an ordered list through the `files` kwarg so
            # httpx serialises them in insertion order.
            multipart: list = [
                ("model", (None, self.stt_model)),
            ]
            if lang:
                multipart.append(("language", (None, lang)))
            multipart.append(("file", (filename, BytesIO(audio_data), mime_type)))
            response = await self.client.post(
                self.DEFAULT_STT_ENDPOINT, files=multipart
            )
            if not response.is_success:
                try:
                    body = response.json()
                except Exception:
                    body = response.text
                self.logger.error(
                    "Cohere STT %s response body: %s", response.status_code, body
                )
            response.raise_for_status()
            return response.json().get("text", "")

        try:
            return await self.retry_handler.execute_with_retry(
                _transcribe,
                error_message="Cohere speech-to-text failed",
            )
        except Exception as e:
            self.logger.error("Cohere speech-to-text failed: %s", e)
            raise_sanitized(e, provider="cohere", operation="speech-to-text")

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs,
    ) -> str:
        return await self.speech_to_text(audio, language, **kwargs)

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        raise NotImplementedError(
            "Cohere does not support text-to-speech. Use another provider for TTS."
        )

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs,
    ) -> str:
        raise NotImplementedError(
            "Cohere audio transcription does not support translation. "
            "Use another provider for audio translation."
        )

    def _prepare_file(
        self,
        audio: Union[str, bytes],
        kwargs: Dict[str, Any],
    ):
        """Return (audio_bytes, filename, mime_type)."""
        filename = kwargs.pop("filename", None)
        mime_type = kwargs.pop("mime_type", None)

        audio_data = self._prepare_audio(audio)

        if isinstance(audio, str):
            filename = filename or os.path.basename(audio)

        ext = None
        if filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()

        if not ext:
            ext = self._detect_format(audio_data) or "wav"

        filename = filename or f"audio.{ext}"
        mime_type = mime_type or self.MIME_TYPES.get(ext, "application/octet-stream")
        return audio_data, filename, mime_type

    def _detect_format(self, data: bytes) -> Optional[str]:
        if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return "wav"
        if len(data) > 3 and (
            data[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
        ):
            return "mp3"
        if len(data) > 4 and data[:4] == b"fLaC":
            return "flac"
        if len(data) > 4 and data[:4] == b"OggS":
            return "ogg"
        return None
