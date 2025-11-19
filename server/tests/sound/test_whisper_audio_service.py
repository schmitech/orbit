#!/usr/bin/env python3
"""
Test Whisper audio service implementation.

This module tests the local Whisper audio service specifically:
- Speech-to-text transcription using OpenAI's Whisper
- Local model loading and inference
- Language detection
- Audio translation (to English)
- Error handling for TTS (not supported)
"""

import pytest
import sys
import os
from pathlib import Path

# Get the absolute path to the server directory
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

# Try importing WhisperAudioService
try:
    from ai_services.implementations.whisper_audio_service import WhisperAudioService, WHISPER_AVAILABLE
    from ai_services.base import ServiceType
except ImportError as e:
    pytest.skip(f"WhisperAudioService not available: {e}", allow_module_level=True)


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="Whisper package not installed")
class TestWhisperAudioService:
    """Test cases for Whisper audio service."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return {
            "sounds": {
                "whisper": {
                    "enabled": True,
                    "model_size": "tiny",  # Use tiny model for faster testing
                    "device": "cpu",  # Force CPU for consistency
                    "language": None,  # Auto-detect
                    "task": "transcribe"
                }
            }
        }

    @pytest.fixture
    def service(self, config):
        """Create a service instance."""
        if not WHISPER_AVAILABLE:
            pytest.skip("Whisper not available")
        return WhisperAudioService(config)

    @pytest.fixture
    def test_audio_file(self):
        """Path to test audio file."""
        # Get path relative to server directory
        test_file = os.path.join(
            os.path.dirname(server_dir),  # Go up from server/ to orbit/
            "examples", "sample-files", "harvard.wav"
        )
        if not os.path.exists(test_file):
            pytest.skip(f"Test audio file not found: {test_file}")
        return test_file

    def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.service_type == ServiceType.AUDIO
        assert service.provider_name == "whisper"
        assert service.model_size == "tiny"
        assert service.device == "cpu"
        assert service.language is None
        assert service.task == "transcribe"
        assert service.model is None  # Not loaded until initialize()
        assert service.model_loaded is False

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization and model loading."""
        print(f"\nInitializing Whisper with model size: {service.model_size}")
        result = await service.initialize()

        assert result is None  # initialize() doesn't return a value
        assert service.initialized is True
        assert service.model is not None
        assert service.model_loaded is True
        print("✓ Model loaded successfully")

    @pytest.mark.asyncio
    async def test_speech_to_text_with_file(self, service, test_audio_file):
        """Test transcription with actual audio file."""
        print(f"\nTranscribing audio file: {test_audio_file}")

        # Read audio file
        with open(test_audio_file, 'rb') as f:
            audio_data = f.read()

        print(f"Audio file size: {len(audio_data)} bytes")

        # Transcribe
        text = await service.speech_to_text(audio_data)

        print(f"Transcription result: {text[:100]}...")  # Print first 100 chars

        assert isinstance(text, str)
        assert len(text) > 0
        # The Harvard sentences should contain recognizable words
        assert any(word in text.lower() for word in ['the', 'and', 'of', 'a'])
        print("✓ Transcription successful")

    @pytest.mark.asyncio
    async def test_transcribe_alias(self, service, test_audio_file):
        """Test that transcribe() is an alias for speech_to_text()."""
        with open(test_audio_file, 'rb') as f:
            audio_data = f.read()

        text = await service.transcribe(audio_data)

        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_translate_to_english(self, service, test_audio_file):
        """Test translation functionality (translates to English)."""
        with open(test_audio_file, 'rb') as f:
            audio_data = f.read()

        # Translate should work (even though input is already English)
        text = await service.translate(
            audio_data,
            source_language=None,
            target_language="en"
        )

        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_translate_to_non_english_falls_back(self, service, test_audio_file):
        """Test that translation to non-English language falls back to transcription."""
        with open(test_audio_file, 'rb') as f:
            audio_data = f.read()

        # Should fall back to transcription with a warning
        text = await service.translate(
            audio_data,
            target_language="fr"  # Whisper can't translate TO French
        )

        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_text_to_speech_not_supported(self, service):
        """Test that TTS raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Whisper does not support text-to-speech"):
            await service.text_to_speech("Hello, world!")

    @pytest.mark.asyncio
    async def test_verify_connection(self, service):
        """Test connection verification."""
        result = await service.verify_connection()

        assert result is True
        assert service.initialized is True
        assert service.model_loaded is True

    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test service cleanup."""
        # Initialize first
        await service.initialize()
        assert service.initialized is True

        # Close
        await service.close()

        assert service.initialized is False
        assert service.model is None
        assert service.model_loaded is False

    @pytest.mark.asyncio
    async def test_multiple_transcriptions(self, service, test_audio_file):
        """Test multiple transcriptions in sequence."""
        with open(test_audio_file, 'rb') as f:
            audio_data = f.read()

        # First transcription
        text1 = await service.speech_to_text(audio_data)
        assert len(text1) > 0

        # Second transcription (model should be cached)
        text2 = await service.speech_to_text(audio_data)
        assert len(text2) > 0

        # Results should be similar (Whisper is deterministic with temp=0)
        assert text1 == text2 or len(text1) - len(text2) < 50  # Allow some variation

    def test_initialization_without_whisper(self):
        """Test that service fails gracefully when Whisper is not available."""
        if WHISPER_AVAILABLE:
            pytest.skip("Whisper is available, can't test unavailable case")

        config = {
            "sounds": {
                "whisper": {
                    "enabled": True,
                    "model_size": "base"
                }
            }
        }

        with pytest.raises(ImportError, match="Whisper library not available"):
            service = WhisperAudioService(config)


@pytest.mark.skipif(WHISPER_AVAILABLE, reason="Only test when Whisper is not installed")
class TestWhisperNotAvailable:
    """Test behavior when Whisper is not installed."""

    def test_import_error_when_not_installed(self):
        """Test that appropriate error is raised when Whisper not installed."""
        config = {
            "sounds": {
                "whisper": {
                    "enabled": True,
                    "model_size": "base"
                }
            }
        }

        with pytest.raises(ImportError, match="Whisper library not available"):
            WhisperAudioService(config)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
