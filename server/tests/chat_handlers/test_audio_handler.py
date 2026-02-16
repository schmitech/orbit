"""
Tests for AudioHandler.
"""

import pytest
import sys
import os
from unittest.mock import patch

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.chat_handlers.audio_handler import AudioHandler


class TestAudioHandler:
    """Test suite for AudioHandler."""

    def test_initialization(self, base_config, mock_adapter_manager):
        """Test handler initialization with valid config."""
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        assert handler.max_text_length == 4096
        assert handler.max_audio_size_mb == 5
        assert handler.truncate_text is True
        assert handler.warn_on_truncate is True
        assert handler.default_provider == 'openai'

    def test_initialization_with_defaults(self):
        """Test handler uses defaults when config is minimal."""
        handler = AudioHandler(config={})

        assert handler.max_text_length == 4096
        assert handler.max_audio_size_mb == 5
        assert handler.truncate_text is True

    def test_truncate_text_within_limit(self, base_config):
        """Test that text within limit is not truncated."""
        handler = AudioHandler(config=base_config)
        text = "This is a short text."

        result = handler._truncate_text(text)

        assert result == text

    def test_truncate_text_exceeds_limit_with_truncation_enabled(self, base_config):
        """Test text truncation when exceeding limit."""
        base_config['sound']['tts_limits']['max_text_length'] = 50
        handler = AudioHandler(config=base_config)

        # Create text longer than 50 chars with a sentence boundary within 80% of limit
        # The period needs to be at position >= 40 (80% of 50) to be used as boundary
        text = "This is a sentence that ends after position forty. Extra text."

        result = handler._truncate_text(text)

        assert result is not None
        assert len(result) <= 50
        # Should end at sentence boundary if possible (and boundary is at least 80% of limit)
        assert result.endswith('.')

    def test_truncate_text_exceeds_limit_without_truncation(self, base_config):
        """Test that None is returned when truncation is disabled."""
        base_config['sound']['tts_limits']['max_text_length'] = 50
        base_config['sound']['tts_limits']['truncate_text'] = False
        handler = AudioHandler(config=base_config)

        text = "This is a very long sentence that exceeds the limit. More text here."

        result = handler._truncate_text(text)

        assert result is None

    def test_get_audio_provider_from_adapter(self, base_config, mock_adapter_manager):
        """Test getting audio provider from adapter config."""
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        provider = handler._get_audio_provider('test_adapter')

        assert provider == 'openai'

    def test_get_audio_provider_fallback_to_default(self, base_config, mock_adapter_manager):
        """Test fallback to default provider when adapter has none."""
        mock_adapter_manager.get_adapter_config.return_value = {'type': 'passthrough'}

        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        provider = handler._get_audio_provider('test_adapter')

        assert provider == 'openai'

    def test_get_audio_provider_no_adapter_manager(self, base_config):
        """Test using default provider when no adapter manager."""
        handler = AudioHandler(config=base_config)

        provider = handler._get_audio_provider('any_adapter')

        assert provider == 'openai'

    def test_get_audio_format(self, base_config):
        """Test getting audio format from config."""
        handler = AudioHandler(config=base_config)

        audio_format = handler._get_audio_format('openai')

        assert audio_format == 'mp3'

    def test_get_audio_format_default(self, base_config):
        """Test default audio format when not configured."""
        handler = AudioHandler(config=base_config)

        audio_format = handler._get_audio_format('unknown_provider')

        assert audio_format == 'mp3'

    @pytest.mark.asyncio
    async def test_generate_audio_success(self, base_config, mock_adapter_manager, mock_audio_service):
        """Test successful audio generation."""
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        with patch('ai_services.registry.register_all_services'), \
             patch('ai_services.factory.AIServiceFactory') as mock_factory:
            mock_factory.create_service.return_value = mock_audio_service

            audio_data, audio_format = await handler.generate_audio(
                text="Hello world",
                adapter_name='test_adapter',
                tts_voice='alloy',
                language='en'
            )

            assert audio_data == b'fake_audio_data'
            assert audio_format == 'mp3'
            mock_audio_service.text_to_speech.assert_called_once_with(
                text="Hello world",
                voice='alloy',
                format=None
            )

    @pytest.mark.asyncio
    async def test_generate_audio_text_truncated(self, base_config, mock_adapter_manager, mock_audio_service):
        """Test audio generation with text truncation."""
        base_config['sound']['tts_limits']['max_text_length'] = 20
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        with patch('ai_services.registry.register_all_services'), \
             patch('ai_services.factory.AIServiceFactory') as mock_factory:
            mock_factory.create_service.return_value = mock_audio_service

            audio_data, audio_format = await handler.generate_audio(
                text="This is a much longer text that will be truncated.",
                adapter_name='test_adapter'
            )

            assert audio_data is not None
            # Verify truncated text was used
            call_args = mock_audio_service.text_to_speech.call_args
            assert len(call_args[1]['text']) <= 20

    @pytest.mark.asyncio
    async def test_generate_audio_exceeds_size_limit(
        self, base_config, mock_adapter_manager, mock_audio_service
    ):
        """Test that None is returned when audio exceeds size limit."""
        base_config['sound']['tts_limits']['max_audio_size_mb'] = 0.000001  # Very small limit
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        # Audio data is 15 bytes, which exceeds the tiny limit
        with patch('ai_services.registry.register_all_services'), \
             patch('ai_services.factory.AIServiceFactory') as mock_factory:
            mock_factory.create_service.return_value = mock_audio_service

            audio_data, audio_format = await handler.generate_audio(
                text="Hello",
                adapter_name='test_adapter'
            )

            assert audio_data is None
            assert audio_format is None

    @pytest.mark.asyncio
    async def test_generate_audio_no_provider(self, base_config):
        """Test that None is returned when no provider configured."""
        base_config['sound']['provider'] = None
        handler = AudioHandler(config=base_config)

        audio_data, audio_format = await handler.generate_audio(
            text="Hello",
            adapter_name='test_adapter'
        )

        assert audio_data is None
        assert audio_format is None

    @pytest.mark.asyncio
    async def test_generate_audio_service_creation_fails(
        self, base_config, mock_adapter_manager
    ):
        """Test handling when audio service creation fails."""
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        with patch('ai_services.registry.register_all_services'), \
             patch('ai_services.factory.AIServiceFactory') as mock_factory:
            mock_factory.create_service.return_value = None

            audio_data, audio_format = await handler.generate_audio(
                text="Hello",
                adapter_name='test_adapter'
            )

            assert audio_data is None
            assert audio_format is None

    @pytest.mark.asyncio
    async def test_generate_audio_exception_handled(
        self, base_config, mock_adapter_manager, mock_audio_service
    ):
        """Test that exceptions are handled gracefully."""
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )
        mock_audio_service.text_to_speech.side_effect = Exception("TTS error")

        with patch('ai_services.registry.register_all_services'), \
             patch('ai_services.factory.AIServiceFactory') as mock_factory:
            mock_factory.create_service.return_value = mock_audio_service

            audio_data, audio_format = await handler.generate_audio(
                text="Hello",
                adapter_name='test_adapter'
            )

            assert audio_data is None
            assert audio_format is None

    @pytest.mark.asyncio
    async def test_audio_service_caching(self, base_config, mock_adapter_manager, mock_audio_service):
        """Test that audio services are cached."""
        handler = AudioHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        with patch('ai_services.registry.register_all_services'), \
             patch('ai_services.factory.AIServiceFactory') as mock_factory:
            mock_factory.create_service.return_value = mock_audio_service

            # First call
            await handler._get_audio_service('openai')
            # Second call should use cache
            await handler._get_audio_service('openai')

            # Factory should only be called once
            assert mock_factory.create_service.call_count == 1
