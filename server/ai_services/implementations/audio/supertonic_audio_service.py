"""
Supertonic TTS audio service implementation.

Supertonic (https://github.com/supertone-inc/supertonic) is a local, high-quality
neural TTS engine with 31-language support, expressive voice styles, and built-in
text chunking. Runs entirely offline using a local model directory.

Model setup:
    hf download Supertone/supertonic-3 --local-dir ./models/supertonic-3

This service provides TTS-only functionality (no STT).

Requires: pip install supertonic
"""

from typing import Dict, Any, Optional, Union
from io import BytesIO
import asyncio
import logging
import os
import wave

from ...services import AudioService
from ...connection import ConnectionManager, RetryHandler

logger = logging.getLogger(__name__)

try:
    from supertonic import TTS as SupertonicTTS
    SUPERTONIC_AVAILABLE = True
except ImportError:
    SUPERTONIC_AVAILABLE = False
    SupertonicTTS = None

# Global model cache — loading takes a few seconds; reuse across requests.
_global_tts_model = None
_global_tts_model_dir = None

SAMPLE_RATE = 44100  # Supertonic always outputs 44.1 kHz
DEFAULT_MODEL_NAME = "supertonic"  # Reported when no local model_dir is configured (auto-download)


class SupertonicAudioService(AudioService):
    """
    Supertonic TTS audio service using unified architecture.

    Supports:
    - Text-to-speech using a locally downloaded Supertonic model
    - 31 languages
    - 10 preset voice styles (M1–M5, F1–F5) plus custom JSON voice profiles
    - Adjustable speed and quality steps

    Does NOT support:
    - Speech-to-text (use WhisperAudioService instead)
    """

    def __init__(self, config: Dict[str, Any]):
        AudioService.__init__(self, config, "supertonic")

        provider_config = self._extract_provider_config()

        self.model_dir: Optional[str] = provider_config.get("model_dir", None)
        # Supertonic has no separate model-name setting — identify it by the local
        # directory it was downloaded to (matches the `hf download` setup instructions).
        self.model: str = (
            os.path.basename(str(self.model_dir).rstrip("/\\")) if self.model_dir else DEFAULT_MODEL_NAME
        ) or DEFAULT_MODEL_NAME
        self.tts_voice: str = provider_config.get("tts_voice", "F1")
        self.tts_language: str = provider_config.get("tts_language", "en")
        self.tts_format: str = provider_config.get("tts_format", "wav")
        self.total_steps: int = int(provider_config.get("total_steps", 8))
        self.speed: float = float(provider_config.get("speed", 1.05))

        self.tts: Optional[SupertonicTTS] = None
        self._tts_initialized = False

        timeout_config = self._get_timeout_config()
        self.connection_manager = ConnectionManager(
            base_url="local://supertonic-tts",
            api_key="",
            timeout_ms=timeout_config["total"],
        )

        self.connection_verified = False
        self._verification_attempted = False
        self._verification_inflight = False

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config["max_retries"],
            initial_wait_ms=retry_config["initial_wait_ms"],
            max_wait_ms=retry_config["max_wait_ms"],
            exponential_base=retry_config["exponential_base"],
            enabled=retry_config["enabled"],
        )

        logger.debug(
            f"Configured Supertonic TTS: model_dir={self.model_dir}, "
            f"voice={self.tts_voice}, lang={self.tts_language}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _initialize_tts(self) -> bool:
        """Load the Supertonic model (blocking — run via executor)."""
        global _global_tts_model, _global_tts_model_dir

        if not SUPERTONIC_AVAILABLE:
            logger.error("Supertonic package not found. Install with: pip install supertonic")
            return False

        if self._tts_initialized and self.tts is not None:
            return True

        # Reuse cached instance if the model directory is the same.
        if _global_tts_model is not None and _global_tts_model_dir == self.model_dir:
            self.tts = _global_tts_model
            self._tts_initialized = True
            logger.debug("Reusing cached Supertonic TTS model")
            return True

        try:
            logger.debug(f"Loading Supertonic TTS model from: {self.model_dir or '(auto-download)'}")
            if self.model_dir:
                # auto_download=False: use only the local directory, no network calls.
                self.tts = SupertonicTTS(model_dir=self.model_dir, auto_download=False)
            else:
                self.tts = SupertonicTTS(auto_download=True)

            _global_tts_model = self.tts
            _global_tts_model_dir = self.model_dir
            self._tts_initialized = True
            logger.debug("Supertonic TTS model loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load Supertonic TTS model: {e}")
            return False

    def _synthesize(self, text: str, voice: str, language: str, total_steps: int, speed: float) -> bytes:
        """Run synthesis in blocking mode (called from executor)."""
        import numpy as np

        voice_style = self.tts.get_voice_style(voice_name=voice)
        wav, duration = self.tts.synthesize(
            text,
            voice_style=voice_style,
            lang=language,
            total_steps=total_steps,
            speed=speed,
        )

        # wav shape: (1, num_samples), float32
        num_samples = int(SAMPLE_RATE * duration[0].item())
        audio = wav[0, :num_samples]

        # Clamp and convert float32 → int16
        audio = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio * 32767).astype(np.int16)

        # Pack as WAV in memory
        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        buf.seek(0)
        return buf.read()

    # ------------------------------------------------------------------
    # AudioService lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        if self.initialized:
            return True

        if not SUPERTONIC_AVAILABLE:
            logger.error("Supertonic package not available. Install with: pip install supertonic")
            return False

        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, self._initialize_tts)
        if not success:
            return False

        self.initialized = True
        self.connection_verified = True
        logger.debug("Supertonic TTS service initialized")
        return True

    async def verify_connection(self) -> bool:
        if not self._tts_initialized or self.tts is None:
            return await self.initialize()
        return True

    async def close(self) -> None:
        if self.connection_manager:
            await self.connection_manager.close()
        self.tts = None
        self.initialized = False
        self._tts_initialized = False
        self.connection_verified = False
        self._verification_attempted = False
        self._verification_inflight = False
        logger.debug("Closed Supertonic TTS service")

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """
        Convert text to speech using the local Supertonic model.

        Args:
            text: Input text (supports inline tags: <laugh>, <breath>, etc.)
            voice: Voice style name — M1–M5, F1–F5, or path to a custom JSON profile.
            format: Output format (only 'wav' is supported natively).
            **kwargs:
                language (str): BCP-47 language code or "na" for language-agnostic mode.
                total_steps (int): Diffusion steps 5–12 (higher = better quality).
                speed (float): Speaking speed 0.7–2.0.
        """
        if not self.initialized:
            await self.initialize()

        if not self._tts_initialized or self.tts is None:
            raise RuntimeError("Supertonic TTS model is not initialized")

        voice_name = voice or self.tts_voice
        language = kwargs.get("language", self.tts_language)
        total_steps = int(kwargs.get("total_steps", self.total_steps))
        speed = float(kwargs.get("speed", self.speed))
        audio_format = format or self.tts_format

        if audio_format.lower() != "wav":
            logger.warning(f"Supertonic only outputs WAV natively; ignoring requested format '{audio_format}'")

        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            self._synthesize,
            text,
            voice_name,
            language,
            total_steps,
            speed,
        )
        return audio_bytes

    # ------------------------------------------------------------------
    # STT — not supported
    # ------------------------------------------------------------------

    async def speech_to_text(self, audio: Union[str, bytes], language: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError(
            "Supertonic is TTS-only. Use WhisperAudioService for speech-to-text."
        )

    async def transcribe(self, audio: Union[str, bytes], language: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError(
            "Supertonic is TTS-only. Use WhisperAudioService for transcription."
        )

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs,
    ) -> str:
        raise NotImplementedError(
            "Supertonic is TTS-only. Use WhisperAudioService for translation."
        )

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _get_timeout_config(self) -> Dict[str, int]:
        provider_config = self._extract_provider_config()
        t = provider_config.get("timeout", {})
        return {
            "connect": t.get("connect", 5000),
            "total": t.get("total", 120000),
        }

    def _get_retry_config(self) -> Dict[str, Any]:
        provider_config = self._extract_provider_config()
        r = provider_config.get("retry", {})
        return {
            "enabled": r.get("enabled", False),
            "max_retries": r.get("max_retries", 1),
            "initial_wait_ms": r.get("initial_wait_ms", 1000),
            "max_wait_ms": r.get("max_wait_ms", 5000),
            "exponential_base": r.get("exponential_base", 2),
        }
