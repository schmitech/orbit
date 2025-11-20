"""
Test API Key Service singleton pattern.

This test verifies that ApiKeyService uses a singleton pattern based on configuration
to prevent duplicate API key service instances.
"""

import pytest
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.api_key_service import ApiKeyService
from services.mongodb_service import MongoDBService
from services.sqlite_service import SQLiteService


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return {
        'general': {
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


@pytest.fixture
def alternate_config():
    """Create an alternate configuration for testing."""
    return {
        'general': {
        },
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27018,  # Different port
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }


def test_api_key_service_singleton_same_config(mock_config):
    """Test that same configuration returns the same API key service instance."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create multiple API key service instances with same config
    service1 = ApiKeyService(mock_config)
    service2 = ApiKeyService(mock_config)
    service3 = ApiKeyService(mock_config)
    
    # All should be the same instance
    assert service1 is service2
    assert service2 is service3
    assert service1 is service3
    
    # Verify only one instance was cached
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_api_key_service_singleton_different_configs(mock_config, alternate_config):
    """Test that different configurations create separate instances."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create API key services with different configs
    service1 = ApiKeyService(mock_config)
    service2 = ApiKeyService(alternate_config)
    
    # Should have different instances
    assert service1 is not service2
    
    # Should have 2 cached instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 2
    
    # Same config should return same instance
    service3 = ApiKeyService(mock_config)
    assert service1 is service3
    
    # Still should have 2 cached instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_api_key_service_with_provided_mongodb(mock_config):
    """Test API key service with provided MongoDB service instance."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create a MongoDB service (now used as database service)
    mongodb_service = MongoDBService(mock_config)

    # Create API key service with provided database service
    service1 = ApiKeyService(mock_config, database_service=mongodb_service)
    service2 = ApiKeyService(mock_config, database_service=mongodb_service)

    # Should be the same instance
    assert service1 is service2

    # Should share the same database service
    assert service1.database is mongodb_service
    assert service2.database is mongodb_service

    # Create another API key service without provided database service
    service3 = ApiKeyService(mock_config)

    # Should be the SAME instance because configuration is the same
    # and MongoDB service singleton ensures the same database instance is used
    assert service1 is service3
    assert service3.database is mongodb_service  # Database service singleton ensures this


def test_api_key_service_cache_key_creation():
    """Test cache key creation for different configurations."""
    
    config1 = {
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'db1'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    config2 = {
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27018,  # Different port
                'database': 'db1'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    key1 = ApiKeyService._create_cache_key(config1)
    key2 = ApiKeyService._create_cache_key(config2)
    
    # Different configs should create different keys
    assert key1 != key2
    
    # Same config should create same key
    key1_again = ApiKeyService._create_cache_key(config1)
    assert key1 == key1_again


def test_api_key_service_different_collections():
    """Test that different collections create separate instances."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config1 = {
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
    
    config2 = {
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'test_db'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys_v2'  # Different collection
        }
    }
    
    service1 = ApiKeyService(config1)
    service2 = ApiKeyService(config2)
    
    # Should be different instances due to different collection names
    assert service1 is not service2
    
    # Should have different collection names
    assert service1.collection_name == 'api_keys'
    assert service2.collection_name == 'api_keys_v2'


def test_api_key_service_cache_stats():
    """Test cache statistics functionality."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    
    # Initial stats should show no instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 0
    assert stats['cached_configurations'] == []
    
    # Create a service
    config = {
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
    
    service = ApiKeyService(config)
    
    # Stats should show one instance
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 1
    assert len(stats['cached_configurations']) == 1
    assert 'API key service instances cached' in stats['memory_info']


def test_api_key_service_clear_cache():
    """Test cache clearing functionality."""
    
    # Clear any existing cache first
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create some cached instances
    config1 = {
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27017,
                'database': 'db1'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    config2 = {
        'internal_services': {
            'mongodb': {
                'host': 'localhost',
                'port': 27018,
                'database': 'db1'
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys'
        }
    }
    
    service1 = ApiKeyService(config1)
    service2 = ApiKeyService(config2)
    
    # Should have 2 instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 2
    
    # Clear cache
    ApiKeyService.clear_cache()
    
    # Should have no instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 0


def test_api_key_service_no_reinitialization():
    """Test that singleton instances are not re-initialized."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config = {
        'general': {},
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
    
    # Store original values
    original_collection_name = service1.collection_name
    original_initialized = hasattr(service1, '_singleton_initialized')
    
    # Create second instance with same config
    service2 = ApiKeyService(config)
    
    # Should be the same instance
    assert service1 is service2
    
    # Values should not have changed
    assert service2.collection_name == original_collection_name
    assert hasattr(service2, '_singleton_initialized') == original_initialized


def test_api_key_service_thread_safety():
    """Test that singleton is thread-safe."""
    import threading
    import time
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    config = {
        'general': {},
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
    
    instances = []
    
    def create_service():
        # Add small delay to increase chance of race condition
        time.sleep(0.01)
        service = ApiKeyService(config)
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
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


# SQLite backend tests

@pytest.fixture
def mock_sqlite_config():
    """Create a mock SQLite configuration for testing."""
    return {
        'general': {
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': 'test_sqlite.db'
                }
            }
        }
    }


@pytest.fixture
def alternate_sqlite_config():
    """Create an alternate SQLite configuration for testing."""
    return {
        'general': {
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': 'test_sqlite_alt.db'  # Different database path
                }
            }
        }
    }


def test_api_key_service_singleton_sqlite_same_config(mock_sqlite_config):
    """Test that same SQLite configuration returns the same API key service instance."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    SQLiteService.clear_cache()
    
    # Create multiple API key service instances with same config
    service1 = ApiKeyService(mock_sqlite_config)
    service2 = ApiKeyService(mock_sqlite_config)
    service3 = ApiKeyService(mock_sqlite_config)
    
    # All should be the same instance
    assert service1 is service2
    assert service2 is service3
    assert service1 is service3
    
    # Verify only one instance was cached
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 1


def test_api_key_service_singleton_sqlite_different_configs(mock_sqlite_config, alternate_sqlite_config):
    """Test that different SQLite configurations create separate instances."""
    
    # Clear any existing cache
    ApiKeyService.clear_cache()
    SQLiteService.clear_cache()
    
    # Create API key services with different configs
    service1 = ApiKeyService(mock_sqlite_config)
    service2 = ApiKeyService(alternate_sqlite_config)
    
    # Should have different instances
    assert service1 is not service2
    
    # Should have 2 cached instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 2
    
    # Same config should return same instance
    service3 = ApiKeyService(mock_sqlite_config)
    assert service1 is service3
    
    # Still should have 2 cached instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 2


def test_api_key_service_cache_key_creation_sqlite():
    """Test cache key creation for SQLite configurations."""
    
    config1 = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': 'test1.db'
                }
            }
        }
    }
    
    config2 = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': 'test2.db'  # Different database path
                }
            }
        }
    }
    
    key1 = ApiKeyService._create_cache_key(config1)
    key2 = ApiKeyService._create_cache_key(config2)
    
    # Different configs should create different keys
    assert key1 != key2
    
    # Same config should create same key
    key1_again = ApiKeyService._create_cache_key(config1)
    assert key1 == key1_again


def test_api_key_service_sqlite_collection_name():
    """Test that SQLite backend uses default collection name."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    SQLiteService.clear_cache()
    
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': 'test_sqlite.db'
                }
            }
        }
    }
    
    service = ApiKeyService(config)
    
    # SQLite should use default collection name 'api_keys'
    assert service.collection_name == 'api_keys'


def test_api_key_service_mixed_backends():
    """Test that MongoDB and SQLite backends create separate instances."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    SQLiteService.clear_cache()
    
    mongodb_config = {
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
    
    sqlite_config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': 'test_sqlite.db'
                }
            }
        }
    }
    
    mongodb_service = ApiKeyService(mongodb_config)
    sqlite_service = ApiKeyService(sqlite_config)
    
    # Should be different instances
    assert mongodb_service is not sqlite_service
    
    # Should have 2 cached instances
    stats = ApiKeyService.get_cache_stats()
    assert stats['total_cached_instances'] == 2
    
    # Should have different collection names (though both default to 'api_keys')
    assert mongodb_service.collection_name == 'api_keys'
    assert sqlite_service.collection_name == 'api_keys'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])