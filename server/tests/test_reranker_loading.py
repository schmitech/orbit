"""
Test reranker service loading and registration.

This test verifies that reranker services are properly registered and accessible
through the AIServiceFactory, addressing the "Available providers: []" issue.
"""

import pytest
import sys
import yaml
from pathlib import Path

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from ai_services.registry import register_all_services
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType
from services.reranker_service_manager import RerankingServiceManager


@pytest.fixture
def config():
    """Load the rerankers configuration."""
    config_path = Path(__file__).parent.parent.parent / "config" / "rerankers.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture(autouse=True)
def register_services(config):
    """Register all services before each test."""
    # Clear reranking services from registry to ensure fresh state per test
    # This is necessary because register_all_services() has a guard that prevents
    # re-registration, but we need to test with different configs (enabled/disabled providers)
    available = AIServiceFactory.list_available_services()
    reranking_providers = available.get('reranking', [])
    for provider in reranking_providers:
        AIServiceFactory.unregister_service(ServiceType.RERANKING, provider)
    
    # Reset the registry flag to allow re-registration
    import ai_services.registry as registry
    registry._services_registered = False
    
    # Now register all services with current config
    register_all_services(config)


def test_reranker_services_registered(config):
    """Test that reranker services are registered in the factory."""
    available = AIServiceFactory.list_available_services()

    # Check that reranking is in the available services
    assert 'reranking' in available, "Reranking service type not found in registry"

    # Get enabled providers from config
    enabled_providers = [
        provider for provider, cfg in config.get('rerankers', {}).items()
        if cfg.get('enabled', True) is not False
    ]

    print(f"Enabled providers in config: {enabled_providers}")
    print(f"Registered providers: {available['reranking']}")

    # Check that enabled providers are registered
    for provider in enabled_providers:
        assert provider in available['reranking'], \
            f"Provider '{provider}' is enabled but not registered. Available: {available['reranking']}"


def test_reranker_service_creation(config):
    """Test that reranker services can be created through RerankingServiceManager."""
    # Get enabled providers from config
    enabled_providers = [
        provider for provider, cfg in config.get('rerankers', {}).items()
        if cfg.get('enabled', True) is not False
    ]

    # Test creating service for first enabled provider
    if enabled_providers:
        provider = enabled_providers[0]
        print(f"Testing service creation for provider: {provider}")

        try:
            service = RerankingServiceManager.create_reranker_service(config, provider)
            assert service is not None, f"Service creation returned None for {provider}"
            print(f"Successfully created service for {provider}: {type(service).__name__}")
        except ValueError as e:
            # Skip if API key is missing (expected in test environment)
            if "API key" in str(e) or "api_key" in str(e):
                pytest.skip(f"Skipping service creation test - API key not configured: {str(e)}")
            else:
                pytest.fail(f"Failed to create service for {provider}: {str(e)}")
        except Exception as e:
            pytest.fail(f"Unexpected error creating service for {provider}: {str(e)}")


def test_factory_module_identity():
    """Test that factory module has consistent identity across import paths."""
    import ai_services.factory as f1
    from server.ai_services.factory import AIServiceFactory as F2

    # Check module identity
    assert sys.modules.get("ai_services.factory") is sys.modules.get("server.ai_services.factory"), \
        "Factory module has different identities for different import paths"

    # Check class identity
    assert f1.AIServiceFactory is F2, \
        "AIServiceFactory class is different for different import paths"


def test_service_type_module_identity():
    """Test that ServiceType enum has consistent identity across import paths."""
    from ai_services.base import ServiceType as ST1
    from server.ai_services.base import ServiceType as ST2

    # Check module identity
    assert sys.modules.get("ai_services.base") is sys.modules.get("server.ai_services.base"), \
        "Base module has different identities for different import paths"

    # Check enum identity
    assert ST1 is ST2, "ServiceType enum is different for different import paths"
    assert ST1.RERANKING is ST2.RERANKING, "ServiceType.RERANKING is different"


def test_disabled_providers_not_registered(config):
    """Test that disabled providers are not registered."""
    available = AIServiceFactory.list_available_services()

    # Get disabled providers from config
    disabled_providers = [
        provider for provider, cfg in config.get('rerankers', {}).items()
        if cfg.get('enabled', True) is False
    ]

    print(f"Disabled providers in config: {disabled_providers}")
    print(f"Registered providers: {available.get('reranking', [])}")

    # Check that disabled providers are NOT registered
    for provider in disabled_providers:
        assert provider not in available.get('reranking', []), \
            f"Provider '{provider}' is disabled but was registered"


def test_reranker_service_manager_cache():
    """Test that RerankingServiceManager caches instances correctly."""
    import yaml

    config_path = Path(__file__).parent.parent.parent / "config" / "rerankers.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Get first enabled provider
    enabled_providers = [
        provider for provider, cfg in config.get('rerankers', {}).items()
        if cfg.get('enabled', True) is not False
    ]

    if enabled_providers:
        provider = enabled_providers[0]

        try:
            # Create service twice
            service1 = RerankingServiceManager.create_reranker_service(config, provider)
            service2 = RerankingServiceManager.create_reranker_service(config, provider)

            # Should be the same instance (singleton)
            assert service1 is service2, \
                f"RerankingServiceManager did not return cached instance for {provider}"

            print(f"Cache test passed for {provider}: {id(service1)} == {id(service2)}")
        except ValueError as e:
            # Skip if API key is missing (expected in test environment)
            if "API key" in str(e) or "api_key" in str(e):
                pytest.skip(f"Skipping cache test - API key not configured: {str(e)}")
            else:
                raise


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
