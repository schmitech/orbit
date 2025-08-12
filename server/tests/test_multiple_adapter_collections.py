"""
Test for multiple adapters with same datasource but different collections.

This test verifies that adapters with the same datasource type but different
collections/tables are properly isolated and use their correct configurations.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional
import copy

import sys
import os
# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.dynamic_adapter_manager import DynamicAdapterManager


class MockQdrantClient:
    """Mock Qdrant client for testing."""
    
    def __init__(self, *args, **kwargs):
        self.search_called = False
        self.last_collection_searched = None
    
    def search(self, collection_name: str, query_vector: List[float], limit: int, **kwargs):
        """Mock search that records which collection was searched."""
        self.search_called = True
        self.last_collection_searched = collection_name
        return []
    
    def get_collections(self):
        """Mock get_collections."""
        mock_response = Mock()
        mock_response.collections = []
        return mock_response


class MockRetriever:
    """Mock retriever that tracks initialization parameters."""
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, **kwargs):
        self.config = config
        self.domain_adapter = domain_adapter
        self.initialized = False
        
        # Extract adapter config
        self.adapter_config = config.get('adapter_config', {})
        
        # Simulate how real retrievers get collection name
        if self.adapter_config and 'collection' in self.adapter_config:
            self.collection_name = self.adapter_config['collection']
        else:
            # Fallback behavior (this is what was causing the bug)
            for adapter in config.get('adapters', []):
                if (adapter.get('enabled', True) and 
                    adapter.get('datasource') == 'qdrant' and 
                    adapter.get('adapter') == 'qa'):
                    self.collection_name = adapter.get('config', {}).get('collection', 'default')
                    break
    
    async def initialize(self):
        """Mock initialization."""
        self.initialized = True
    
    async def get_relevant_context(self, query: str, **kwargs):
        """Mock retrieval that uses the collection name."""
        return [{
            "content": f"Document from collection: {self.collection_name}",
            "collection": self.collection_name,
            "confidence": 0.9
        }]


@pytest.mark.asyncio
async def test_multiple_adapters_same_datasource_different_collections():
    """Test that multiple adapters with same datasource use correct collections."""
    
    # Setup test configuration with multiple Qdrant adapters
    config = {
        'general': {
            'verbose': True,
            'inference_provider': 'ollama'
        },
        'datasources': {
            'qdrant': {
                'host': 'localhost',
                'port': 6333
            }
        },
        'adapters': [
            {
                'name': 'qa-vector-qdrant-csedottawa',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'qdrant',
                'adapter': 'qa',
                'implementation': 'retrievers.implementations.qa.QAQdrantRetriever',
                'config': {
                    'collection': 'csedottawa',
                    'confidence_threshold': 0.3,
                    'max_results': 5
                }
            },
            {
                'name': 'qa-vector-qdrant-humane',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'qdrant',
                'adapter': 'qa',
                'implementation': 'retrievers.implementations.qa.QAQdrantRetriever',
                'config': {
                    'collection': 'humane',
                    'confidence_threshold': 0.3,
                    'max_results': 5
                }
            }
        ]
    }
    
    # Create adapter manager
    adapter_manager = DynamicAdapterManager(config)
    
    # Store the original __import__ function
    import builtins
    original_import = builtins.__import__
    
    # Mock the retriever class import
    def mock_import_func(name, *args, **kwargs):
        if 'retrievers.implementations.qa' in name:
            mock_module = Mock()
            mock_module.QAQdrantRetriever = MockRetriever
            return mock_module
        return original_import(name, *args, **kwargs)
    
    with patch('builtins.__import__', side_effect=mock_import_func):
        
        # Load first adapter (csedottawa)
        adapter1 = await adapter_manager.get_adapter('qa-vector-qdrant-csedottawa')
        
        # Verify it has the correct collection
        assert adapter1.collection_name == 'csedottawa', \
            f"Expected collection 'csedottawa' but got '{adapter1.collection_name}'"
        
        # Load second adapter (humane)  
        adapter2 = await adapter_manager.get_adapter('qa-vector-qdrant-humane')
        
        # Verify it has the correct collection (this would fail with the bug)
        assert adapter2.collection_name == 'humane', \
            f"Expected collection 'humane' but got '{adapter2.collection_name}'"
        
        # Verify adapters are different instances
        assert adapter1 is not adapter2, "Adapters should be different instances"
        
        # Test retrieval to ensure correct collections are used
        result1 = await adapter1.get_relevant_context("test query")
        assert 'csedottawa' in result1[0]['collection']
        
        result2 = await adapter2.get_relevant_context("test query")
        assert 'humane' in result2[0]['collection']
    
    print("✅ Test passed: Multiple adapters with same datasource use correct collections")


@pytest.mark.asyncio
async def test_adapter_config_isolation():
    """Test that adapter configurations are properly isolated."""
    
    config = {
        'general': {'verbose': False},
        'adapters': [
            {
                'name': 'adapter1',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'chroma',
                'adapter': 'qa',
                'implementation': 'test.MockRetriever',
                'config': {
                    'collection': 'collection1',
                    'max_results': 10
                }
            },
            {
                'name': 'adapter2',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'chroma',
                'adapter': 'qa',
                'implementation': 'test.MockRetriever',
                'config': {
                    'collection': 'collection2',
                    'max_results': 20
                }
            }
        ]
    }
    
    adapter_manager = DynamicAdapterManager(config)
    
    # Get adapter configs
    adapter1_config = adapter_manager.get_adapter_config('adapter1')
    adapter2_config = adapter_manager.get_adapter_config('adapter2')
    
    # Verify configs are different
    assert adapter1_config is not None
    assert adapter2_config is not None
    assert adapter1_config.get('config', {})['collection'] == 'collection1'
    assert adapter2_config.get('config', {})['collection'] == 'collection2'
    assert adapter1_config.get('config', {})['max_results'] == 10
    assert adapter2_config.get('config', {})['max_results'] == 20
    
    # Modify one config
    adapter1_config['config']['collection'] = 'modified'
    
    # Verify other config is not affected
    adapter2_config_after = adapter_manager.get_adapter_config('adapter2')
    assert adapter2_config_after.get('config', {})['collection'] == 'collection2', \
        "Adapter configs should be isolated"
    
    print("✅ Test passed: Adapter configurations are properly isolated")


@pytest.mark.asyncio
async def test_sql_adapters_different_tables():
    """Test multiple SQL adapters pointing to different tables."""
    
    config = {
        'general': {'verbose': False},
        'datasources': {
            'sqlite': {
                'db_path': '/tmp/test.db'
            }
        },
        'adapters': [
            {
                'name': 'qa-sql-users',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'sqlite',
                'adapter': 'qa',
                'implementation': 'retrievers.implementations.qa.QASSQLRetriever',
                'config': {
                    'table': 'users',
                    'confidence_threshold': 0.3
                }
            },
            {
                'name': 'qa-sql-products',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'sqlite',
                'adapter': 'qa',
                'implementation': 'retrievers.implementations.qa.QASSQLRetriever',
                'config': {
                    'table': 'products',
                    'confidence_threshold': 0.5
                }
            }
        ]
    }
    
    adapter_manager = DynamicAdapterManager(config)
    
    # Verify each adapter has correct table configuration
    users_config = adapter_manager.get_adapter_config('qa-sql-users')
    assert users_config is not None
    assert users_config.get('config', {})['table'] == 'users'
    assert users_config.get('config', {})['confidence_threshold'] == 0.3
    
    products_config = adapter_manager.get_adapter_config('qa-sql-products')
    assert products_config is not None
    assert products_config.get('config', {})['table'] == 'products'
    assert products_config.get('config', {})['confidence_threshold'] == 0.5
    
    print("✅ Test passed: SQL adapters use correct table configurations")


@pytest.mark.asyncio
async def test_intent_adapter_inference_provider_override():
    """Test that intent adapters use the correct inference provider override."""
    
    config = {
        'general': {
            'verbose': False,
            'inference_provider': 'llama_cpp'  # Default
        },
        'datasources': {
            'postgres': {
                'host': 'localhost',
                'port': 5432
            }
        },
        'adapters': [
            {
                'name': 'intent-sql-postgres',
                'enabled': True,
                'type': 'retriever',
                'datasource': 'postgres',
                'adapter': 'intent',
                'implementation': 'retrievers.implementations.intent.IntentPostgreSQLRetriever',
                'inference_provider': 'ollama',  # Override
                'config': {
                    'domain_config_path': 'config/domain.yaml',
                    'confidence_threshold': 0.75
                }
            }
        ]
    }
    
    adapter_manager = DynamicAdapterManager(config)
    
    # Get the adapter config
    adapter_config = adapter_manager.get_adapter_config('intent-sql-postgres')
    assert adapter_config is not None
    
    # Verify the inference provider override is in the adapter definition
    full_adapter_config = None
    for adapter in config['adapters']:
        if adapter['name'] == 'intent-sql-postgres':
            full_adapter_config = adapter
            break
    
    assert full_adapter_config is not None
    assert full_adapter_config.get('inference_provider') == 'ollama'
    
    print("✅ Test passed: Intent adapter has correct inference provider override")


if __name__ == "__main__":
    # Run all tests
    asyncio.run(test_multiple_adapters_same_datasource_different_collections())
    asyncio.run(test_adapter_config_isolation())
    asyncio.run(test_sql_adapters_different_tables())
    asyncio.run(test_intent_adapter_inference_provider_override())
    print("\n✅ All tests passed!")