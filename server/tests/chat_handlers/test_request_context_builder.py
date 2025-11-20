"""
Tests for RequestContextBuilder.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock
from bson import ObjectId

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.chat_handlers.request_context_builder import RequestContextBuilder


class TestRequestContextBuilder:
    """Test suite for RequestContextBuilder."""

    def test_initialization(self, base_config, mock_adapter_manager):
        """Test builder initialization."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        assert builder.config == base_config
        assert builder.adapter_manager == mock_adapter_manager

    def test_get_adapter_config(self, base_config, mock_adapter_manager):
        """Test getting adapter configuration."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        config = builder.get_adapter_config('test_adapter')

        assert config['type'] == 'passthrough'
        assert config['inference_provider'] == 'openai'

    def test_get_adapter_config_no_manager(self, base_config):
        """Test getting adapter config without manager returns empty dict."""
        builder = RequestContextBuilder(config=base_config)

        config = builder.get_adapter_config('test_adapter')

        assert config == {}

    def test_get_adapter_config_no_adapter(self, base_config, mock_adapter_manager):
        """Test getting config for non-existent adapter."""
        mock_adapter_manager.get_adapter_config.return_value = None

        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        config = builder.get_adapter_config('unknown_adapter')

        assert config == {}

    def test_get_inference_provider(self, base_config, mock_adapter_manager):
        """Test getting inference provider from adapter."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        provider = builder.get_inference_provider('test_adapter')

        assert provider == 'openai'

    def test_get_inference_provider_none(self, base_config, mock_adapter_manager):
        """Test getting inference provider when not set."""
        mock_adapter_manager.get_adapter_config.return_value = {'type': 'passthrough'}

        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        provider = builder.get_inference_provider('test_adapter')

        assert provider is None

    def test_get_timezone(self, base_config, mock_adapter_manager):
        """Test getting timezone from adapter config."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        timezone = builder.get_timezone('test_adapter')

        assert timezone == 'America/New_York'

    def test_get_timezone_none(self, base_config, mock_adapter_manager):
        """Test getting timezone when not configured."""
        mock_adapter_manager.get_adapter_config.return_value = {'type': 'passthrough'}

        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        timezone = builder.get_timezone('test_adapter')

        assert timezone is None

    def test_build_context_basic(self, base_config, mock_adapter_manager):
        """Test building context with basic parameters."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        context = builder.build_context(
            message="Hello, world!",
            adapter_name="test_adapter",
            context_messages=[]
        )

        assert context.message == "Hello, world!"
        assert context.adapter_name == "test_adapter"
        assert context.context_messages == []
        assert context.inference_provider == 'openai'
        assert context.timezone == 'America/New_York'

    def test_build_context_with_all_parameters(self, base_config, mock_adapter_manager):
        """Test building context with all parameters."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )
        system_prompt_id = ObjectId()
        context_messages = [
            {'role': 'user', 'content': 'Previous message'},
            {'role': 'assistant', 'content': 'Previous response'}
        ]

        context = builder.build_context(
            message="Current message",
            adapter_name="test_adapter",
            context_messages=context_messages,
            system_prompt_id=system_prompt_id,
            user_id="user123",
            session_id="session456",
            api_key="key789",
            file_ids=["file1", "file2"],
            audio_input="base64_audio",
            audio_format="wav",
            language="en",
            return_audio=True,
            tts_voice="alloy",
            source_language="en",
            target_language="es"
        )

        assert context.message == "Current message"
        assert context.adapter_name == "test_adapter"
        assert context.context_messages == context_messages
        assert context.system_prompt_id == str(system_prompt_id)
        assert context.user_id == "user123"
        assert context.session_id == "session456"
        assert context.api_key == "key789"
        assert context.file_ids == ["file1", "file2"]
        assert context.audio_input == "base64_audio"
        assert context.audio_format == "wav"
        assert context.language == "en"
        assert context.return_audio is True
        assert context.tts_voice == "alloy"
        assert context.source_language == "en"
        assert context.target_language == "es"

    def test_build_context_without_system_prompt_id(self, base_config, mock_adapter_manager):
        """Test building context without system prompt ID."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        context = builder.build_context(
            message="Test",
            adapter_name="test_adapter",
            context_messages=[],
            system_prompt_id=None
        )

        assert context.system_prompt_id is None

    def test_build_context_empty_file_ids(self, base_config, mock_adapter_manager):
        """Test building context with empty file IDs defaults to empty list."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        context = builder.build_context(
            message="Test",
            adapter_name="test_adapter",
            context_messages=[],
            file_ids=None
        )

        assert context.file_ids == []

    def test_build_context_without_adapter_manager(self, base_config):
        """Test building context without adapter manager."""
        builder = RequestContextBuilder(config=base_config)

        context = builder.build_context(
            message="Test",
            adapter_name="test_adapter",
            context_messages=[]
        )

        # Should not have adapter-specific settings
        assert context.inference_provider is None
        assert context.timezone is None
