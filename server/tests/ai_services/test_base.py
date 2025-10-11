"""
Basic tests for AI services base classes.

This module contains simple tests to verify that the base classes
can be imported and instantiated correctly.

Run with: python -m pytest server/tests/ai_services/test_base.py
"""

import pytest
from typing import Dict, Any

from server.ai_services.base import AIService, ProviderAIService, ServiceType


# Mock concrete implementation for testing
class MockAIService(AIService):
    """Mock implementation of AIService for testing."""

    def __init__(self, config: Dict[str, Any], service_type: ServiceType):
        super().__init__(config, service_type)

    async def initialize(self) -> bool:
        self.initialized = True
        return True

    async def close(self) -> None:
        self.initialized = False

    async def verify_connection(self) -> bool:
        return True


class MockProviderService(ProviderAIService):
    """Mock implementation of ProviderAIService for testing."""

    async def initialize(self) -> bool:
        self.initialized = True
        return True

    async def close(self) -> None:
        self.initialized = False

    async def verify_connection(self) -> bool:
        return True


class TestAIServiceBase:
    """Tests for AIService base class."""

    def test_service_initialization(self):
        """Test that AIService can be instantiated."""
        config = {"test": "config"}
        service = MockAIService(config, ServiceType.EMBEDDING)

        assert service.config == config
        assert service.service_type == ServiceType.EMBEDDING
        assert service.initialized is False
        assert service.logger is not None

    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """Test service lifecycle (initialize -> close)."""
        config = {"test": "config"}
        service = MockAIService(config, ServiceType.EMBEDDING)

        # Initially not initialized
        assert service.initialized is False

        # Initialize
        result = await service.initialize()
        assert result is True
        assert service.initialized is True

        # Close
        await service.close()
        assert service.initialized is False

    @pytest.mark.asyncio
    async def test_service_connection_verification(self):
        """Test connection verification."""
        config = {"test": "config"}
        service = MockAIService(config, ServiceType.EMBEDDING)

        result = await service.verify_connection()
        assert result is True


class TestProviderAIService:
    """Tests for ProviderAIService base class."""

    def test_provider_service_initialization(self):
        """Test that ProviderAIService can be instantiated."""
        config = {
            "openai": {
                "model": "test-model",
                "api_key": "test-key",
                "base_url": "https://test.api.com"
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")

        assert service.config == config
        assert service.service_type == ServiceType.EMBEDDING
        assert service.provider_name == "openai"
        assert service.initialized is False

    def test_extract_provider_config(self):
        """Test extraction of provider-specific config."""
        config = {
            "embeddings": {
                "openai": {
                    "model": "text-embedding-3-small",
                    "api_key": "test-key"
                }
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        provider_config = service._extract_provider_config()

        assert "model" in provider_config
        assert provider_config["model"] == "text-embedding-3-small"

    def test_resolve_api_key_from_config(self):
        """Test API key resolution from config."""
        config = {
            "openai": {
                "api_key": "direct-key-value"
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        api_key = service._resolve_api_key("NONEXISTENT_ENV_VAR")

        # Should get the direct value since env var doesn't exist
        assert api_key == "direct-key-value"

    def test_get_base_url(self):
        """Test base URL retrieval."""
        config = {
            "openai": {
                "base_url": "https://custom.api.com"
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        base_url = service._get_base_url("https://default.api.com")

        assert base_url == "https://custom.api.com"

    def test_get_base_url_default(self):
        """Test base URL with default."""
        config = {"openai": {}}
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        base_url = service._get_base_url("https://default.api.com")

        assert base_url == "https://default.api.com"

    def test_get_endpoint(self):
        """Test endpoint retrieval."""
        config = {
            "openai": {
                "endpoint": "/v2/embeddings"
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        endpoint = service._get_endpoint("/v1/embeddings")

        assert endpoint == "/v2/embeddings"

    def test_get_timeout_config(self):
        """Test timeout configuration retrieval."""
        config = {
            "openai": {
                "timeout": {
                    "connect": 5000,
                    "total": 30000,
                    "warmup": 20000
                }
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        timeout_config = service._get_timeout_config()

        assert timeout_config["connect"] == 5000
        assert timeout_config["total"] == 30000
        assert timeout_config["warmup"] == 20000

    def test_get_timeout_config_defaults(self):
        """Test timeout configuration with defaults."""
        config = {"openai": {}}
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        timeout_config = service._get_timeout_config()

        # Should use defaults
        assert timeout_config["connect"] == 10000
        assert timeout_config["total"] == 60000
        assert timeout_config["warmup"] == 45000

    def test_get_retry_config(self):
        """Test retry configuration retrieval."""
        config = {
            "openai": {
                "retry": {
                    "enabled": True,
                    "max_retries": 5,
                    "initial_wait_ms": 2000,
                    "max_wait_ms": 60000,
                    "exponential_base": 3
                }
            }
        }
        service = MockProviderService(config, ServiceType.EMBEDDING, "openai")
        retry_config = service._get_retry_config()

        assert retry_config["enabled"] is True
        assert retry_config["max_retries"] == 5
        assert retry_config["initial_wait_ms"] == 2000
        assert retry_config["max_wait_ms"] == 60000
        assert retry_config["exponential_base"] == 3


class TestServiceType:
    """Tests for ServiceType enum."""

    def test_service_types_exist(self):
        """Test that all expected service types exist."""
        assert ServiceType.EMBEDDING.value == "embedding"
        assert ServiceType.INFERENCE.value == "inference"
        assert ServiceType.MODERATION.value == "moderation"
        assert ServiceType.RERANKING.value == "reranking"
        assert ServiceType.VISION.value == "vision"
        assert ServiceType.AUDIO.value == "audio"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
