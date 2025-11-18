"""
Direct Whisper audio service implementation using OpenAI's open-source Whisper.

This implementation provides local, offline speech-to-text using the Whisper model
from https://github.com/openai/whisper

Installation:
    pip install openai-whisper
    # OR for faster inference (requires FFmpeg):
    pip install git+https://github.com/openai/whisper.git

    # For GPU acceleration (optional):
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
"""

from typing import Dict, Any, Optional, Union
import tempfile
import os
from pathlib import Path

try:
    import whisper
    import torch
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

from ..base import ProviderAIService, ServiceType
from ..services import AudioService


class WhisperAudioService(AudioService, ProviderAIService):
    """
    Direct Whisper audio service using OpenAI's open-source model.

    Provides local, offline speech-to-text with high accuracy.
    Does NOT support TTS - use for STT/transcription only.

    Features:
    - 99 languages supported
    - Multiple model sizes (tiny, base, small, medium, large)
    - GPU acceleration (if available)
    - Automatic language detection
    - Timestamp generation
    - No API costs or internet required

    Model sizes:
    - tiny: Fast but less accurate (~1GB VRAM)
    - base: Good balance (~1GB VRAM)
    - small: Recommended for most use cases (~2GB VRAM)
    - medium: High quality (~5GB VRAM)
    - large-v3: Best quality (~10GB VRAM)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Whisper audio service."""
        if not WHISPER_AVAILABLE:
            raise ImportError(
                "Whisper library not available. Install with: pip install openai-whisper"
            )

        # Initialize base service
        ProviderAIService.__init__(self, config, ServiceType.AUDIO, "whisper")

        # Get Whisper-specific configuration
        provider_config = self._extract_provider_config()
        self.model_size = provider_config.get('model_size', 'base')  # tiny, base, small, medium, large-v3
        self.device = provider_config.get('device', 'auto')  # auto, cpu, cuda
        self.compute_type = provider_config.get('compute_type', 'default')  # default, int8, float16
        self.language = provider_config.get('language', None)  # None = auto-detect
        self.task = provider_config.get('task', 'transcribe')  # transcribe or translate

        # Model cache
        self.model = None
        self.model_loaded = False

        self.logger.info(f"Whisper service initialized with model={self.model_size}, device={self.device}")

    def _extract_provider_config(self) -> Dict[str, Any]:
        """Extract Whisper-specific configuration from config."""
        # Check for whisper-specific config
        if 'whisper' in self.config:
            return self.config['whisper']
        # Fallback to sounds section
        elif 'sounds' in self.config and 'whisper' in self.config['sounds']:
            return self.config['sounds']['whisper']
        return {}

    async def initialize(self) -> None:
        """Initialize the Whisper service and load the model."""
        if self.initialized:
            return

        try:
            # Determine device
            if self.device == 'auto':
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            else:
                device = self.device

            self.logger.info(f"Loading Whisper model '{self.model_size}' on device '{device}'...")

            # Load the model
            # This downloads the model on first use (cached in ~/.cache/whisper/)
            self.model = whisper.load_model(self.model_size, device=device)
            self.model_loaded = True

            self.logger.info(f"Whisper model '{self.model_size}' loaded successfully on {device}")
            self.initialized = True

        except Exception as e:
            self.logger.error(f"Failed to initialize Whisper service: {str(e)}")
            raise

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Convert speech audio to text using Whisper.

        Args:
            audio: Audio data as bytes or base64 string
            language: Language code (e.g., 'en', 'es', 'fr'). None = auto-detect
            **kwargs: Additional options:
                - task: 'transcribe' or 'translate' (translate to English)
                - temperature: Sampling temperature (0.0-1.0)
                - beam_size: Beam size for decoding
                - best_of: Number of candidates to sample
                - word_timestamps: Return word-level timestamps

        Returns:
            Transcribed text
        """
        if not self.initialized:
            await self.initialize()

        if not self.model_loaded:
            raise RuntimeError("Whisper model not loaded")

        try:
            # Prepare audio data
            audio_data = self._prepare_audio(audio)

            # Write audio to temporary file (Whisper works with files)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(audio_data)

            try:
                # Transcribe options
                transcribe_options = {
                    'language': language or self.language,
                    'task': kwargs.get('task', self.task),
                    'temperature': kwargs.get('temperature', 0.0),
                    'beam_size': kwargs.get('beam_size', 5),
                    'best_of': kwargs.get('best_of', 5),
                    'word_timestamps': kwargs.get('word_timestamps', False),
                    'verbose': False
                }

                # Remove None values
                transcribe_options = {k: v for k, v in transcribe_options.items() if v is not None}

                self.logger.debug(f"Transcribing with options: {transcribe_options}")

                # Transcribe
                result = self.model.transcribe(temp_path, **transcribe_options)

                # Extract text
                text = result['text'].strip()

                # Log detected language
                detected_language = result.get('language', 'unknown')
                self.logger.info(f"Transcription complete. Detected language: {detected_language}")

                return text

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except Exception as e:
            self.logger.error(f"Whisper transcription error: {str(e)}")
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
        """
        Translate audio from any language to English using Whisper.

        Note: Whisper can only translate TO English, not from English to other languages.
        For other translation directions, use transcribe + separate translation service.

        Args:
            audio: Audio data
            source_language: Source language (optional, auto-detected if None)
            target_language: Must be 'en' (English) - Whisper limitation
            **kwargs: Additional transcription options

        Returns:
            Translated text in English
        """
        if not self.initialized:
            await self.initialize()

        if target_language != 'en':
            # Whisper can only translate to English
            # Fall back to transcription
            self.logger.warning(
                f"Whisper can only translate to English. "
                f"Requested target: {target_language}. Falling back to transcription."
            )
            return await self.speech_to_text(audio, source_language, **kwargs)

        # Use translate task
        kwargs['task'] = 'translate'
        return await self.speech_to_text(audio, source_language, **kwargs)

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Text-to-speech is NOT supported by Whisper (STT only).

        Raises:
            NotImplementedError: Whisper does not support TTS
        """
        raise NotImplementedError(
            "Whisper does not support text-to-speech (TTS). "
            "Use OpenAI TTS API, Google TTS, ElevenLabs, or Ollama TTS instead."
        )

    async def close(self) -> None:
        """Close the Whisper audio service and release resources."""
        await self.cleanup()

    async def verify_connection(self) -> bool:
        """
        Verify that Whisper is available and can load models.

        For a local service, this checks if the model can be initialized.

        Returns:
            True if Whisper is available, False otherwise
        """
        try:
            if not WHISPER_AVAILABLE:
                self.logger.error("Whisper library not available")
                return False

            # If already initialized, we're good
            if self.initialized and self.model_loaded:
                return True

            # Try to initialize
            await self.initialize()
            return self.initialized and self.model_loaded

        except Exception as e:
            self.logger.error(f"Whisper connection verification failed: {str(e)}")
            return False

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.model is not None:
            # Clear model from memory
            del self.model
            self.model = None
            self.model_loaded = False

            # Clear CUDA cache if using GPU
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        self.initialized = False
        self.logger.info("Whisper service cleaned up")
