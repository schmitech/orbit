"""
Test API Key Service integration with other services.

This test verifies that services creating API Key Service instances 
actually get the shared singleton instance and work properly with the service factory.
"""

import pytest
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.api_key_service import ApiKeyService
from services.mongodb_service import MongoDBService


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
            'apikey_collection': 'api_keys'
        }
    }


def test_service_factory_pattern_with_api_key_service(mock_config):
    """Test that service factory pattern works with API key service singleton."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create instance like service factory does (with shared MongoDB service)
    shared_mongodb = MongoDBService(mock_config)
    shared_api_key_service = ApiKeyService(mock_config, shared_mongodb)
    
    # Create another instance that would normally create its own
    another_api_key_service = ApiKeyService(mock_config, shared_mongodb)
    
    # Should be the same instance
    assert shared_api_key_service is another_api_key_service
    
    # Should share the same MongoDB service
    assert shared_api_key_service.mongodb is shared_mongodb
    assert another_api_key_service.mongodb is shared_mongodb
    
    # Verify only one API key service instance cached
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_api_key_service_with_different_mongodb_instances(mock_config):
    """Test that different MongoDB instances create separate API key service instances."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create two different MongoDB services (this should not happen in practice due to singleton)
    mongodb1 = MongoDBService(mock_config)
    mongodb2 = MongoDBService(mock_config)  # Should be same as mongodb1 due to singleton
    
    # Since MongoDB is singleton, both should be the same
    assert mongodb1 is mongodb2
    
    # Create API key services with same MongoDB instance
    service1 = ApiKeyService(mock_config, mongodb1)
    service2 = ApiKeyService(mock_config, mongodb2)
    
    # Should be same instance since MongoDB instances are the same
    assert service1 is service2


def test_api_key_service_mixed_initialization_patterns():
    """Test mixing service creation with and without provided MongoDB service."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config = {
        'general': {'verbose': False},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    # Create API key service without providing MongoDB (it will create its own)
    service1 = ApiKeyService(config)
    
    # Create MongoDB service separately
    mongodb_service = MongoDBService(config)
    
    # Since MongoDB uses singleton, service1's MongoDB should be the same
    assert service1.mongodb is mongodb_service
    
    # Create another API key service with explicitly provided MongoDB
    service2 = ApiKeyService(config, mongodb_service)
    
    # Should be the same API key service instance
    assert service1 is service2


def test_api_key_service_preserves_configuration_integrity():
    """Test that singleton preserves configuration integrity across instances."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config = {
        'general': {'verbose': True},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'custom_api_keys'
        }
    }
    
    # Create first instance
    service1 = ApiKeyService(config)
    
    # Verify configuration
    assert service1.collection_name == 'custom_api_keys'
    assert service1.verbose is True
    
    # Create second instance with same config
    service2 = ApiKeyService(config)
    
    # Should be same instance
    assert service1 is service2
    
    # Configuration should be preserved
    assert service2.collection_name == 'custom_api_keys'
    assert service2.verbose is True


def test_api_key_service_handles_initialization_state():
    """Test that singleton properly handles initialization state."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config = {
        'general': {'verbose': False},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    # Create first instance
    service1 = ApiKeyService(config)
    
    # Check initial state
    assert not service1._initialized
    assert service1.api_keys_collection is None
    
    # Create second instance
    service2 = ApiKeyService(config)
    
    # Should be same instance with same state
    assert service1 is service2
    assert not service2._initialized
    assert service2.api_keys_collection is None


def test_api_key_service_concurrent_access():
    """Test that concurrent access to singleton works correctly."""
    import threading
    import time
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config = {
        'general': {'verbose': False},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    services = []
    mongodb_services = []
    
    def create_services():
        # Add delay to increase chance of race conditions
        time.sleep(0.01)
        
        # Create MongoDB service
        mongodb = MongoDBService(config)
        mongodb_services.append(mongodb)
        
        # Create API key service
        api_key_service = ApiKeyService(config, mongodb)
        services.append(api_key_service)
    
    # Create multiple threads
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=create_services)
        threads.append(thread)
    
    # Start all threads
    for thread in threads:
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # All API key service instances should be the same
    first_service = services[0]
    for service in services[1:]:
        assert service is first_service
    
    # All MongoDB services should be the same
    first_mongodb = mongodb_services[0]
    for mongodb in mongodb_services[1:]:
        assert mongodb is first_mongodb
    
    # Should have only 1 cached instance of each
    api_key_stats = ApiKeyService.get_cache_stats()
    mongodb_stats = MongoDBService.get_cache_stats()
    assert api_key_stats['total_cached_instances'] == 1
    assert mongodb_stats['total_cached_instances'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])