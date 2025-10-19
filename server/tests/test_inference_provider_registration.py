#!/usr/bin/env python3
"""
Test inference provider registration with selective loading based on config.

This module tests the registry functionality to ensure that only enabled
inference providers are registered when a config is provided, reducing
memory usage by not loading disabled providers.
"""

import pytest
import sys
import os
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Add server directory to Python path
sys.path.append(server_dir)

from ai_services.registry import register_inference_services
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType


class TestInferenceProviderRegistration:
    """Test cases for selective inference provider registration."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset the factory before each test to ensure clean state."""
        # Clear the factory's internal registry before each test
        # The registry is a dict with (ServiceType, provider) tuples as keys
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
        """Create a config with only some providers enabled."""
        return {
            "inference": {
                "openai": {"enabled": True, "api_key": "test-key", "model": "gpt-4"},
                "anthropic": {"enabled": True, "api_key": "test-key", "model": "claude-3"},
                "ollama": {"enabled": False, "base_url": "http://localhost:11434"},
                "groq": {"enabled": True, "api_key": "test-key", "model": "llama-3.1"},
                "gemini": {"enabled": False, "api_key": "test-key"},
                "mistral": {"enabled": False, "api_key": "test-key"},
                "deepseek": {"enabled": False, "api_key": "test-key"},
                "aws": {"enabled": False},
                "azure": {"enabled": False},
                "vertexai": {"enabled": False},
                "cohere": {"enabled": False, "api_key": "test-key"},
                "nvidia": {"enabled": False},
                "replicate": {"enabled": False},
                "watson": {"enabled": False},
                "vllm": {"enabled": False},
                "llama_cpp": {"enabled": False},
                "huggingface": {"enabled": False},
                "ollama_cloud": {"enabled": False},
                "bitnet": {"enabled": False},
                "zai": {"enabled": False},
                "fireworks": {"enabled": False},
                "perplexity": {"enabled": False},
                "together": {"enabled": False},
                "openrouter": {"enabled": False},
                "xai": {"enabled": False},
            }
        }

    @pytest.fixture
    def all_disabled_config(self) -> Dict[str, Any]:
        """Create a config with all providers disabled."""
        return {
            "inference": {
                "openai": {"enabled": False},
                "anthropic": {"enabled": False},
                "ollama": {"enabled": False},
                "groq": {"enabled": False},
                "gemini": {"enabled": False},
                "mistral": {"enabled": False},
                "deepseek": {"enabled": False},
                "aws": {"enabled": False},
                "azure": {"enabled": False},
                "vertexai": {"enabled": False},
                "cohere": {"enabled": False},
                "nvidia": {"enabled": False},
                "replicate": {"enabled": False},
                "watson": {"enabled": False},
                "vllm": {"enabled": False},
                "llama_cpp": {"enabled": False},
                "huggingface": {"enabled": False},
                "ollama_cloud": {"enabled": False},
                "bitnet": {"enabled": False},
                "zai": {"enabled": False},
                "fireworks": {"enabled": False},
                "perplexity": {"enabled": False},
                "together": {"enabled": False},
                "openrouter": {"enabled": False},
                "xai": {"enabled": False},
            }
        }

    def test_register_only_enabled_providers(self, enabled_providers_config):
        """Test that only enabled providers are registered when config is provided."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            # Create a mock module with mock service classes
            mock_module = MagicMock()
            mock_module.OpenAIInferenceService = MagicMock()
            mock_module.AnthropicInferenceService = MagicMock()
            mock_module.GroqInferenceService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                # For other imports, use the real import
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_inference_services(enabled_providers_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            inference_providers = available_services.get('inference', [])

            # Verify that only enabled providers are registered
            assert 'openai' in inference_providers
            assert 'anthropic' in inference_providers
            assert 'groq' in inference_providers

            # Verify that disabled providers are NOT registered
            assert 'ollama' not in inference_providers
            assert 'gemini' not in inference_providers
            assert 'mistral' not in inference_providers
            assert 'deepseek' not in inference_providers

    def test_register_no_providers_when_all_disabled(self, all_disabled_config):
        """Test that no providers are registered when all are disabled."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config where all are disabled
            register_inference_services(all_disabled_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            inference_providers = available_services.get('inference', [])

            # Verify that no inference providers are registered
            assert len(inference_providers) == 0

    def test_register_without_config_backward_compatibility(self):
        """Test that providers are registered when no config is provided (backward compatibility)."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            # Add some mock service classes
            mock_module.OpenAIInferenceService = MagicMock()
            mock_module.AnthropicInferenceService = MagicMock()
            mock_module.OllamaInferenceService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services without config (backward compatibility)
            register_inference_services(None)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            inference_providers = available_services.get('inference', [])

            # When no config is provided, all providers should be attempted
            # (subject to successful import)
            assert 'openai' in inference_providers
            assert 'anthropic' in inference_providers
            assert 'ollama' in inference_providers

    def test_logging_for_disabled_providers(self, enabled_providers_config, caplog):
        """Test that disabled providers are logged appropriately."""
        import logging
        caplog.set_level(logging.DEBUG)

        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIInferenceService = MagicMock()
            mock_module.AnthropicInferenceService = MagicMock()
            mock_module.OllamaInferenceService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_inference_services(enabled_providers_config)

            # Check that disabled providers are logged
            assert any("Ollama" in record.message and "disabled in config" in record.message
                      for record in caplog.records)
            assert any("Gemini" in record.message and "disabled in config" in record.message
                      for record in caplog.records)

    def test_logging_for_enabled_providers(self, enabled_providers_config, caplog):
        """Test that enabled providers are logged when registered."""
        import logging
        caplog.set_level(logging.DEBUG)

        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIInferenceService = MagicMock()
            mock_module.AnthropicInferenceService = MagicMock()
            mock_module.GroqInferenceService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_inference_services(enabled_providers_config)

            # Get all log messages
            all_messages = [record.message for record in caplog.records]

            # Check that enabled providers are logged as registered
            # The actual log message is "Registered {display_name} inference service"
            assert any("OpenAI" in msg and "inference service" in msg for msg in all_messages), \
                f"Expected OpenAI log message not found. All messages: {all_messages}"
            assert any("Anthropic" in msg and "inference service" in msg for msg in all_messages), \
                f"Expected Anthropic log message not found. All messages: {all_messages}"
            assert any("Groq" in msg and "inference service" in msg for msg in all_messages), \
                f"Expected Groq log message not found. All messages: {all_messages}"

    def test_partial_enabled_providers(self):
        """Test with a mix of enabled and disabled providers."""
        config = {
            "inference": {
                "openai": {"enabled": True, "api_key": "test"},
                "anthropic": {"enabled": False},
                "groq": {"enabled": True, "api_key": "test"},
                "ollama": {"enabled": False},
            }
        }

        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIInferenceService = MagicMock()
            mock_module.GroqInferenceService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with mixed config
            register_inference_services(config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            inference_providers = available_services.get('inference', [])

            # Verify correct providers are registered
            assert 'openai' in inference_providers
            assert 'groq' in inference_providers
            assert 'anthropic' not in inference_providers
            assert 'ollama' not in inference_providers

    def test_missing_enabled_flag_defaults_to_false(self):
        """Test that providers without an 'enabled' flag are treated as disabled."""
        config = {
            "inference": {
                "openai": {"enabled": True, "api_key": "test"},
                "anthropic": {"api_key": "test"},  # No enabled flag
            }
        }

        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIInferenceService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_inference_services(config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            inference_providers = available_services.get('inference', [])

            # Only openai should be registered (anthropic has no enabled flag)
            assert 'openai' in inference_providers
            assert 'anthropic' not in inference_providers

    def test_empty_inference_config(self):
        """Test behavior when inference config is empty."""
        config = {"inference": {}}

        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with empty inference config
            register_inference_services(config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            inference_providers = available_services.get('inference', [])

            # No providers should be registered
            assert len(inference_providers) == 0


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
