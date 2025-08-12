"""
Test that multiple initialize calls don't duplicate work.

This simulates what happens when multiple adapters each initialize
the same API key service singleton instance.
"""

import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_multiple_initialize_calls_only_run_once(mock_config):
    """Test that multiple initialize calls on same instance only run initialization once."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create an API key service
    service = ApiKeyService(mock_config)
    
    # Mock the MongoDB service and its methods
    with patch.object(service, 'mongodb') as mock_mongodb:
        mock_mongodb.initialize = AsyncMock()
        mock_mongodb.database = {'api_keys': 'mock_collection'}
        mock_mongodb.create_index = AsyncMock()
        
        # Call initialize multiple times (simulating multiple adapters)
        await service.initialize()
        await service.initialize()
        await service.initialize()
        await service.initialize()
        await service.initialize()
        
        # MongoDB initialize should only be called once
        mock_mongodb.initialize.assert_called_once()
        
        # MongoDB create_index should only be called once
        mock_mongodb.create_index.assert_called_once_with('api_keys', 'api_key', unique=True)
        
        # Service should be marked as initialized
        assert service._initialized is True


@pytest.mark.asyncio
async def test_multiple_api_key_services_same_config_share_initialization(mock_config):
    """Test that multiple API key service instances with same config share initialization."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Create multiple API key service instances (they should be the same due to singleton)
    service1 = ApiKeyService(mock_config)
    service2 = ApiKeyService(mock_config)
    service3 = ApiKeyService(mock_config)
    
    # Should be the same instance
    assert service1 is service2 is service3
    
    # Mock the MongoDB service and its methods for all instances (they're the same)
    with patch.object(service1, 'mongodb') as mock_mongodb:
        mock_mongodb.initialize = AsyncMock()
        mock_mongodb.database = {'api_keys': 'mock_collection'}
        mock_mongodb.create_index = AsyncMock()
        
        # Initialize all instances (should only run once since they're the same)
        await service1.initialize()
        await service2.initialize()  # Should be skipped
        await service3.initialize()  # Should be skipped
        
        # MongoDB initialize should only be called once
        mock_mongodb.initialize.assert_called_once()
        
        # MongoDB create_index should only be called once
        mock_mongodb.create_index.assert_called_once()
        
        # All instances should be marked as initialized
        assert service1._initialized is True
        assert service2._initialized is True
        assert service3._initialized is True


@pytest.mark.asyncio
async def test_simulated_multiple_adapters_initialization(mock_config):
    """Test simulation of multiple adapters initializing API key service."""
    
    # Clear cache
    ApiKeyService.clear_cache()
    MongoDBService.clear_cache()
    
    # Simulate multiple adapters each creating and initializing API key service
    async def simulate_adapter_initialization(adapter_name):
        # Each adapter creates an API key service (gets same singleton)
        api_key_service = ApiKeyService(mock_config)
        
        # Each adapter initializes it
        await api_key_service.initialize()
        
        return api_key_service, adapter_name
    
    # Mock MongoDB for the singleton instance that will be created
    with patch('services.api_key_service.MongoDBService') as MockMongoDB:
        mock_mongodb_instance = AsyncMock()
        mock_mongodb_instance.initialize = AsyncMock()
        mock_mongodb_instance.database = {'api_keys': 'mock_collection'}
        mock_mongodb_instance.create_index = AsyncMock()
        MockMongoDB.return_value = mock_mongodb_instance
        
        # Simulate 7 adapters (like in the actual config) initializing concurrently
        adapters = [
            'qa-sql',
            'qa-vector-chroma', 
            'qa-vector-qdrant-csedottawa',
            'qa-vector-qdrant-humane',
            'qa-vector-qdrant-city',
            'qa-vector-qdrant-crcrr',
            'file-vector'
        ]
        
        # Initialize all adapters concurrently
        results = await asyncio.gather(*[
            simulate_adapter_initialization(adapter) 
            for adapter in adapters
        ])
        
        # All should get the same API key service instance
        services = [result[0] for result in results]
        first_service = services[0]
        for service in services[1:]:
            assert service is first_service
        
        # MongoDB initialize should only be called once despite 7 adapters
        mock_mongodb_instance.initialize.assert_called_once()
        
        # Create index should only be called once
        mock_mongodb_instance.create_index.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])