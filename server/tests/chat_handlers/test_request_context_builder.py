"""
Tests for RequestContextBuilder.
"""

import pytest
import sys
import os
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


class TestAllowedModels:
    """Tests for runtime model override via allowed_models."""

    def _builder_with_allowed_models(self, base_config, allowed_models):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'passthrough',
            'inference_provider': 'openai',
            'config': {},
            'allowed_models': allowed_models,
        }
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def test_valid_model_overrides_provider(self, base_config):
        """A model name present in allowed_models sets runtime_provider and runtime_model_name."""
        allowed = [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}]
        builder = self._builder_with_allowed_models(base_config, allowed)

        context = builder.build_context(
            message="hello",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="claude",
        )

        assert context.runtime_provider == 'anthropic'
        assert context.runtime_model_name == 'claude-sonnet-4-5'

    def test_model_echo_from_openai_client_uses_adapter_default(self, base_config):
        """When requested_model equals the adapter name, treat it as no override.

        OpenAI-compatible clients (e.g. LiteLLM) echo the adapter name back as the
        model field. This narrow case is ignored so those clients work out of the box
        without disabling validation for genuinely unknown model names.
        """
        allowed = [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}]
        builder = self._builder_with_allowed_models(base_config, allowed)

        context = builder.build_context(
            message="hello",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="test_adapter",  # echoes adapter name — treated as no override
        )

        assert context.runtime_provider is None
        assert context.runtime_model_name is None

    def test_unknown_model_not_in_allowed_models_raises(self, base_config):
        """A model name not in allowed_models (and not an adapter-name echo) raises ValueError."""
        allowed = [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}]
        builder = self._builder_with_allowed_models(base_config, allowed)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="hello",
                adapter_name="test_adapter",
                context_messages=[],
                requested_model="gpt-99",  # unknown, not an adapter-name echo
            )

    def test_no_allowed_models_ignores_requested_model(self, base_config):
        """When adapter defines no allowed_models list, any requested_model is silently ignored."""
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'passthrough',
            'inference_provider': 'openai',
            'config': {},
            # no allowed_models key
        }
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="hello",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="anything",
        )

        assert context.runtime_provider is None
        assert context.runtime_model_name is None


class TestSkillRouting:
    """Tests for skill invocation via RequestContextBuilder."""

    def _make_builder(self, base_config, adapter_config, skill_adapter_name=None):
        """Helper: build a RequestContextBuilder with controllable adapter mocks."""
        from unittest.mock import MagicMock

        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            adapter_config if name in ("test_adapter", skill_adapter_name) else None
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def test_skill_routes_to_skill_adapter(self, base_config):
        """When skill is allowed, adapter_name is swapped to the skill adapter."""
        adapter_cfg = {
            'type': 'retriever',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': ['image-generation']},
        }
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='image-generator')

        context = builder.build_context(
            message="a sunset over mountains",
            adapter_name="test_adapter",
            context_messages=[],
            skill="image-generation",
        )

        assert context.adapter_name == 'image-generator'
        assert context.original_adapter_name == 'test_adapter'
        assert context.requested_skill == 'image-generation'

    def test_skill_not_in_allowlist_raises(self, base_config):
        """Requesting a skill not in available_skills raises ValueError."""
        adapter_cfg = {
            'type': 'retriever',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': []},
        }
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='image-generator')

        with pytest.raises(ValueError, match="not available"):
            builder.build_context(
                message="test",
                adapter_name="test_adapter",
                context_messages=[],
                skill="image-generation",
            )

    def test_skill_adapter_not_registered_raises(self, base_config):
        """Raises ValueError when no adapter is registered for the skill."""
        adapter_cfg = {
            'type': 'retriever',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': ['image-generation']},
        }
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name=None)

        with pytest.raises(ValueError, match="No adapter is registered"):
            builder.build_context(
                message="test",
                adapter_name="test_adapter",
                context_messages=[],
                skill="image-generation",
            )

    def test_no_skill_leaves_adapter_unchanged(self, base_config):
        """Omitting skill= leaves adapter_name untouched."""
        from unittest.mock import MagicMock

        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'passthrough',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': ['image-generation']},
        }
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="hello",
            adapter_name="test_adapter",
            context_messages=[],
        )

        assert context.adapter_name == 'test_adapter'
        assert context.requested_skill is None
        assert context.original_adapter_name is None


class TestWebSearchCapability:
    """Tests for the web_search capability flag on ProcessingContext."""

    def test_web_search_flag_set_from_skill_adapter(self, base_config):
        """Routing to a skill adapter with web_search: true sets context.web_search."""
        from unittest.mock import MagicMock

        consumer_cfg = {
            'type': 'passthrough',
            'inference_provider': 'gemini',
            'config': {},
            'capabilities': {'available_skills': ['web-search']},
        }
        skill_cfg = {
            'type': 'passthrough',
            'inference_provider': 'gemini',
            'config': {},
            'capabilities': {'web_search': True, 'expose_as_skill': True, 'skill_name': 'web-search'},
        }
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            skill_cfg if name == 'web-search-chat' else consumer_cfg
        )
        manager.get_skill_adapter.return_value = 'web-search-chat'
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="latest news",
            adapter_name="test_adapter",
            context_messages=[],
            skill="web-search",
        )

        assert context.adapter_name == 'web-search-chat'
        assert context.web_search is True

    def test_skill_discards_caller_runtime_model(self, base_config):
        """The caller's runtime model override is dropped when routing to a skill.

        Prevents the calling adapter's selected model (e.g. deepseek) from receiving
        the web_search flag; the skill always uses its own configured provider/model.
        """
        from unittest.mock import MagicMock

        consumer_cfg = {
            'type': 'passthrough',
            'inference_provider': 'ollama_cloud',
            'config': {},
            'allowed_models': [
                {'name': 'deepseek', 'provider': 'deepseek', 'model': 'deepseek-chat'},
            ],
            'capabilities': {'available_skills': ['web-search']},
        }
        skill_cfg = {
            'type': 'passthrough',
            'inference_provider': 'openai',
            'model': 'gpt-5.5',
            'config': {},
            'capabilities': {'web_search': True, 'expose_as_skill': True, 'skill_name': 'web-search'},
        }
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            skill_cfg if name == 'web-search-chat' else consumer_cfg
        )
        manager.get_skill_adapter.return_value = 'web-search-chat'
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="latest news",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="deepseek",
            skill="web-search",
        )

        assert context.adapter_name == 'web-search-chat'
        assert context.inference_provider == 'openai'
        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.web_search is True

    def test_web_search_flag_false_by_default(self, base_config, mock_adapter_manager):
        """Adapters without web_search capability leave context.web_search False."""
        builder = RequestContextBuilder(
            config=base_config,
            adapter_manager=mock_adapter_manager,
        )

        context = builder.build_context(
            message="hello",
            adapter_name="test_adapter",
            context_messages=[],
        )

        assert context.web_search is False
