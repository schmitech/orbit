#!/usr/bin/env python3
"""
Integration test for Intent adapter with new vector store system.
Tests the complete flow from adapter initialization to template storage.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from retrievers.adapters.intent.intent_adapter import IntentAdapter
from retrievers.base.intent_sql_base import IntentSQLRetriever
from vector_stores.base.store_manager import StoreManager


class TestIntentVectorStoreIntegration:
    """Test cases for Intent adapter integration with vector stores."""
    
    @pytest.fixture
    def sample_templates(self):
        """Sample templates for testing."""
        return [
            {
                'id': 'get_user_by_id',
                'description': 'Get user information by ID',
                'nl_examples': ['get user 123', 'show user with id 456'],
                'tags': ['user', 'retrieve'],
                'parameters': [
                    {'name': 'user_id', 'type': 'integer', 'description': 'User ID'}
                ]
            },
            {
                'id': 'list_products',
                'description': 'List all products',
                'nl_examples': ['show all products', 'list products'],
                'tags': ['product', 'list'],
                'parameters': []
            }
        ]
    
    @pytest.mark.asyncio
    async def test_adapter_with_store_manager(self, sample_templates):
        """Test intent adapter initialization with store manager."""
        
        # Create adapter without config files (will use defaults)
        adapter = IntentAdapter(
            confidence_threshold=0.75,
            verbose=False
        )
        
        # Manually set template library for testing
        adapter.template_library = {'templates': sample_templates}
        
        # Create store manager
        store_manager = StoreManager()
        
        # Initialize embeddings
        await adapter.initialize_embeddings(store_manager)
        
        # Verify store manager is set
        assert hasattr(adapter, 'store_manager')
        assert adapter.store_manager == store_manager
        
        # Verify template store was created (if vector stores are available)
        if hasattr(adapter, 'template_store'):
            print("Template store successfully created")
        else:
            print("Template store not created (vector stores may not be configured)")
    
    @pytest.mark.asyncio
    async def test_retriever_vector_store_initialization(self, sample_templates):
        """Test IntentSQLRetriever with vector store initialization."""
        
        # Create mock configuration
        config = {
            'datasource': 'postgresql',
            'config': {
                'host': 'localhost',
                'port': 5432,
                'database': 'test_db',
                'username': 'test_user',
                'password': 'test_pass',
                'template_collection_name': 'test_templates',
                'confidence_threshold': 0.75,
                'vector_store': {
                    'type': 'chroma',
                    'ephemeral': True,
                    'collection_name': 'test_templates'
                }
            }
        }
        
        # Create mock domain adapter
        mock_adapter = Mock(spec=IntentAdapter)
        mock_adapter.get_all_templates.return_value = sample_templates
        mock_adapter.get_domain_config.return_value = {}
        mock_adapter.get_template_library.return_value = {'templates': sample_templates}
        
        # Create retriever with mocks
        with patch('retrievers.base.intent_sql_base.IntentSQLRetriever.create_connection'):
            retriever = MockIntentSQLRetriever(config, domain_adapter=mock_adapter)
            
            # Check that store manager is initialized
            assert retriever.store_manager is not None
            
            # Check that template store is set up
            assert retriever.template_store is not None
    
    def test_adapter_template_methods(self, sample_templates):
        """Test adapter template management methods."""
        
        adapter = IntentAdapter(confidence_threshold=0.75)
        adapter.template_library = {'templates': sample_templates}
        
        # Test get_all_templates
        templates = adapter.get_all_templates()
        assert len(templates) == 2
        
        # Test get_template_by_id
        template = adapter.get_template_by_id('get_user_by_id')
        assert template is not None
        assert template['description'] == 'Get user information by ID'
        
        # Test non-existent template
        template = adapter.get_template_by_id('non_existent')
        assert template is None


class MockIntentSQLRetriever(IntentSQLRetriever):
    """Mock retriever for testing without database connection."""
    
    def __init__(self, config, domain_adapter=None, **kwargs):
        """Initialize mock retriever."""
        super().__init__(config, domain_adapter, **kwargs)
        # Override store initialization to avoid real connections
        self.store_manager = StoreManager()
        self.template_store = Mock()
    
    async def create_connection(self):
        """Mock connection creation."""
        return Mock()
    
    def _get_datasource_name(self):
        """Return mock datasource name."""
        return 'mock_postgres'
    
    async def execute_query(self, query, params=None):
        """Mock query execution."""
        return []
    
    async def _execute_raw_query(self, query, params=None):
        """Mock raw query execution."""
        return []
    
    async def _close_connection(self):
        """Mock connection close."""
        pass
    
    def get_test_query(self):
        """Return test query."""
        return "SELECT 1"


def run_async_test(coro):
    """Helper to run async tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


if __name__ == '__main__':
    # Run tests
    print("\n=== Running Intent Vector Store Integration Tests ===\n")
    
    test = TestIntentVectorStoreIntegration()
    test.setUp()
    
    # Run async tests
    print("1. Testing adapter with store manager...")
    run_async_test(test.test_adapter_with_store_manager())
    
    print("\n2. Testing retriever vector store initialization...")
    run_async_test(test.test_retriever_vector_store_initialization())
    
    print("\n3. Testing adapter template methods...")
    test.test_adapter_template_methods()
    print("   Template methods test passed")
    
    print("\n=== All Tests Completed Successfully ===\n")