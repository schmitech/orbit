"""
Test Redis service singleton pattern.

This test verifies that RedisService uses a singleton pattern based on configuration
to prevent duplicate Redis connections for the same configuration.
"""

import pytest
import sys
import os
import asyncio

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.redis_service import RedisService


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return {
        'general': {
            'verbose': False
        },
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'use_ssl': False
            }
        }
    }


@pytest.fixture
def alternate_config():
    """Create an alternate configuration for testing."""
    return {
        'general': {
            'verbose': False
        },
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6380,  # Different port
                'db': 0,
                'use_ssl': False
            }
        }
    }


def test_redis_singleton_same_config(mock_config):
    """Test that same configuration returns the same Redis service instance."""
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    # Create multiple Redis service instances with same config
    service1 = RedisService(mock_config)
    service2 = RedisService(mock_config)
    service3 = RedisService(mock_config)
    
    # All should be the same instance
    assert service1 is service2
    assert service2 is service3
    assert service1 is service3
    
    # Verify only one instance was cached
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_redis_singleton_different_configs(mock_config, alternate_config):
    """Test that different configurations create separate instances."""
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    # Create Redis services with different configs
    service1 = RedisService(mock_config)
    service2 = RedisService(alternate_config)
    
    # Should have different instances
    assert service1 is not service2
    
    # Should have 2 cached instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 2
    
    # Same config should return same instance
    service3 = RedisService(mock_config)
    assert service1 is service3
    
    # Still should have 2 cached instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_redis_cache_key_creation():
    """Test cache key creation for different configurations."""
    
    config1 = {
        'internal_services': {
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'use_ssl': False
            }
        }
    }
    
    config2 = {
        'internal_services': {
            'redis': {
                'host': 'localhost',
                'port': 6380,  # Different port
                'db': 0,
                'use_ssl': False
            }
        }
    }
    
    key1 = RedisService._create_cache_key(config1)
    key2 = RedisService._create_cache_key(config2)
    
    # Different configs should create different keys
    assert key1 != key2
    
    # Same config should create same key
    key1_again = RedisService._create_cache_key(config1)
    assert key1 == key1_again


def test_redis_cache_stats():
    """Test cache statistics functionality."""
    
    # Clear cache
    RedisService.clear_cache()
    
    # Initial stats should show no instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 0
    assert stats['cached_configurations'] == []
    
    # Create a service
    config = {
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0
            }
        }
    }
    
    service = RedisService(config)
    
    # Stats should show one instance
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 1
    assert len(stats['cached_configurations']) == 1
    assert 'Redis service instances cached' in stats['memory_info']


def test_redis_clear_cache():
    """Test cache clearing functionality."""
    
    # Create some cached instances
    config1 = {
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0
            }
        }
    }
    
    config2 = {
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6380,
                'db': 0
            }
        }
    }
    
    service1 = RedisService(config1)
    service2 = RedisService(config2)
    
    # Should have 2 instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 2
    
    # Clear cache
    RedisService.clear_cache()
    
    # Should have no instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 0


def test_redis_singleton_with_ssl_config():
    """Test that SSL configuration affects cache key."""
    
    # Clear cache
    RedisService.clear_cache()
    
    config_no_ssl = {
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'use_ssl': False
            }
        }
    }
    
    config_with_ssl = {
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'use_ssl': True
            }
        }
    }
    
    service1 = RedisService(config_no_ssl)
    service2 = RedisService(config_with_ssl)
    
    # Should be different instances due to SSL difference
    assert service1 is not service2
    
    # Should have 2 cached instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_redis_no_reinitialization():
    """Test that singleton instances are not re-initialized."""
    
    # Clear cache
    RedisService.clear_cache()
    
    config = {
        'general': {'verbose': True},
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0
            }
        }
    }
    
    # Create first instance
    service1 = RedisService(config)
    
    # Store original values
    original_enabled = service1.enabled
    original_initialized = hasattr(service1, '_singleton_initialized')
    
    # Create second instance with same config
    service2 = RedisService(config)
    
    # Should be the same instance
    assert service1 is service2
    
    # Values should not have changed
    assert service2.enabled == original_enabled
    assert hasattr(service2, '_singleton_initialized') == original_initialized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])