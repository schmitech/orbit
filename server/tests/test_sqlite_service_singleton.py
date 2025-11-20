"""
Test for SQLite service singleton functionality.

This test verifies that the SQLiteService properly reuses
instances instead of creating new ones for the same configuration.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os
import tempfile
import shutil

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.sqlite_service import SQLiteService


@pytest.fixture
def mock_sqlite_config():
    """Create a mock SQLite configuration for testing."""
    temp_dir = tempfile.mkdtemp()
    return {
        'general': {
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir, 'test.db')
                }
            }
        }
    }


def test_sqlite_service_singleton_same_config(mock_sqlite_config):
    """Test that the same configuration returns the same instance."""

    # Clear any existing cache
    SQLiteService.clear_cache()

    # Create two services with same config
    service1 = SQLiteService(mock_sqlite_config)
    service2 = SQLiteService(mock_sqlite_config)

    # Should be the same instance
    assert service1 is service2

    # Verify cache stats
    stats = SQLiteService.get_cache_stats()
    assert stats['total_cached_instances'] == 1

    # Cleanup
    SQLiteService.clear_cache()


def test_sqlite_service_singleton_different_configs():
    """Test that different configurations create different instances."""

    # Clear any existing cache
    SQLiteService.clear_cache()

    temp_dir1 = tempfile.mkdtemp()
    temp_dir2 = tempfile.mkdtemp()

    config1 = {
        'general': {},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir1, 'db1.db')
                }
            }
        }
    }

    config2 = {
        'general': {},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir2, 'db2.db')  # Different database
                }
            }
        }
    }

    # Create services with different configs
    service1 = SQLiteService(config1)
    service2 = SQLiteService(config2)

    # Should be different instances
    assert service1 is not service2

    # Verify cache stats
    stats = SQLiteService.get_cache_stats()
    assert stats['total_cached_instances'] == 2

    # Cleanup
    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir1, ignore_errors=True)
    shutil.rmtree(temp_dir2, ignore_errors=True)


def test_sqlite_service_cache_key_generation():
    """Test that cache keys are generated correctly."""

    temp_dir = tempfile.mkdtemp()
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir, 'test.db')
                }
            }
        }
    }

    cache_key = SQLiteService._create_cache_key(config)
    expected_key = f'sqlite:{os.path.join(temp_dir, "test.db")}'

    assert cache_key == expected_key

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_sqlite_service_cache_key_defaults():
    """Test that cache keys handle missing configuration gracefully."""

    # Config with minimal SQLite settings
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {}  # Empty SQLite config
            }
        }
    }

    cache_key = SQLiteService._create_cache_key(config)
    expected_key = 'sqlite:orbit.db'

    assert cache_key == expected_key


def test_sqlite_service_clear_cache():
    """Test that cache clearing works properly."""

    # Clear any existing cache
    SQLiteService.clear_cache()

    temp_dir = tempfile.mkdtemp()
    config = {
        'general': {},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir, 'test.db')
                }
            }
        }
    }

    # Create a service
    service1 = SQLiteService(config)

    # Verify it's cached
    cached_instances = SQLiteService.get_cached_instances()
    assert len(cached_instances) == 1

    # Clear cache
    SQLiteService.clear_cache()

    # Verify cache is empty
    cached_instances = SQLiteService.get_cached_instances()
    assert len(cached_instances) == 0

    # Create another service - should create new instance
    service2 = SQLiteService(config)

    # Should be different instance now (new creation)
    assert service1 is not service2

    # Cleanup
    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_sqlite_service_initialization_once():
    """Test that singleton instances don't re-initialize."""

    # Clear any existing cache
    SQLiteService.clear_cache()

    temp_dir = tempfile.mkdtemp()
    config = {
        'general': {},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir, 'test.db')
                }
            }
        }
    }

    # Create first service and mark as initialized
    service1 = SQLiteService(config)
    service1._initialized = True
    service1.test_marker = "first_init"

    # Create second service with same config
    service2 = SQLiteService(config)

    # Should be same instance and retain the marker
    assert service1 is service2
    assert hasattr(service2, 'test_marker')
    assert service2.test_marker == "first_init"

    # Cleanup
    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_sqlite_service_multiple_databases():
    """Test that different database paths create different instances."""

    # Clear any existing cache
    SQLiteService.clear_cache()

    temp_dir = tempfile.mkdtemp()

    # Create configs for different databases
    configs = []
    for i in range(3):
        configs.append({
            'general': {},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {
                        'database_path': os.path.join(temp_dir, f'db{i}.db')
                    }
                }
            }
        })

    # Create services for each config
    services = [SQLiteService(config) for config in configs]

    # All should be different instances
    assert services[0] is not services[1]
    assert services[1] is not services[2]
    assert services[0] is not services[2]

    # Verify cache stats
    stats = SQLiteService.get_cache_stats()
    assert stats['total_cached_instances'] == 3

    # Cleanup
    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_sqlite_service_cache_reuse():
    """Test that accessing the same config multiple times reuses cache."""

    # Clear any existing cache
    SQLiteService.clear_cache()

    temp_dir = tempfile.mkdtemp()
    config = {
        'general': {},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(temp_dir, 'test.db')
                }
            }
        }
    }

    # Create multiple services with same config
    services = [SQLiteService(config) for _ in range(5)]

    # All should be the same instance
    for i in range(1, 5):
        assert services[0] is services[i]

    # Should only have one cached instance
    stats = SQLiteService.get_cache_stats()
    assert stats['total_cached_instances'] == 1

    # Cleanup
    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
