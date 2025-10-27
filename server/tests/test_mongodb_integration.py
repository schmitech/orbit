"""
Test MongoDB service integration with other services.

This test verifies that services creating MongoDB instances 
actually get the shared singleton instance.
"""

import pytest
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.mongodb_service import MongoDBService
from services.api_key_service import ApiKeyService
from services.auth_service import AuthService
from services.prompt_service import PromptService


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return {
        'general': {
            'verbose': False
        },
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys',
            'system_prompts_collection': 'system_prompts'
        }
    }


def test_services_share_mongodb_singleton(mock_config):
    """Test that different services share the same MongoDB instance."""
    
    # Clear any existing caches for all services
    MongoDBService.clear_cache()
    ApiKeyService.clear_cache()
    # Note: AuthService and PromptService don't have singleton patterns yet
    
    # Create services that internally create database instances
    api_key_service = ApiKeyService(mock_config)  # No database_service passed
    auth_service = AuthService(mock_config)       # No database_service passed
    prompt_service = PromptService(mock_config)   # No database_service passed

    # All should have the same database instance due to singleton
    assert api_key_service.database is auth_service.database
    assert auth_service.database is prompt_service.database
    assert api_key_service.database is prompt_service.database

    # Verify only one MongoDB instance was cached
    stats = MongoDBService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_service_factory_and_services_share_mongodb(mock_config):
    """Test that service factory and individual services share MongoDB."""

    # Clear any existing caches for all services
    MongoDBService.clear_cache()
    ApiKeyService.clear_cache()

    # Create instance like service factory does
    shared_mongodb = MongoDBService(mock_config)

    # Create service that would normally create its own instance
    api_key_service = ApiKeyService(mock_config)

    # Should be the same instance (database property now)
    assert api_key_service.database is shared_mongodb

    # Verify only one instance cached
    stats = MongoDBService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_mongodb_singleton_with_different_databases():
    """Test that different databases create separate instances."""
    
    # Clear any existing caches for all services
    MongoDBService.clear_cache()
    ApiKeyService.clear_cache()
    
    config1 = {
        'general': {'verbose': False},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'db1'
            }
        }
    }
    
    config2 = {
        'general': {'verbose': False},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'db2'  # Different database
            }
        }
    }
    
    # Create services with different database configs
    service1 = ApiKeyService(config1)
    service2 = ApiKeyService(config2)

    # Should have different database instances
    assert service1.database is not service2.database

    # Should have 2 cached instances
    stats = MongoDBService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])