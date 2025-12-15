"""
Test for MongoDB service singleton functionality.

This test verifies that the MongoDBService properly reuses
instances instead of creating new ones for the same configuration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

from services.mongodb_service import MongoDBService


@pytest.fixture
def mock_mongodb_config():
    """Create a mock MongoDB configuration for testing."""
    return {
        'general': {
        },
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db',
                'username': 'user',
                'password': 'pass'
            }
        }
    }


def test_mongodb_service_singleton_same_config(mock_mongodb_config):
    """Test that the same configuration returns the same instance."""
    
    # Clear any existing cache
    MongoDBService.clear_cache()
    
    # Create two services with same config
    service1 = MongoDBService(mock_mongodb_config)
    service2 = MongoDBService(mock_mongodb_config)
    
    # Should be the same instance
    assert service1 is service2
    
    # Verify cache stats
    stats = MongoDBService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_mongodb_service_singleton_different_configs():
    """Test that different configurations create different instances."""
    
    # Clear any existing cache
    MongoDBService.clear_cache()
    
    config1 = {
        'general': {},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'db1'
            }
        }
    }
    
    config2 = {
        'general': {},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'db2'  # Different database
            }
        }
    }
    
    # Create services with different configs
    service1 = MongoDBService(config1)
    service2 = MongoDBService(config2)
    
    # Should be different instances
    assert service1 is not service2
    
    # Verify cache stats
    stats = MongoDBService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_mongodb_service_cache_key_generation():
    """Test that cache keys are generated correctly."""
    
    config = {
        'internal_services': {
            'mongodb': {
                'host': 'test-host',
                'port': 27017,
                'database': 'test_db'
            }
        }
    }
    
    cache_key = MongoDBService._create_cache_key(config)
    expected_key = 'mongodb:test-host:27017:test_db'
    
    assert cache_key == expected_key


def test_mongodb_service_cache_key_defaults():
    """Test that cache keys handle missing configuration gracefully."""
    
    # Config with minimal MongoDB settings
    config = {
        'internal_services': {
            'mongodb': {}  # Empty MongoDB config
        }
    }
    
    cache_key = MongoDBService._create_cache_key(config)
    expected_key = 'mongodb:localhost:27017:default'
    
    assert cache_key == expected_key


def test_mongodb_service_clear_cache():
    """Test that cache clearing works properly."""
    
    # Clear any existing cache
    MongoDBService.clear_cache()
    
    config = {
        'general': {},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        }
    }
    
    # Create a service
    service1 = MongoDBService(config)
    
    # Verify it's cached
    cached_instances = MongoDBService.get_cached_instances()
    assert len(cached_instances) == 1
    
    # Clear cache
    MongoDBService.clear_cache()
    
    # Verify cache is empty
    cached_instances = MongoDBService.get_cached_instances()
    assert len(cached_instances) == 0
    
    # Create another service - should create new instance
    service2 = MongoDBService(config)
    
    # Should be different instance now (new creation)
    assert service1 is not service2


def test_mongodb_service_initialization_once():
    """Test that singleton instances don't re-initialize."""
    
    # Clear any existing cache
    MongoDBService.clear_cache()
    
    config = {
        'general': {},
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        }
    }
    
    # Create first service and mark as initialized
    service1 = MongoDBService(config)
    service1._initialized = True
    service1.test_marker = "first_init"
    
    # Create second service with same config
    service2 = MongoDBService(config)
    
    # Should be same instance and retain the marker
    assert service1 is service2
    assert hasattr(service2, 'test_marker')
    assert service2.test_marker == "first_init"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])