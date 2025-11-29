"""
Coqui TTS audio service implementation using unified architecture.

Coqui TTS (https://github.com/coqui-ai/TTS) is an open-source text-to-speech
synthesis library that runs completely locally. It supports multiple languages,
voices, and even voice cloning.

This service provides TTS-only functionality (no STT).

Requires: pip install TTS
"""

from typing import Dict, Any, Optional, Union
from io import BytesIO
import asyncio
import logging
import wave
import numpy as np

from ...base import ServiceType
from ...services import AudioService
from ...connection import ConnectionManager, RetryHandler


logger = logging.getLogger(__name__)
# Optional TTS import
try:
    from TTS.api import TTS as CoquiTTS
    import torch
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    CoquiTTS = None
    torch = None

# Global TTS model cache (singleton pattern for efficiency)
_global_tts_model = None
_global_tts_config = None


class CoquiAudioService(AudioService):
    """
    Coqui TTS audio service using unified architecture.

    Supports:
    - Text-to-speech using local Coqui TTS models
    - Multiple languages and voices
    - GPU acceleration (CUDA)
    - Various TTS models (Tacotron2, VITS, XTTS, etc.)

    Does NOT support:
    - Speech-to-text (use WhisperAudioService instead)
    - Audio transcription
    - Audio translation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Coqui TTS audio service."""
        # Initialize via AudioService base class
        AudioService.__init__(self, config, "coqui")

        # Get audio-specific configuration
        provider_config = self._extract_provider_config()

        # Model configuration
        self.tts_model = provider_config.get('tts_model', 'tts_models/en/ljspeech/tacotron2-DDC')
        self.vocoder_model = provider_config.get('vocoder_model', 'vocoder_models/en/ljspeech/hifigan_v2')
        self.speaker = provider_config.get('speaker', None)
        self.language = provider_config.get('language', 'en')
        self.tts_format = provider_config.get('tts_format', 'wav')

        # Device configuration
        device_config = provider_config.get('device', 'auto')
        use_cuda = provider_config.get('use_cuda', True)

        # Determine device
        if device_config == 'auto':
            if TTS_AVAILABLE and torch is not None and torch.cuda.is_available() and use_cuda:
                self.device = 'cuda'
            else:
                self.device = 'cpu'
        elif device_config == 'cuda':
            if TTS_AVAILABLE and torch is not None and torch.cuda.is_available():
                self.device = 'cuda'
            else:
                logger.warning("CUDA requested but not available, falling back to CPU")
                self.device = 'cpu'
        else:
            self.device = 'cpu'

        # Synthesis parameters
        self.speed = provider_config.get('speed', 1.0)

        # TTS model instance
        self.tts = None
        self._tts_initialized = False

        # Setup connection manager (for local processing, this is minimal)
        timeout_config = self._get_timeout_config()
        self.connection_manager = ConnectionManager(
            base_url="local://coqui-tts",
            api_key="",
            timeout_ms=timeout_config['total']
        )

        self.connection_verified = False
        self._verification_attempted = False
        self._verification_inflight = False

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        logger.debug(
            f"Configured Coqui TTS service with model: {self.tts_model}, "
            f"device: {self.device}, language: {self.language}"
        )

    def _extract_provider_config(self) -> Dict[str, Any]:
        """
        Extract provider-specific configuration from the config dictionary.

        Override base method to look for 'sounds' (the actual key in sound.yaml)
        instead of 'audios' (the default plural form).
        """
        # Try 'sounds' first (as used in config/sound.yaml)
        sounds_config = self.config.get('sounds', {})
        provider_config = sounds_config.get(self.provider_name, {})

        if provider_config:
            return provider_config

        # Fallback to base class logic
        return super()._extract_provider_config()

    def _initialize_tts(self) -> bool:
        """Initialize Coqui TTS model."""
        global _global_tts_model, _global_tts_config

        if not TTS_AVAILABLE:
            logger.error(
                "Coqui TTS library not available. Install with: pip install TTS"
            )
            return False

        if self._tts_initialized and self.tts is not None:
            return True

        # Check if we can reuse a cached model with the same configuration
        current_config = {
            'model': self.tts_model,
            'vocoder': self.vocoder_model,
            'device': self.device
        }

        if _global_tts_model is not None and _global_tts_config == current_config:
            self.tts = _global_tts_model
            self._tts_initialized = True
            logger.debug(f"Using cached Coqui TTS model on device: {self.device}")
            return True

        try:
            logger.debug(f"Loading Coqui TTS model: {self.tts_model} on device: {self.device}")
            if self.device == 'cuda' and torch.cuda.is_available():
                logger.debug(
                    f"GPU: {torch.cuda.get_device_name(0)}, "
                    f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB"
                )

            # Initialize TTS model
            # For models that need a separate vocoder, TTS will load it automatically
            self.tts = CoquiTTS(
                model_name=self.tts_model,
                vocoder_name=self.vocoder_model if self._needs_vocoder() else None,
                gpu=(self.device == 'cuda')
            )

            # Warm up the model with a short test (reduces first inference latency)
            logger.debug("Warming up Coqui TTS model...")

            test_text = "Hello"
            try:
                # Run a quick test synthesis
                if self.speaker:
                    _ = self.tts.tts(text=test_text, speaker=self.speaker, language=self.language)
                else:
                    _ = self.tts.tts(text=test_text, language=self.language)

                if self.device == 'cuda' and torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()

                logger.debug("Model warm-up completed")
            except Exception as warmup_error:
                logger.warning(f"Model warm-up failed (non-critical): {str(warmup_error)}")

            self._tts_initialized = True

            # Cache globally for reuse
            _global_tts_model = self.tts
            _global_tts_config = current_config

            logger.debug("Coqui TTS model loaded successfully")
            if self.device == 'cuda' and torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated(0) / 1024**2
                reserved = torch.cuda.memory_reserved(0) / 1024**2
                logger.debug(f"GPU memory - Allocated: {allocated:.2f} MB, Reserved: {reserved:.2f} MB")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize Coqui TTS model: {str(e)}")
            return False

    def _needs_vocoder(self) -> bool:
        """
        Check if the TTS model needs a separate vocoder.

        Some models (like VITS, XTTS) have built-in vocoders.
        Others (like Tacotron2, GlowTTS) output spectrograms and need a vocoder.
        """
        # Models with built-in vocoders
        builtin_vocoder_models = ['vits', 'xtts', 'overflow', 'capacitron']

        model_lower = self.tts_model.lower()
        return not any(model in model_lower for model in builtin_vocoder_models)

    async def initialize(self) -> bool:
        """Initialize the Coqui TTS audio service."""
        try:
            if self.initialized:
                return True

            if not TTS_AVAILABLE:
                logger.error(
                    "Coqui TTS is not available. Install with: pip install TTS"
                )
                return False

            # Initialize TTS model in a thread pool to avoid blocking
            # (model loading can take a few seconds)
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self._initialize_tts)

            if not success:
                return False

            self.initialized = True
            self.connection_verified = True  # Local service, no remote connection needed

            logger.debug(
                f"Initialized Coqui TTS service with model {self.tts_model} on {self.device}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Coqui TTS service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify TTS model is loaded and working.

        For local processing, this is a simple check.
        """
        try:
            if not self._tts_initialized or self.tts is None:
                return await self.initialize()

            logger.debug("Coqui TTS connection verified (local service)")
            return True

        except Exception as e:
            logger.error(f"Coqui TTS verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the Coqui TTS service and release resources."""
        if self.connection_manager:
            await self.connection_manager.close()

        # Clean up GPU memory if using CUDA
        if self.device == 'cuda' and TTS_AVAILABLE and torch is not None:
            if torch.cuda.is_available():
                # Note: We keep the global model cached for reuse
                # Only clear the local reference
                self.tts = None
                torch.cuda.empty_cache()
                logger.debug("GPU memory cleared (model remains cached)")

        self.initialized = False
        self._verification_attempted = False
        self.connection_verified = False
        self._verification_inflight = False
        self._tts_initialized = False
        logger.debug("Closed Coqui TTS service")

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Convert text to speech audio using Coqui TTS.

        Args:
            text: Text to convert to speech
            voice: Optional speaker name (for multi-speaker models)
            format: Optional audio format (e.g., 'wav', 'mp3')
            **kwargs: Additional parameters:
                - speed: Speech speed multiplier (default: 1.0)
                - language: Language code (for multilingual models)

        Returns:
            Audio data as bytes
        """
        if not self.initialized:
            await self.initialize()

        if not self._tts_initialized or self.tts is None:
            raise RuntimeError("Coqui TTS model not initialized")

        try:
            # Get parameters
            speaker = voice or self.speaker or kwargs.get('speaker')
            language = kwargs.get('language', self.language)
            speed = kwargs.get('speed', self.speed)
            audio_format = format or self.tts_format

            # Run TTS in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                None,
                self._synthesize_speech,
                text,
                speaker,
                language,
                speed
            )

            # Convert to requested format if needed
            if audio_format.lower() == 'wav':
                return self._to_wav_bytes(audio_data)
            else:
                # For other formats, return the raw audio
                # In production, you'd convert to mp3/ogg etc. using pydub or similar
                logger.warning(f"Format '{audio_format}' not natively supported, returning WAV")
                return self._to_wav_bytes(audio_data)

        except Exception as e:
            logger.error(f"Coqui TTS error: {str(e)}")
            raise

    def _synthesize_speech(
        self,
        text: str,
        speaker: Optional[str],
        language: str,
        speed: float
    ) -> np.ndarray:
        """
        Synthesize speech using Coqui TTS (blocking operation).

        This runs in a thread pool executor to avoid blocking the event loop.
        """
        try:
            # Build TTS arguments
            tts_kwargs = {
                'text': text,
                'language': language
            }

            # Add speaker if specified and model supports it
            if speaker and self.tts.is_multi_speaker:
                tts_kwargs['speaker'] = speaker

            # Add language if model supports it
            if language and self.tts.is_multi_lingual:
                tts_kwargs['language'] = language

            # Some models support speed parameter
            if hasattr(self.tts, 'synthesizer') and speed != 1.0:
                tts_kwargs['speed'] = speed

            # Generate audio
            logger.debug(f"Synthesizing: '{text[:50]}...' with Coqui TTS")

            # TTS returns a numpy array
            audio_array = self.tts.tts(**tts_kwargs)

            duration = len(audio_array) / self.tts.synthesizer.output_sample_rate if hasattr(self.tts, 'synthesizer') else len(audio_array) / 22050
            logger.debug(f"Generated {len(audio_array)} samples ({duration:.2f}s)")

            return audio_array

        except Exception as e:
            logger.error(f"Speech synthesis failed: {str(e)}")
            raise

    def _to_wav_bytes(self, audio_array: np.ndarray) -> bytes:
        """
        Convert numpy audio array to WAV bytes.

        Args:
            audio_array: Audio data as numpy array (float32, -1.0 to 1.0)

        Returns:
            WAV file as bytes
        """
        # Get sample rate from TTS model
        if hasattr(self.tts, 'synthesizer') and hasattr(self.tts.synthesizer, 'output_sample_rate'):
            sample_rate = self.tts.synthesizer.output_sample_rate
        else:
            # Default sample rate (most Coqui models use 22050)
            sample_rate = 22050

        # Convert float32 to int16
        # Ensure audio is in range [-1.0, 1.0]
        audio_array = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_array * 32767).astype(np.int16)

        # Create WAV file in memory
        wav_buffer = BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        wav_buffer.seek(0)
        return wav_buffer.read()

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Convert speech audio to text.

        NOT SUPPORTED by Coqui TTS (TTS-only library).
        Use WhisperAudioService or OpenAIAudioService for STT.
        """
        raise NotImplementedError(
            "Speech-to-text is not supported by Coqui TTS. "
            "Coqui TTS is a TTS-only library. "
            "For STT, use WhisperAudioService, OpenAIAudioService, or GoogleAudioService."
        )

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Transcribe audio to text.

        NOT SUPPORTED by Coqui TTS (TTS-only library).
        """
        raise NotImplementedError(
            "Transcription is not supported by Coqui TTS. "
            "Use WhisperAudioService for local transcription."
        )

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """
        Translate audio from one language to another.

        NOT SUPPORTED by Coqui TTS (TTS-only library).
        """
        raise NotImplementedError(
            "Translation is not supported by Coqui TTS. "
            "Use WhisperAudioService for local translation."
        )

    def _get_timeout_config(self) -> Dict[str, int]:
        """Get timeout configuration."""
        provider_config = self._extract_provider_config()
        timeout_config = provider_config.get('timeout', {})
        return {
            'connect': timeout_config.get('connect', 5000),
            'total': timeout_config.get('total', 120000)
        }

    def _get_retry_config(self) -> Dict[str, Any]:
        """Get retry configuration."""
        provider_config = self._extract_provider_config()
        retry_config = provider_config.get('retry', {})
        return {
            'enabled': retry_config.get('enabled', False),
            'max_retries': retry_config.get('max_retries', 1),
            'initial_wait_ms': retry_config.get('initial_wait_ms', 1000),
            'max_wait_ms': retry_config.get('max_wait_ms', 5000),
            'exponential_base': retry_config.get('exponential_base', 2)
        }
