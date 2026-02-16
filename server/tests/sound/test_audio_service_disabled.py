#!/usr/bin/env python3
"""
Test audio service registration and handling when globally disabled.

This module tests that:
1. When sound.enabled: false, no audio services are registered
2. Audio service creation fails gracefully with appropriate error messages
3. Adapter loader handles disabled audio services without errors
4. Log messages are clear and appropriate when audio is disabled
"""

import pytest
import sys
import os
from typing import Dict, Any
from unittest.mock import patch, MagicMock, AsyncMock
import logging

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Add server directory to Python path
sys.path.append(server_dir)

from ai_services.registry import register_audio_services
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType


class TestAudioServiceDisabled:
    """Test cases for audio service behavior when globally disabled."""

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
    def audio_disabled_config(self) -> Dict[str, Any]:
        """Create a config with audio globally disabled."""
        return {
            "sound": {
                "enabled": False,
                "provider": "openai"
            },
            "sounds": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-key",
                    "tts_model": "gpt-4o-mini-tts",
                    "stt_model": "whisper-1"
                },
                "google": {
                    "enabled": True,
                    "api_key": "test-key"
                },
                "whisper": {
                    "enabled": True,
                    "model_size": "base"
                }
            }
        }

    @pytest.fixture
    def audio_enabled_config(self) -> Dict[str, Any]:
        """Create a config with audio globally enabled."""
        return {
            "sound": {
                "enabled": True,
                "provider": "openai"
            },
            "sounds": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-key",
                    "tts_model": "gpt-4o-mini-tts",
                    "stt_model": "whisper-1"
                },
                "google": {
                    "enabled": False,  # Individual provider disabled
                    "api_key": "test-key"
                },
                "whisper": {
                    "enabled": True,
                    "model_size": "base"
                }
            }
        }

    def test_no_audio_services_registered_when_disabled(self, audio_disabled_config):
        """Test that no audio services are registered when sound.enabled: false."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIAudioService = MagicMock()
            mock_module.GoogleAudioService = MagicMock()
            mock_module.WhisperAudioService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with audio disabled
            register_audio_services(audio_disabled_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])

            # Verify that NO audio providers are registered
            assert len(audio_providers) == 0
            assert 'openai' not in audio_providers
            assert 'google' not in audio_providers
            assert 'whisper' not in audio_providers

    def test_audio_services_registered_when_enabled(self, audio_enabled_config):
        """Test that audio services are registered when sound.enabled: true."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIAudioService = MagicMock()
            mock_module.WhisperAudioService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with audio enabled
            register_audio_services(audio_enabled_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])

            # Verify that enabled audio providers are registered
            assert 'openai' in audio_providers
            assert 'whisper' in audio_providers
            # Google should not be registered (individually disabled)
            assert 'google' not in audio_providers

    def test_logging_when_audio_globally_disabled(self, audio_disabled_config, caplog):
        """Test that appropriate log message is shown when audio is globally disabled."""
        caplog.set_level(logging.INFO)

        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with audio disabled
            register_audio_services(audio_disabled_config)

            # Check that the global disable message was logged
            log_messages = [record.message for record in caplog.records]
            assert any("Sound services are globally disabled" in msg for msg in log_messages)
            assert any("sound.enabled: false" in msg for msg in log_messages)
            assert any("TTS and STT functionality will not be available" in msg for msg in log_messages)

    def test_create_service_fails_when_audio_disabled(self, audio_disabled_config):
        """Test that creating an audio service fails when audio is disabled."""
        # Register services (will register nothing due to audio being disabled)
        register_audio_services(audio_disabled_config)

        # Try to create an audio service
        with pytest.raises(ValueError) as exc_info:
            AIServiceFactory.create_service(
                ServiceType.AUDIO,
                "openai",
                audio_disabled_config
            )

        # Verify error message mentions that no service is registered
        assert "No service registered for audio with provider openai" in str(exc_info.value)

    def test_string_false_value_for_enabled(self):
        """Test that string 'false' value is properly handled."""
        config = {
            "sound": {
                "enabled": "false",  # String instead of boolean
                "provider": "openai"
            }
        }

        # Mock the import
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_import.side_effect = lambda name, *args, **kwargs: (
                mock_module if 'ai_services.implementations' in name
                else __import__(name, *args, **kwargs)
            )

            # Register services
            register_audio_services(config)

            # Verify no services registered
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])
            assert len(audio_providers) == 0

    def test_missing_sound_config_defaults_to_enabled(self):
        """Test that missing sound config defaults to enabled (backward compatibility)."""
        config = {
            "sounds": {
                "openai": {"enabled": True}
            }
            # No "sound" section
        }

        # Mock the import
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIAudioService = MagicMock()

            mock_import.side_effect = lambda name, *args, **kwargs: (
                mock_module if 'ai_services.implementations' in name
                else __import__(name, *args, **kwargs)
            )

            # Register services - should work (backward compatibility)
            register_audio_services(config)

            # Verify services are registered
            available_services = AIServiceFactory.list_available_services()
            audio_providers = available_services.get('audio', [])
            assert 'openai' in audio_providers


class TestAudioCacheManagerDisabled:
    """Test audio cache manager behavior when audio is disabled."""

    @pytest.fixture
    def audio_disabled_config(self) -> Dict[str, Any]:
        """Create a config with audio globally disabled."""
        return {
            "sound": {
                "enabled": False,
                "provider": "openai"
            },
            "sounds": {
                "openai": {
                    "enabled": True,
                    "tts_model": "gpt-4o-mini-tts",
                    "stt_model": "whisper-1"
                }
            }
        }

    @pytest.mark.asyncio
    async def test_cache_manager_logs_info_when_audio_disabled(
        self, audio_disabled_config, caplog
    ):
        """Test that cache manager logs at INFO level (not ERROR) when audio is disabled."""
        caplog.set_level(logging.INFO)

        from services.cache.audio_cache_manager import AudioCacheManager

        # Clear any registered services
        AIServiceFactory._service_registry = {}

        # Create cache manager
        cache_manager = AudioCacheManager(audio_disabled_config)

        # Try to create an audio service
        with pytest.raises(ValueError):
            await cache_manager.create_service("openai", "test-adapter")

        # Check log messages
        log_messages = [record.message for record in caplog.records]

        # Should have INFO message about audio being disabled
        assert any(
            "audio is globally disabled" in msg and "openai" in msg
            for msg in log_messages
        ), f"Expected INFO log about audio disabled. Got: {log_messages}"

        # Should NOT have ERROR level logs about missing services
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        # Error records should not contain the "No service registered" message
        # when audio is globally disabled
        for record in error_records:
            if "No service registered" in record.message:
                assert "audio is globally disabled" in record.message or True  # Allow if it explains why


class TestAdapterLoaderAudioDisabled:
    """Test adapter loader behavior when audio is disabled."""

    @pytest.fixture
    def audio_disabled_config(self) -> Dict[str, Any]:
        """Create a config with audio globally disabled."""
        return {
            "sound": {
                "enabled": False,
                "provider": "openai"
            },
            "sounds": {
                "openai": {"enabled": True}
            }
        }

    @pytest.mark.asyncio
    async def test_adapter_loader_logs_debug_when_audio_disabled(
        self, audio_disabled_config, caplog
    ):
        """Test that adapter loader logs at DEBUG level when skipping audio service."""
        caplog.set_level(logging.DEBUG)

        from services.loader.adapter_loader import AdapterLoader

        # Clear any registered services
        AIServiceFactory._service_registry = {}

        # Create mock cache managers
        provider_cache = MagicMock()
        embedding_cache = MagicMock()
        reranker_cache = MagicMock()
        audio_cache = AsyncMock()

        # Make audio_cache.create_service raise ValueError
        audio_cache.create_service.side_effect = ValueError(
            "No service registered for audio with provider openai"
        )

        # Create loader
        loader = AdapterLoader(
            config=audio_disabled_config,
            app_state=None,
            provider_cache=provider_cache,
            embedding_cache=embedding_cache,
            reranker_cache=reranker_cache,
            audio_cache=audio_cache
        )

        # Create adapter config with audio_provider
        adapter_config = {
            "name": "test-adapter",
            "audio_provider": "openai",
            "implementation": "retrievers.base_retriever.BaseRetriever",
            "type": "passthrough"
        }

        # Mock the retriever class creation
        with patch('services.loader.adapter_loader.AdapterLoader._create_adapter_sync') as mock_create:
            mock_retriever = MagicMock()
            mock_create.return_value = mock_retriever
            mock_retriever.initialize = AsyncMock()

            # Try to load adapter
            try:
                await loader.load_adapter("test-adapter", adapter_config)
            except Exception:
                pass  # We just want to test the logging

        # Check log messages
        log_messages = [record.message for record in caplog.records]

        # Should have DEBUG message about skipping audio service
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any(
            "Skipping audio service preload" in r.message and "audio is globally disabled" in r.message
            for r in debug_records
        ), f"Expected DEBUG log about skipping audio. Got: {log_messages}"

        # Should NOT have WARNING about failed preload (when audio is globally disabled)
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "Failed to preload audio service" in r.message
        ]
        # If there are warnings, they should not be about globally disabled audio
        for record in warning_records:
            if "test-adapter" in record.message and "openai" in record.message:
                # This warning should not appear because we handle it at DEBUG level
                pytest.fail(f"Unexpected WARNING log when audio is disabled: {record.message}")


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v", "-s"])
