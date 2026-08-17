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


class TestAllowedImageModels:
    """Tests for runtime model override via allowed_image_models (image_generation adapters)."""

    def _builder_with_allowed_image_models(self, base_config, allowed_image_models):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'image_generation',
            'image_provider': 'gemini',
            'config': {},
            'allowed_image_models': allowed_image_models,
        }
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def test_valid_image_model_overrides_provider_and_params(self, base_config):
        """A model name present in allowed_image_models sets runtime_provider/model and passes
        through non-name/provider/model keys as runtime_image_param_overrides."""
        allowed = [{
            'name': 'gpt-image-2', 'provider': 'openai', 'model': 'gpt-image-2',
            'size': '1024x1024', 'quality': 'auto',
        }]
        builder = self._builder_with_allowed_image_models(base_config, allowed)

        context = builder.build_context(
            message="draw a cat",
            adapter_name="image-generator",
            context_messages=[],
            requested_model="gpt-image-2",
        )

        assert context.runtime_provider == 'openai'
        assert context.runtime_model_name == 'gpt-image-2'
        assert context.runtime_image_param_overrides == {'size': '1024x1024', 'quality': 'auto'}
        assert context.runtime_param_overrides is None

    def test_unknown_image_model_raises(self, base_config):
        """A model name not in allowed_image_models raises ValueError."""
        allowed = [{'name': 'gpt-image-2', 'provider': 'openai', 'model': 'gpt-image-2'}]
        builder = self._builder_with_allowed_image_models(base_config, allowed)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="draw a cat",
                adapter_name="image-generator",
                context_messages=[],
                requested_model="unknown-image-model",
            )

    def test_no_allowed_image_models_ignores_requested_model(self, base_config):
        """When the adapter defines no allowed_image_models, any requested_model is ignored."""
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'image_generation',
            'image_provider': 'gemini',
            'config': {},
        }
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="draw a cat",
            adapter_name="image-generator",
            context_messages=[],
            requested_model="anything",
        )

        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_image_param_overrides is None


class TestAllowedImageModelsViaSkillRouting:
    """Tests for allowed_image_models resolution after skill routing (not before)."""

    def _make_builder(self, base_config, caller_cfg, image_cfg, skill_adapter_name='image-generator'):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            image_cfg if name == skill_adapter_name else caller_cfg
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def _configs(self):
        caller_cfg = {
            'type': 'multimodal',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': ['Image'], 'auto_routable_skills': ['Image']},
            'allowed_models': [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}],
        }
        image_cfg = {
            'type': 'image_generation',
            'image_provider': 'gemini',
            'config': {},
            'allowed_image_models': [
                {'name': 'gpt-image-2', 'provider': 'openai', 'model': 'gpt-image-2', 'size': '1024x1024'},
            ],
        }
        return caller_cfg, image_cfg

    def test_explicit_image_skill_with_valid_image_model(self, base_config):
        """Explicit Image skill + a matching allowed_image_models name resolves cleanly,
        even though the calling adapter's own allowed_models doesn't contain it."""
        caller_cfg, image_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, image_cfg)

        context = builder.build_context(
            message="draw a cat",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="gpt-image-2",
            skill="Image",
            skill_auto_detected=False,
        )

        assert context.adapter_name == 'image-generator'
        assert context.runtime_provider == 'openai'
        assert context.runtime_model_name == 'gpt-image-2'
        assert context.runtime_image_param_overrides == {'size': '1024x1024'}

    def test_explicit_image_skill_invalid_model_raises(self, base_config):
        """Explicit Image skill + an unrecognized image model name still raises."""
        caller_cfg, image_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, image_cfg)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="draw a cat",
                adapter_name="test_adapter",
                context_messages=[],
                requested_model="unknown-image-model",
                skill="Image",
                skill_auto_detected=False,
            )

    def test_auto_detected_image_skill_ignores_callers_llm_model(self, base_config):
        """Auto-detected Image skill carries along the calling adapter's previously
        selected LLM model name (e.g. 'claude'), which has no meaning for the image
        adapter — this must be silently ignored, not raise."""
        caller_cfg, image_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, image_cfg)

        context = builder.build_context(
            message="draw a cat",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="claude",
            skill="Image",
            skill_auto_detected=True,
        )

        assert context.adapter_name == 'image-generator'
        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_image_param_overrides is None


class TestAllowedVideoModels:
    """Tests for runtime model override via allowed_video_models (video_generation adapters)."""

    def _builder_with_allowed_video_models(self, base_config, allowed_video_models):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'video_generation',
            'video_provider': 'gemini',
            'config': {},
            'allowed_video_models': allowed_video_models,
        }
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def test_valid_video_model_overrides_provider_and_params(self, base_config):
        """A model name present in allowed_video_models sets runtime_provider/model and passes
        through non-name/provider/model keys as runtime_video_param_overrides."""
        allowed = [{
            'name': 'xai-video', 'provider': 'xai', 'model': 'grok-imagine-video',
            'aspect_ratio': '16:9', 'resolution': '720p',
        }]
        builder = self._builder_with_allowed_video_models(base_config, allowed)

        context = builder.build_context(
            message="a video of a cat",
            adapter_name="video-generator",
            context_messages=[],
            requested_model="xai-video",
        )

        assert context.runtime_provider == 'xai'
        assert context.runtime_model_name == 'grok-imagine-video'
        assert context.runtime_video_param_overrides == {'aspect_ratio': '16:9', 'resolution': '720p'}
        assert context.runtime_param_overrides is None

    def test_unknown_video_model_raises(self, base_config):
        """A model name not in allowed_video_models raises ValueError."""
        allowed = [{'name': 'xai-video', 'provider': 'xai', 'model': 'grok-imagine-video'}]
        builder = self._builder_with_allowed_video_models(base_config, allowed)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="a video of a cat",
                adapter_name="video-generator",
                context_messages=[],
                requested_model="unknown-video-model",
            )

    def test_no_allowed_video_models_ignores_requested_model(self, base_config):
        """When the adapter defines no allowed_video_models, any requested_model is ignored."""
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'video_generation',
            'video_provider': 'gemini',
            'config': {},
        }
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="a video of a cat",
            adapter_name="video-generator",
            context_messages=[],
            requested_model="anything",
        )

        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_video_param_overrides is None


class TestAllowedVideoModelsViaSkillRouting:
    """Tests for allowed_video_models resolution after skill routing (not before)."""

    def _make_builder(self, base_config, caller_cfg, video_cfg, skill_adapter_name='video-generator'):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            video_cfg if name == skill_adapter_name else caller_cfg
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def _configs(self):
        caller_cfg = {
            'type': 'multimodal',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': ['Video'], 'auto_routable_skills': ['Video']},
            'allowed_models': [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}],
        }
        video_cfg = {
            'type': 'video_generation',
            'video_provider': 'gemini',
            'config': {},
            'allowed_video_models': [
                {'name': 'xai-video', 'provider': 'xai', 'model': 'grok-imagine-video', 'aspect_ratio': '16:9'},
            ],
        }
        return caller_cfg, video_cfg

    def test_explicit_video_skill_with_valid_video_model(self, base_config):
        """Explicit Video skill + a matching allowed_video_models name resolves cleanly,
        even though the calling adapter's own allowed_models doesn't contain it."""
        caller_cfg, video_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, video_cfg)

        context = builder.build_context(
            message="make a video of a cat",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="xai-video",
            skill="Video",
            skill_auto_detected=False,
        )

        assert context.adapter_name == 'video-generator'
        assert context.runtime_provider == 'xai'
        assert context.runtime_model_name == 'grok-imagine-video'
        assert context.runtime_video_param_overrides == {'aspect_ratio': '16:9'}

    def test_explicit_video_skill_invalid_model_raises(self, base_config):
        """Explicit Video skill + an unrecognized video model name still raises."""
        caller_cfg, video_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, video_cfg)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="make a video of a cat",
                adapter_name="test_adapter",
                context_messages=[],
                requested_model="unknown-video-model",
                skill="Video",
                skill_auto_detected=False,
            )

    def test_auto_detected_video_skill_ignores_callers_llm_model(self, base_config):
        """Auto-detected Video skill carries along the calling adapter's previously
        selected LLM model name (e.g. 'claude'), which has no meaning for the video
        adapter — this must be silently ignored, not raise."""
        caller_cfg, video_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, video_cfg)

        context = builder.build_context(
            message="make a video of a cat",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="claude",
            skill="Video",
            skill_auto_detected=True,
        )

        assert context.adapter_name == 'video-generator'
        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_video_param_overrides is None


class TestAllowedAudioModels:
    """Tests for runtime model override via allowed_audio_models (audio_generation adapters)."""

    def _builder_with_allowed_audio_models(self, base_config, allowed_audio_models):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'audio_generation',
            'tts_provider': 'gemini',
            'config': {},
            'allowed_audio_models': allowed_audio_models,
        }
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def test_valid_audio_model_overrides_provider_and_params(self, base_config):
        """A model name present in allowed_audio_models sets runtime_provider/model and passes
        through non-name/provider/model keys as runtime_audio_param_overrides."""
        allowed = [{
            'name': 'openai-tts', 'provider': 'openai', 'model': 'gpt-4o-mini-tts',
            'voice': 'coral',
        }]
        builder = self._builder_with_allowed_audio_models(base_config, allowed)

        context = builder.build_context(
            message="read this out loud",
            adapter_name="audio-generator",
            context_messages=[],
            requested_model="openai-tts",
        )

        assert context.runtime_provider == 'openai'
        assert context.runtime_model_name == 'gpt-4o-mini-tts'
        assert context.runtime_audio_param_overrides == {'voice': 'coral'}
        assert context.runtime_param_overrides is None

    def test_unknown_audio_model_raises(self, base_config):
        """A model name not in allowed_audio_models raises ValueError."""
        allowed = [{'name': 'openai-tts', 'provider': 'openai', 'model': 'gpt-4o-mini-tts'}]
        builder = self._builder_with_allowed_audio_models(base_config, allowed)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="read this out loud",
                adapter_name="audio-generator",
                context_messages=[],
                requested_model="unknown-audio-model",
            )

    def test_no_allowed_audio_models_ignores_requested_model(self, base_config):
        """When the adapter defines no allowed_audio_models, any requested_model is ignored."""
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'audio_generation',
            'tts_provider': 'gemini',
            'config': {},
        }
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="read this out loud",
            adapter_name="audio-generator",
            context_messages=[],
            requested_model="anything",
        )

        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_audio_param_overrides is None


class TestAllowedAudioModelsViaSkillRouting:
    """Tests for allowed_audio_models resolution after skill routing (not before)."""

    def _make_builder(self, base_config, caller_cfg, audio_cfg, skill_adapter_name='audio-generator'):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            audio_cfg if name == skill_adapter_name else caller_cfg
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def _configs(self):
        caller_cfg = {
            'type': 'multimodal',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': ['Audio'], 'auto_routable_skills': ['Audio']},
            'allowed_models': [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}],
        }
        audio_cfg = {
            'type': 'audio_generation',
            'tts_provider': 'gemini',
            'config': {},
            'allowed_audio_models': [
                {'name': 'openai-tts', 'provider': 'openai', 'model': 'gpt-4o-mini-tts', 'voice': 'coral'},
            ],
        }
        return caller_cfg, audio_cfg

    def test_explicit_audio_skill_with_valid_audio_model(self, base_config):
        """Explicit Audio skill + a matching allowed_audio_models name resolves cleanly,
        even though the calling adapter's own allowed_models doesn't contain it."""
        caller_cfg, audio_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, audio_cfg)

        context = builder.build_context(
            message="read this out loud",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="openai-tts",
            skill="Audio",
            skill_auto_detected=False,
        )

        assert context.adapter_name == 'audio-generator'
        assert context.runtime_provider == 'openai'
        assert context.runtime_model_name == 'gpt-4o-mini-tts'
        assert context.runtime_audio_param_overrides == {'voice': 'coral'}

    def test_explicit_audio_skill_invalid_model_raises(self, base_config):
        """Explicit Audio skill + an unrecognized audio model name still raises."""
        caller_cfg, audio_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, audio_cfg)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="read this out loud",
                adapter_name="test_adapter",
                context_messages=[],
                requested_model="unknown-audio-model",
                skill="Audio",
                skill_auto_detected=False,
            )

    def test_auto_detected_audio_skill_ignores_callers_llm_model(self, base_config):
        """Auto-detected Audio skill carries along the calling adapter's previously
        selected LLM model name (e.g. 'claude'), which has no meaning for the audio
        adapter — this must be silently ignored, not raise."""
        caller_cfg, audio_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, audio_cfg)

        context = builder.build_context(
            message="read this out loud",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="claude",
            skill="Audio",
            skill_auto_detected=True,
        )

        assert context.adapter_name == 'audio-generator'
        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_audio_param_overrides is None


class TestAllowedSearchProviders:
    """Tests for runtime search-backend override via allowed_search_providers (web-search adapters)."""

    def _builder_with_allowed_search_providers(self, base_config, allowed_search_providers):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'web-search',
            'inference_provider': 'anthropic',
            'model': 'claude-haiku-4-5-20251001',
            'config': {},
            'web_search': {'provider': 'duckduckgo', 'result_count': 5},
            'allowed_search_providers': allowed_search_providers,
        }
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def test_valid_search_provider_overrides_backend(self, base_config):
        """A name present in allowed_search_providers sets runtime_search_provider_overrides
        and leaves the LLM synthesis path (runtime_provider/model) untouched."""
        allowed = [{'name': 'brave', 'provider': 'brave', 'api_key': 'brave-key', 'result_count': 5}]
        builder = self._builder_with_allowed_search_providers(base_config, allowed)

        context = builder.build_context(
            message="latest news",
            adapter_name="web-search-duckduckgo",
            context_messages=[],
            requested_model="brave",
        )

        assert context.runtime_search_provider_overrides == {
            'provider': 'brave', 'api_key': 'brave-key', 'result_count': 5,
        }
        assert context.runtime_provider is None
        assert context.runtime_model_name is None
        assert context.runtime_param_overrides is None

    def test_unknown_search_provider_raises(self, base_config):
        """A name not in allowed_search_providers raises ValueError."""
        allowed = [{'name': 'brave', 'provider': 'brave'}]
        builder = self._builder_with_allowed_search_providers(base_config, allowed)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="latest news",
                adapter_name="web-search-duckduckgo",
                context_messages=[],
                requested_model="unknown-backend",
            )

    def test_adapter_name_echo_treated_as_no_override(self, base_config):
        """An OpenAI-compatible client echoing the adapter name as 'model' is treated
        as no override, not an invalid search-provider name."""
        allowed = [{'name': 'brave', 'provider': 'brave'}]
        builder = self._builder_with_allowed_search_providers(base_config, allowed)

        context = builder.build_context(
            message="latest news",
            adapter_name="web-search-duckduckgo",
            context_messages=[],
            requested_model="web-search-duckduckgo",
        )

        assert context.runtime_search_provider_overrides is None

    def test_no_allowed_search_providers_ignores_requested_model(self, base_config):
        """When the adapter defines no allowed_search_providers, any requested_model is ignored."""
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.return_value = {
            'type': 'web-search',
            'inference_provider': 'anthropic',
            'model': 'claude-haiku-4-5-20251001',
            'config': {},
            'web_search': {'provider': 'duckduckgo', 'result_count': 5},
        }
        builder = RequestContextBuilder(config=base_config, adapter_manager=manager)

        context = builder.build_context(
            message="latest news",
            adapter_name="web-search-duckduckgo",
            context_messages=[],
            requested_model="anything",
        )

        assert context.runtime_search_provider_overrides is None


class TestAllowedSearchProvidersViaSkillRouting:
    """Tests for allowed_search_providers resolution after skill routing (not before)."""

    def _make_builder(self, base_config, caller_cfg, search_cfg, skill_adapter_name='web-search-duckduckgo'):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            search_cfg if name == skill_adapter_name else caller_cfg
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def _configs(self):
        caller_cfg = {
            'type': 'multimodal',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {
                'available_skills': ['web-search-duckduckgo'],
                'auto_routable_skills': ['web-search-duckduckgo'],
            },
            'allowed_models': [{'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'}],
        }
        search_cfg = {
            'type': 'web-search',
            'inference_provider': 'anthropic',
            'model': 'claude-haiku-4-5-20251001',
            'config': {},
            'web_search': {'provider': 'duckduckgo', 'result_count': 5},
            'allowed_search_providers': [
                {'name': 'brave', 'provider': 'brave', 'api_key': 'brave-key'},
            ],
        }
        return caller_cfg, search_cfg

    def test_explicit_skill_with_valid_search_provider(self, base_config):
        """Explicit skill + a matching allowed_search_providers name resolves cleanly,
        even though the calling adapter's own allowed_models doesn't contain it."""
        caller_cfg, search_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, search_cfg)

        context = builder.build_context(
            message="latest news",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="brave",
            skill="web-search-duckduckgo",
            skill_auto_detected=False,
        )

        assert context.adapter_name == 'web-search-duckduckgo'
        assert context.runtime_search_provider_overrides == {'provider': 'brave', 'api_key': 'brave-key'}

    def test_explicit_skill_preserves_skill_adapters_synthesis_provider(self, base_config):
        """Routing through skill= must use the skill (web-search) adapter's own fixed
        inference_provider for synthesis, not the calling adapter's."""
        caller_cfg, search_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, search_cfg)

        context = builder.build_context(
            message="latest news",
            adapter_name="test_adapter",
            context_messages=[],
            skill="web-search-duckduckgo",
            skill_auto_detected=False,
        )

        assert context.inference_provider == 'anthropic'

    def test_explicit_skill_invalid_provider_raises(self, base_config):
        """Explicit skill + an unrecognized search-provider name still raises."""
        caller_cfg, search_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, search_cfg)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="latest news",
                adapter_name="test_adapter",
                context_messages=[],
                requested_model="unknown-backend",
                skill="web-search-duckduckgo",
                skill_auto_detected=False,
            )

    def test_auto_detected_skill_ignores_callers_llm_model(self, base_config):
        """Auto-detected skill carries along the calling adapter's previously selected
        LLM model name (e.g. 'claude'), which has no meaning for the search adapter —
        this must be silently ignored, not raise."""
        caller_cfg, search_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, search_cfg)

        context = builder.build_context(
            message="latest news",
            adapter_name="test_adapter",
            context_messages=[],
            requested_model="claude",
            skill="web-search-duckduckgo",
            skill_auto_detected=True,
        )

        assert context.adapter_name == 'web-search-duckduckgo'
        assert context.runtime_search_provider_overrides is None


class TestAllowedModelsOnSkillWithOwnLLM:
    """Tests for allowed_models resolution on a skill that has its own fixed LLM
    (e.g. web-search.yaml's passthrough adapter with capabilities.web_search: true) —
    the model override must validate against the SKILL adapter's own allowed_models,
    not the calling adapter's, once the skill has its own inference_provider."""

    def _make_builder(self, base_config, caller_cfg, skill_cfg, skill_adapter_name='web-search-chat'):
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            skill_cfg if name == skill_adapter_name else caller_cfg
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def _configs(self):
        caller_cfg = {
            'type': 'multimodal',
            'inference_provider': 'ollama_cloud',
            'config': {},
            'capabilities': {'available_skills': ['web-search'], 'auto_routable_skills': ['web-search']},
            'allowed_models': [{'name': 'gemini', 'provider': 'gemini', 'model': 'gemini-3.6-flash'}],
        }
        skill_cfg = {
            'type': 'passthrough',
            'inference_provider': 'openai',
            'model': 'gpt-5.6',
            'config': {},
            'capabilities': {'web_search': True},
            'allowed_models': [
                {'name': 'gemini-search', 'provider': 'gemini', 'model': 'gemini-3.6-flash'},
                {'name': 'openai-search', 'provider': 'openai', 'model': 'gpt-5.6'},
            ],
        }
        return caller_cfg, skill_cfg

    def test_explicit_skill_with_own_valid_model_resolves(self, base_config):
        """Reproduces the reported bug: selecting a model from the skill's OWN
        allowed_models (not the caller's) must succeed, not raise ValueError."""
        caller_cfg, skill_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, skill_cfg)

        context = builder.build_context(
            message="what's in the news today",
            adapter_name="simple-chat-with-files",
            context_messages=[],
            requested_model="gemini-search",
            skill="web-search",
            skill_auto_detected=False,
        )

        assert context.adapter_name == 'web-search-chat'
        assert context.inference_provider == 'openai'
        assert context.runtime_provider == 'gemini'
        assert context.runtime_model_name == 'gemini-3.6-flash'

    def test_explicit_skill_invalid_model_raises(self, base_config):
        """A model name that's not in the SKILL's allowed_models still raises, even
        if it happens to match the calling adapter's own allowed_models."""
        caller_cfg, skill_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, skill_cfg)

        with pytest.raises(ValueError, match="not allowed"):
            builder.build_context(
                message="what's in the news today",
                adapter_name="simple-chat-with-files",
                context_messages=[],
                requested_model="gemini",  # valid for the CALLER, not for web-search-chat
                skill="web-search",
                skill_auto_detected=False,
            )

    def test_auto_detected_skill_ignores_callers_llm_model(self, base_config):
        """Auto-detected skill carries along the calling adapter's previously
        selected model name, which has no meaning for the skill's own LLM — must be
        silently ignored, not raise."""
        caller_cfg, skill_cfg = self._configs()
        builder = self._make_builder(base_config, caller_cfg, skill_cfg)

        context = builder.build_context(
            message="what's in the news today",
            adapter_name="simple-chat-with-files",
            context_messages=[],
            requested_model="gemini",
            skill="web-search",
            skill_auto_detected=True,
        )

        assert context.adapter_name == 'web-search-chat'
        assert context.inference_provider == 'openai'
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

    def test_auto_detected_skill_allowed_via_auto_routable(self, base_config):
        """An auto-detected skill passes when it's in auto_routable_skills even if
        available_skills is empty (users can't invoke it, but ORBIT may route to it)."""
        adapter_cfg = {
            'type': 'retriever',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': [], 'auto_routable_skills': ['image-generation']},
        }
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='image-generator')

        context = builder.build_context(
            message="a sunset over mountains",
            adapter_name="test_adapter",
            context_messages=[],
            skill="image-generation",
            skill_auto_detected=True,
        )
        assert context.adapter_name == 'image-generator'
        assert context.requested_skill == 'image-generation'

    def test_explicit_skill_not_allowed_by_auto_routable_only(self, base_config):
        """A skill only in auto_routable_skills cannot be invoked EXPLICITLY by a user."""
        adapter_cfg = {
            'type': 'retriever',
            'inference_provider': 'openai',
            'config': {},
            'capabilities': {'available_skills': [], 'auto_routable_skills': ['image-generation']},
        }
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='image-generator')

        with pytest.raises(ValueError, match="not available"):
            builder.build_context(
                message="test",
                adapter_name="test_adapter",
                context_messages=[],
                skill="image-generation",
                skill_auto_detected=False,
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


class TestSkillRoutingWithCompositeAdapter:
    """Tests that skill routing works identically when the calling adapter is a
    composite retriever (adapter: "composite"), e.g. composite-customer-360 in
    config/adapters/composite.yaml. Skill routing is resolved entirely in
    RequestContextBuilder before the pipeline picks a retriever, so it must
    behave the same regardless of adapter type."""

    def _make_builder(self, base_config, adapter_config, skill_adapter_name=None):
        from unittest.mock import MagicMock

        manager = MagicMock()
        manager.get_adapter_config.side_effect = lambda name: (
            adapter_config if name in ("composite_adapter", skill_adapter_name) else None
        )
        manager.get_skill_adapter.return_value = skill_adapter_name
        return RequestContextBuilder(config=base_config, adapter_manager=manager)

    def _composite_adapter_cfg(self, available_skills=None, auto_routable_skills=None):
        return {
            'type': 'retriever',
            'adapter': 'composite',
            'inference_provider': 'openai',
            'config': {
                'child_adapters': ['intent-sql-sqlite-billing', 'intent-http-sla-metrics'],
            },
            'capabilities': {
                'retrieval_behavior': 'always',
                'supports_threading': True,
                'available_skills': available_skills or [],
                'auto_routable_skills': auto_routable_skills or [],
            },
        }

    def test_skill_routes_to_skill_adapter_from_composite_caller(self, base_config):
        """A composite adapter's allowed skill swaps adapter_name to the skill adapter,
        exactly like an intent/passthrough/multimodal caller."""
        adapter_cfg = self._composite_adapter_cfg(available_skills=['web-search'])
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='web-search-chat')

        context = builder.build_context(
            message="what's the latest on this outage",
            adapter_name="composite_adapter",
            context_messages=[],
            skill="web-search",
        )

        assert context.adapter_name == 'web-search-chat'
        assert context.original_adapter_name == 'composite_adapter'
        assert context.requested_skill == 'web-search'

    def test_skill_not_in_allowlist_raises_for_composite_caller(self, base_config):
        """Composite adapters are subject to the same available_skills allowlist check."""
        adapter_cfg = self._composite_adapter_cfg(available_skills=[])
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='web-search-chat')

        with pytest.raises(ValueError, match="not available"):
            builder.build_context(
                message="test",
                adapter_name="composite_adapter",
                context_messages=[],
                skill="web-search",
            )

    def test_auto_detected_skill_allowed_via_auto_routable_for_composite_caller(self, base_config):
        """Auto-routable skills work for composite callers the same as any other adapter type."""
        adapter_cfg = self._composite_adapter_cfg(auto_routable_skills=['web-search'])
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='web-search-chat')

        context = builder.build_context(
            message="search the web for this",
            adapter_name="composite_adapter",
            context_messages=[],
            skill="web-search",
            skill_auto_detected=True,
        )

        assert context.adapter_name == 'web-search-chat'
        assert context.requested_skill == 'web-search'

    def test_no_skill_leaves_composite_adapter_unchanged(self, base_config):
        """Omitting skill= on a composite adapter leaves adapter_name untouched, so the
        composite retriever runs normally (child-adapter fan-out unaffected)."""
        adapter_cfg = self._composite_adapter_cfg(available_skills=['web-search'])
        builder = self._make_builder(base_config, adapter_cfg, skill_adapter_name='web-search-chat')

        context = builder.build_context(
            message="hello",
            adapter_name="composite_adapter",
            context_messages=[],
        )

        assert context.adapter_name == 'composite_adapter'
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
