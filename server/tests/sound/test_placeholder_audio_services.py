#!/usr/bin/env python3
"""
Test the Anthropic placeholder audio service and the Cohere audio service.

- Anthropic: full placeholder (no audio API yet) — every method raises
  NotImplementedError with a "coming soon" style message.
- Cohere: real speech-to-text via Cohere's v2 transcription API; only
  text-to-speech and translation remain unsupported (Cohere has no TTS API),
  raising NotImplementedError with a permanent "use another provider" message
  rather than Anthropic's "not yet supported" framing.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

# Get the absolute path to the server directory
# Since we're in tests/sound/, we need to go up two levels to get to server/
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.implementations.audio.anthropic_audio_service import AnthropicAudioService
from ai_services.implementations.audio.cohere_audio_service import CohereAudioService
from ai_services.base import ServiceType


class TestAnthropicAudioServicePlaceholder:
    """Test cases for Anthropic audio service placeholder."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return {
            "sounds": {
                "anthropic": {
                    "enabled": False,
                    "api_key": "test-anthropic-key",
                    "api_base": "https://api.anthropic.com/v1",
                    "stt_model": None,
                    "tts_model": None
                }
            }
        }

    @pytest.fixture
    def service(self, config):
        """Create a service instance."""
        return AnthropicAudioService(config)

    def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.service_type == ServiceType.AUDIO
        assert service.provider_name == "anthropic"
        assert service.stt_model is None
        assert service.tts_model is None

    @pytest.mark.asyncio
    async def test_text_to_speech_not_implemented(self, service):
        """Test that TTS raises NotImplementedError."""
        with pytest.raises(NotImplementedError) as exc_info:
            await service.text_to_speech("Hello, world!")

        assert "Anthropic doesn't currently support text-to-speech" in str(exc_info.value)
        assert "audio API support" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_speech_to_text_not_implemented(self, service):
        """Test that STT raises NotImplementedError."""
        with pytest.raises(NotImplementedError) as exc_info:
            await service.speech_to_text(b"audio data")

        assert "Anthropic doesn't currently support speech-to-text" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcribe_not_implemented(self, service):
        """Test that transcribe raises NotImplementedError."""
        with pytest.raises(NotImplementedError) as exc_info:
            await service.transcribe(b"audio data")

        assert "Anthropic doesn't currently support audio transcription" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_translate_not_implemented(self, service):
        """Test that translate raises NotImplementedError."""
        with pytest.raises(NotImplementedError) as exc_info:
            await service.translate(b"audio data", target_language="en")

        assert "Anthropic doesn't currently support audio translation" in str(exc_info.value)


class TestCohereAudioServiceSTT:
    """Test cases for Cohere's real speech-to-text support and its TTS/translate gaps."""

    @pytest.fixture
    def config(self):
        """Create a test configuration using the real stt_providers.cohere schema."""
        return {
            "stt_providers": {
                "cohere": {
                    "enabled": False,
                    "api_key": "test-cohere-key",
                    "api_base": "https://api.cohere.com/v2",
                    "stt_model": "cohere-transcribe-03-2026",
                }
            }
        }

    @pytest.fixture
    def service(self, config):
        """Create a service instance."""
        return CohereAudioService(config)

    def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.service_type == ServiceType.AUDIO
        assert service.provider_name == "cohere"
        assert service.stt_model == "cohere-transcribe-03-2026"
        # Cohere is STT-only; it has no tts_model attribute at all.
        assert not hasattr(service, "tts_model")

    @pytest.mark.asyncio
    async def test_text_to_speech_not_implemented(self, service):
        """Test that TTS raises NotImplementedError (Cohere has no TTS API)."""
        with pytest.raises(NotImplementedError) as exc_info:
            await service.text_to_speech("Hello, world!")

        assert "Cohere does not support text-to-speech" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_speech_to_text_returns_transcript(self, service, monkeypatch):
        """Test that STT calls Cohere's transcription endpoint and returns the transcript."""
        await service.initialize()

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"text": "hello world"}
        service.client.post = AsyncMock(return_value=mock_response)

        result = await service.speech_to_text(b"RIFF....WAVEfmt ")

        assert result == "hello world"
        service.client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transcribe_returns_transcript(self, service, monkeypatch):
        """Test that transcribe (alias for speech_to_text) returns the transcript."""
        await service.initialize()

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"text": "hello world"}
        service.client.post = AsyncMock(return_value=mock_response)

        result = await service.transcribe(b"RIFF....WAVEfmt ")

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_translate_not_implemented(self, service):
        """Test that translate raises NotImplementedError (no translation API)."""
        with pytest.raises(NotImplementedError) as exc_info:
            await service.translate(b"audio data", target_language="en")

        assert "Cohere audio transcription does not support translation" in str(exc_info.value)


class TestPlaceholderServicesConfiguration:
    """Test placeholder services handle various configurations."""

    def test_anthropic_with_minimal_config(self):
        """Test Anthropic service with minimal configuration."""
        config = {
            "sounds": {
                "anthropic": {
                    "enabled": False,
                    "api_key": "test-key"
                }
            }
        }

        service = AnthropicAudioService(config)

        assert service.provider_name == "anthropic"
        # Models should be None or extracted from config
        assert service.stt_model is None or isinstance(service.stt_model, str)

    def test_cohere_with_minimal_config(self):
        """Test Cohere service with minimal configuration."""
        config = {
            "stt_providers": {
                "cohere": {
                    "enabled": False,
                    "api_key": "test-key"
                }
            }
        }

        service = CohereAudioService(config)

        assert service.provider_name == "cohere"
        # stt_model falls back to Cohere's default when not configured
        assert isinstance(service.stt_model, str)

    def test_placeholder_services_inherit_from_base(self):
        """Test that placeholder services inherit from AudioService."""
        from ai_services.services.audio_service import AudioService

        config = {
            "sounds": {
                "anthropic": {"enabled": False, "api_key": "test"},
            },
            "stt_providers": {
                "cohere": {"enabled": False, "api_key": "test"}
            }
        }

        anthropic_service = AnthropicAudioService(config)
        cohere_service = CohereAudioService(config)

        # Both should be instances of AudioService
        assert isinstance(anthropic_service, AudioService)
        assert isinstance(cohere_service, AudioService)

        # Both should have helper methods from AudioService
        assert hasattr(anthropic_service, '_prepare_audio')
        assert hasattr(anthropic_service, '_get_audio_format')
        assert hasattr(anthropic_service, '_validate_audio_format')

        assert hasattr(cohere_service, '_prepare_audio')
        assert hasattr(cohere_service, '_get_audio_format')
        assert hasattr(cohere_service, '_validate_audio_format')


class TestPlaceholderServicesErrorMessages:
    """Test that placeholder services provide helpful error messages."""

    @pytest.mark.asyncio
    async def test_anthropic_error_message_clarity(self):
        """Test that Anthropic error messages are clear and helpful."""
        config = {
            "sounds": {
                "anthropic": {
                    "enabled": False,
                    "api_key": "test-key"
                }
            }
        }

        service = AnthropicAudioService(config)

        # Test each method has a clear, helpful error message
        methods_to_test = [
            ("text_to_speech", lambda: service.text_to_speech("test")),
            ("speech_to_text", lambda: service.speech_to_text(b"audio")),
            ("transcribe", lambda: service.transcribe(b"audio")),
            ("translate", lambda: service.translate(b"audio")),
        ]

        for method_name, method_call in methods_to_test:
            with pytest.raises(NotImplementedError) as exc_info:
                await method_call()

            error_msg = str(exc_info.value)
            # Error message should mention Anthropic
            assert "Anthropic" in error_msg
            # Error message should indicate it's not currently supported
            assert "doesn't currently support" in error_msg or "not yet supported" in error_msg
            # Error message should give hope for future support
            assert "will be available" in error_msg or "when" in error_msg

    @pytest.mark.asyncio
    async def test_cohere_error_message_clarity(self):
        """Test that Cohere's unsupported-capability error messages are clear and helpful.

        Unlike Anthropic's full placeholder, Cohere only lacks TTS and audio
        translation — those are permanent product gaps, not "coming soon"
        features, so the messages point to another provider instead of
        promising future support.
        """
        config = {
            "stt_providers": {
                "cohere": {
                    "enabled": False,
                    "api_key": "test-key"
                }
            }
        }

        service = CohereAudioService(config)

        # Only TTS and translation are unimplemented for Cohere; speech-to-text
        # and transcribe are real API calls, covered separately above.
        methods_to_test = [
            ("text_to_speech", lambda: service.text_to_speech("test")),
            ("translate", lambda: service.translate(b"audio")),
        ]

        for method_name, method_call in methods_to_test:
            with pytest.raises(NotImplementedError) as exc_info:
                await method_call()

            error_msg = str(exc_info.value)
            # Error message should mention Cohere
            assert "Cohere" in error_msg
            # Error message should indicate it's not supported
            assert "does not support" in error_msg
            # Error message should point to an alternative
            assert "another provider" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
