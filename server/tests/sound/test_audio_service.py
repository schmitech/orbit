#!/usr/bin/env python3
"""
Test audio service implementations and registration.

This module tests the audio service functionality including:
- Audio service registration
- Provider implementations (OpenAI, Google, Anthropic, Ollama, Cohere)
- Text-to-speech (TTS) and speech-to-text (STT)
- Audio transcription and translation
- Error handling
"""

import pytest
import sys
import os
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# Get the absolute path to the server directory (parent of tests)
# Since we're in tests/sound/, we need to go up two levels to get to server/
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add server directory to Python path
sys.path.append(server_dir)

from ai_services.registry import register_audio_services
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType


class TestAudioServiceRegistration:
    """Test cases for audio service registration."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset the factory before each test to ensure clean state."""
        # Clear the factory's internal registry before each test
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        # Reset the registration flag
        import ai_services.registry as registry_module
        registry_module._services_registered = False
        yield
        # Clean up after test
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        registry_module._services_registered = False

    @pytest.fixture
    def enabled_providers_config(self) -> Dict[str, Any]:
        """Create a config with all audio providers enabled."""
        return {
            "sounds": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-openai-key",
                    "stt_model": "whisper-1",
                    "tts_model": "tts-1",
                    "tts_voice": "alloy",
                    "tts_format": "mp3"
                },
                "google": {
                    "enabled": True,
                    "api_key": "test-google-key",
                    "stt_model": "latest_long",
                    "tts_model": "neural2",
                    "tts_voice": "en-US-Neural2-A"
                },
                "anthropic": {
                    "enabled": True,
                    "api_key": "test-anthropic-key",
                    "stt_model": None,
                    "tts_model": None
                },
                "ollama": {
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "stt_model": "whisper",
                    "tts_model": "piper",
                    "tts_voice": "en_US-lessac-medium"
                },
                "cohere": {
                    "enabled": True,
                    "api_key": "test-cohere-key",
                    "stt_model": None,
                    "tts_model": None
                }
            }
        }

    @pytest.fixture
    def partial_enabled_config(self) -> Dict[str, Any]:
        """Create a config with only some audio providers enabled."""
        return {
            "sounds": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-openai-key",
                    "stt_model": "whisper-1"
                },
                "google": {
                    "enabled": False,
                    "api_key": "test-google-key"
                },
                "anthropic": {
                    "enabled": False,
                    "api_key": "test-anthropic-key"
                },
                "ollama": {
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "stt_model": "whisper"
                },
                "cohere": {
                    "enabled": False,
                    "api_key": "test-cohere-key"
                }
            }
        }

    def test_register_all_audio_providers(self, enabled_providers_config):
        """Test that all audio providers are registered when enabled."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            # Create a mock module with mock service classes
            mock_module = MagicMock()
            mock_module.OpenAIAudioService = MagicMock()
            mock_module.GoogleAudioService = MagicMock()
            mock_module.AnthropicAudioService = MagicMock()
            mock_module.OllamaAudioService = MagicMock()
            mock_module.CohereAudioService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                # For other imports, use the real import
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_audio_services(enabled_providers_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])

            # Verify that all providers are registered
            assert 'openai' in audio_providers
            assert 'google' in audio_providers
            assert 'anthropic' in audio_providers
            assert 'ollama' in audio_providers
            assert 'cohere' in audio_providers

    def test_register_partial_audio_providers(self, partial_enabled_config):
        """Test that only enabled audio providers are registered."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIAudioService = MagicMock()
            mock_module.OllamaAudioService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_audio_services(partial_enabled_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])

            # Verify that only enabled providers are registered
            assert 'openai' in audio_providers
            assert 'ollama' in audio_providers
            assert 'google' not in audio_providers
            assert 'anthropic' not in audio_providers
            assert 'cohere' not in audio_providers

    def test_register_without_config(self):
        """Test that providers are registered when no config is provided."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIAudioService = MagicMock()
            mock_module.GoogleAudioService = MagicMock()
            mock_module.AnthropicAudioService = MagicMock()
            mock_module.OllamaAudioService = MagicMock()
            mock_module.CohereAudioService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services without config (backward compatibility)
            register_audio_services(None)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])

            # When no config is provided, all providers should be attempted
            assert 'openai' in audio_providers
            assert 'google' in audio_providers
            assert 'anthropic' in audio_providers
            assert 'ollama' in audio_providers
            assert 'cohere' in audio_providers


class TestAudioServiceHelpers:
    """Test audio service helper methods."""

    @pytest.fixture
    def sample_audio_bytes(self):
        """Create sample audio bytes for testing."""
        # Create a minimal WAV file header
        return b'RIFF' + b'\x00' * 4 + b'WAVE' + b'fmt ' + b'\x00' * 20

    def test_prepare_audio_from_bytes(self, sample_audio_bytes):
        """Test preparing audio from bytes."""
        from ai_services.services.audio_service import AudioService

        # Create a minimal mock implementation with all required methods
        config = {"api_key": "test"}

        class TestAudioService(AudioService):
            async def text_to_speech(self, text, voice=None, format=None, **kwargs): pass
            async def speech_to_text(self, audio, language=None, **kwargs): pass
            async def transcribe(self, audio, language=None, **kwargs): pass
            async def translate(self, audio, source_language=None, target_language="en", **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestAudioService(config, "test")

        result = service._prepare_audio(sample_audio_bytes)
        assert isinstance(result, bytes)
        assert result == sample_audio_bytes

    def test_prepare_audio_from_file(self, tmp_path, sample_audio_bytes):
        """Test preparing audio from file path."""
        from ai_services.services.audio_service import AudioService

        # Create a temporary audio file
        audio_file = tmp_path / "test_audio.wav"
        audio_file.write_bytes(sample_audio_bytes)

        # Create a minimal mock implementation
        config = {"api_key": "test"}

        class TestAudioService(AudioService):
            async def text_to_speech(self, text, voice=None, format=None, **kwargs): pass
            async def speech_to_text(self, audio, language=None, **kwargs): pass
            async def transcribe(self, audio, language=None, **kwargs): pass
            async def translate(self, audio, source_language=None, target_language="en", **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestAudioService(config, "test")

        result = service._prepare_audio(str(audio_file))
        assert isinstance(result, bytes)
        assert result == sample_audio_bytes

    def test_get_audio_format_from_path(self):
        """Test getting audio format from file path."""
        from ai_services.services.audio_service import AudioService

        config = {"api_key": "test"}

        class TestAudioService(AudioService):
            async def text_to_speech(self, text, voice=None, format=None, **kwargs): pass
            async def speech_to_text(self, audio, language=None, **kwargs): pass
            async def transcribe(self, audio, language=None, **kwargs): pass
            async def translate(self, audio, source_language=None, target_language="en", **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestAudioService(config, "test")

        assert service._get_audio_format("test.mp3") == "mp3"
        assert service._get_audio_format("test.wav") == "wav"
        assert service._get_audio_format("test.opus") == "opus"
        assert service._get_audio_format("test.ogg") == "ogg"
        assert service._get_audio_format("test.flac") == "flac"
        assert service._get_audio_format("test.m4a") == "m4a"
        assert service._get_audio_format("test.aac") == "aac"

    def test_validate_audio_format(self):
        """Test audio format validation."""
        from ai_services.services.audio_service import AudioService

        config = {"api_key": "test"}

        class TestAudioService(AudioService):
            async def text_to_speech(self, text, voice=None, format=None, **kwargs): pass
            async def speech_to_text(self, audio, language=None, **kwargs): pass
            async def transcribe(self, audio, language=None, **kwargs): pass
            async def translate(self, audio, source_language=None, target_language="en", **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestAudioService(config, "test")

        # Test valid formats
        assert service._validate_audio_format("mp3") is True
        assert service._validate_audio_format("wav") is True
        assert service._validate_audio_format("opus") is True
        assert service._validate_audio_format("MP3") is True  # Case insensitive

        # Test invalid formats
        assert service._validate_audio_format("xyz") is False
        assert service._validate_audio_format("") is False


class TestAudioResult:
    """Test AudioResult class."""

    def test_audio_result_creation_with_text(self):
        """Test creating AudioResult with text (STT result)."""
        from ai_services.services.audio_service import AudioResult

        result = AudioResult(
            text="Hello, world!",
            language="en",
            provider="openai",
            metadata={"model": "whisper-1"}
        )

        assert result.text == "Hello, world!"
        assert result.language == "en"
        assert result.provider == "openai"
        assert result.metadata["model"] == "whisper-1"
        assert result.audio is None
        assert str(result) == "Hello, world!"

    def test_audio_result_creation_with_audio(self):
        """Test creating AudioResult with audio (TTS result)."""
        from ai_services.services.audio_service import AudioResult

        audio_data = b"fake audio data"
        result = AudioResult(
            audio=audio_data,
            format="mp3",
            provider="openai",
            metadata={"model": "tts-1", "voice": "alloy"}
        )

        assert result.audio == audio_data
        assert result.format == "mp3"
        assert result.provider == "openai"
        assert result.metadata["model"] == "tts-1"
        assert result.text is None

    def test_audio_result_to_dict_with_text(self):
        """Test converting AudioResult to dict (text result)."""
        from ai_services.services.audio_service import AudioResult

        result = AudioResult(
            text="Hello, world!",
            language="en",
            provider="openai"
        )

        result_dict = result.to_dict()
        assert result_dict["text"] == "Hello, world!"
        assert result_dict["language"] == "en"
        assert result_dict["provider"] == "openai"
        assert "audio" not in result_dict

    def test_audio_result_to_dict_with_audio(self):
        """Test converting AudioResult to dict (audio result)."""
        from ai_services.services.audio_service import AudioResult

        audio_data = b"fake audio data" * 100
        result = AudioResult(
            audio=audio_data,
            format="mp3",
            provider="openai"
        )

        result_dict = result.to_dict()
        assert result_dict["format"] == "mp3"
        assert result_dict["provider"] == "openai"
        assert result_dict["audio_size"] == len(audio_data)
        assert "<" in result_dict["audio"]  # Should show size, not full data
        assert "bytes" in result_dict["audio"]


class TestAudioServiceFactory:
    """Test audio service creation via factory."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset the factory before each test."""
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        yield
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}

    def test_create_audio_service_function(self):
        """Test create_audio_service factory function."""
        from ai_services.services.audio_service import create_audio_service

        # Mock the factory
        with patch('ai_services.factory.AIServiceFactory.create_service') as mock_create:
            mock_service = MagicMock()
            mock_create.return_value = mock_service

            config = {"sounds": {"openai": {"enabled": True}}}
            service = create_audio_service("openai", config)

            # Verify factory was called correctly
            mock_create.assert_called_once_with(
                ServiceType.AUDIO,
                "openai",
                config
            )
            assert service == mock_service


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
