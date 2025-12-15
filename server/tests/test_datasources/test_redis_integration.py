"""
Test Redis service integration with other services.

This test verifies that services creating Redis instances 
actually get the shared singleton instance.
"""

import pytest
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

from services.redis_service import RedisService


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return {
        'general': {
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


def test_service_factory_and_other_services_share_redis(mock_config):
    """Test that service factory and any other services share Redis."""
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    # Create instance like service factory does
    shared_redis = RedisService(mock_config)
    
    # Create another instance that would normally create its own
    another_redis = RedisService(mock_config)
    
    # Should be the same instance
    assert shared_redis is another_redis
    
    # Verify only one instance cached
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_redis_singleton_with_different_databases():
    """Test that different databases create separate instances."""
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    config1 = {
        'general': {},
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
        'general': {},
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 1  # Different database
            }
        }
    }
    
    # Create services with different database configs
    service1 = RedisService(config1)
    service2 = RedisService(config2)
    
    # Should have different Redis instances
    assert service1 is not service2
    
    # Should have 2 cached instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_redis_singleton_with_different_hosts():
    """Test that different hosts create separate instances."""
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    config1 = {
        'general': {},
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
        'general': {},
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'redis-server',  # Different host
                'port': 6379,
                'db': 0
            }
        }
    }
    
    # Create services with different host configs
    service1 = RedisService(config1)
    service2 = RedisService(config2)
    
    # Should have different Redis instances
    assert service1 is not service2
    
    # Should have 2 cached instances
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_redis_singleton_preserves_configuration():
    """Test that singleton preserves original configuration."""
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    config = {
        'general': {},
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'ttl': 3600  # Custom TTL
            }
        }
    }
    
    # Create first instance
    service1 = RedisService(config)
    
    # Create second instance with same config
    service2 = RedisService(config)
    
    # Should be same instance
    assert service1 is service2
    
    # Configuration should be preserved
    assert service1.config == config
    assert service2.config == config
    assert service1.default_ttl == 3600  # Custom TTL should be preserved


def test_redis_singleton_thread_safety():
    """Test that singleton is thread-safe."""
    import threading
    import time
    
    # Clear any existing cache
    RedisService.clear_cache()
    
    config = {
        'general': {},
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': 'localhost',
                'port': 6379,
                'db': 0
            }
        }
    }
    
    instances = []
    
    def create_service():
        # Add small delay to increase chance of race condition
        time.sleep(0.01)
        service = RedisService(config)
        instances.append(service)
    
    # Create multiple threads
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=create_service)
        threads.append(thread)
    
    # Start all threads
    for thread in threads:
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # All instances should be the same
    first_instance = instances[0]
    for instance in instances[1:]:
        assert instance is first_instance
    
    # Should have only 1 cached instance
    stats = RedisService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])