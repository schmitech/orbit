"""
Test script to verify vector retrievers work with the new API key system.
This tests the fixes applied to ChromaRetriever and QdrantRetriever to ensure
they properly read collection names from adapter configuration.
"""

import asyncio
import logging
import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch

# Add the server directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from retrievers.implementations.vector.chroma_retriever import ChromaRetriever
from retrievers.implementations.vector.qdrant_retriever import QdrantRetriever
from retrievers.implementations.qa.qa_chroma_retriever import QAChromaRetriever
from retrievers.implementations.qa.qa_qdrant_retriever import QAQdrantRetriever
from services.dynamic_adapter_manager import DynamicAdapterManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestVectorAdapterFix:
    """Test class for vector adapter fixes"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Mock configuration with adapter configs including collection names
        self.config = {
            'general': {'verbose': True},
            'embedding': {'enabled': True, 'provider': 'ollama'},
            'datasources': {
                'chroma': {
                    'use_local': True,
                    'db_path': '/tmp/test_chroma',
                    'host': 'localhost',
                    'port': 8000
                },
                'qdrant': {
                    'host': 'localhost',
                    'port': 6333,
                    'timeout': 30
                }
            },
            'adapters': [
                {
                    'name': 'qa-vector-chroma',
                    'type': 'retriever',
                    'datasource': 'chroma',
                    'adapter': 'qa',
                    'collection': 'city',
                    'config': {
                        'confidence_threshold': 0.3,
                        'max_results': 5,
                        'return_results': 3
                    }
                },
                {
                    'name': 'qa-vector-qdrant',
                    'type': 'retriever',
                    'datasource': 'qdrant',
                    'adapter': 'qa',
                    'collection': 'city',
                    'config': {
                        'confidence_threshold': 0.3,
                        'max_results': 5,
                        'return_results': 3
                    }
                }
            ]
        }
        
        # Configuration with adapter_config for direct retriever testing
        self.adapter_config_with_collection = {
            'adapter_config': {
                'collection': 'city',
                'confidence_threshold': 0.3,
                'max_results': 5,
                'return_results': 3
            },
            'general': {'verbose': True},
            'embedding': {'enabled': True},
            'datasources': {
                'chroma': {
                    'use_local': True,
                    'db_path': '/tmp/test_chroma'
                },
                'qdrant': {
                    'host': 'localhost',
                    'port': 6333
                }
            }
        }

    def test_chroma_retriever_reads_collection_from_adapter_config(self):
        """Test that ChromaRetriever reads collection name from adapter config"""
        logger.info("Testing ChromaRetriever collection name reading from adapter config")
        
        # Create retriever with adapter config containing collection
        retriever = ChromaRetriever(
            config=self.adapter_config_with_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Verify collection name was read from adapter config
        assert retriever.collection_name == 'city', f"Expected collection_name='city', got '{retriever.collection_name}'"
        logger.info(f"✓ ChromaRetriever correctly read collection name: {retriever.collection_name}")

    def test_qdrant_retriever_reads_collection_from_adapter_config(self):
        """Test that QdrantRetriever reads collection name from adapter config"""
        logger.info("Testing QdrantRetriever collection name reading from adapter config")
        
        # Create retriever with adapter config containing collection
        retriever = QdrantRetriever(
            config=self.adapter_config_with_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Verify collection name was read from adapter config
        assert retriever.collection_name == 'city', f"Expected collection_name='city', got '{retriever.collection_name}'"
        logger.info(f"✓ QdrantRetriever correctly read collection name: {retriever.collection_name}")

    def test_qa_chroma_retriever_inherits_collection_handling(self):
        """Test that QAChromaRetriever inherits collection handling from parent"""
        logger.info("Testing QAChromaRetriever collection name inheritance")
        
        # Create QA retriever with adapter config containing collection
        retriever = QAChromaRetriever(
            config=self.adapter_config_with_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Verify collection name was read from adapter config
        assert retriever.collection_name == 'city', f"Expected collection_name='city', got '{retriever.collection_name}'"
        logger.info(f"✓ QAChromaRetriever correctly inherited collection name: {retriever.collection_name}")

    def test_qa_qdrant_retriever_inherits_collection_handling(self):
        """Test that QAQdrantRetriever inherits collection handling from parent"""
        logger.info("Testing QAQdrantRetriever collection name inheritance")
        
        # Create QA retriever with adapter config containing collection
        retriever = QAQdrantRetriever(
            config=self.adapter_config_with_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Verify collection name was read from adapter config
        assert retriever.collection_name == 'city', f"Expected collection_name='city', got '{retriever.collection_name}'"
        logger.info(f"✓ QAQdrantRetriever correctly inherited collection name: {retriever.collection_name}")

    def test_dynamic_adapter_manager_passes_collection_name(self):
        """Test that DynamicAdapterManager passes collection name from adapter config"""
        logger.info("Testing DynamicAdapterManager collection name passing")
        
        # Create adapter manager
        adapter_manager = DynamicAdapterManager(self.config)
        
        # Verify adapter configs were loaded with collection names
        qa_chroma_config = adapter_manager._adapter_configs.get('qa-vector-chroma')
        qa_qdrant_config = adapter_manager._adapter_configs.get('qa-vector-qdrant')
        
        assert qa_chroma_config is not None, "qa-vector-chroma config not found"
        assert qa_qdrant_config is not None, "qa-vector-qdrant config not found"
        
        assert qa_chroma_config['collection'] == 'city', f"Expected chroma collection='city', got '{qa_chroma_config.get('collection')}'"
        assert qa_qdrant_config['collection'] == 'city', f"Expected qdrant collection='city', got '{qa_qdrant_config.get('collection')}'"
        
        logger.info("✓ DynamicAdapterManager correctly loaded adapter configs with collection names")

    @patch('retrievers.implementations.vector.chroma_retriever.LazyLoader')
    async def test_chroma_retriever_initialization_with_collection(self, mock_lazy_loader):
        """Test ChromaRetriever initialization sets collection from config"""
        logger.info("Testing ChromaRetriever initialization with collection")
        
        # Mock the ChromaDB client
        mock_client = Mock()
        mock_collection = Mock()
        mock_client.get_collection.return_value = mock_collection
        mock_lazy_loader.return_value.get_instance.return_value = mock_client
        
        # Create retriever
        retriever = ChromaRetriever(
            config=self.adapter_config_with_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Initialize the client
        await retriever.initialize_client()
        
        # Verify collection was set during initialization
        assert retriever.collection_name == 'city'
        assert retriever.collection == mock_collection
        
        # Verify get_collection was called with correct name
        mock_client.get_collection.assert_called_with(name='city')
        
        logger.info("✓ ChromaRetriever correctly initialized with collection from config")

    @patch('qdrant_client.QdrantClient')
    async def test_qdrant_retriever_initialization_with_collection(self, mock_qdrant_client_class):
        """Test QdrantRetriever initialization sets collection from config"""
        logger.info("Testing QdrantRetriever initialization with collection")
        
        # Mock the Qdrant client
        mock_client = Mock()
        mock_collection_info = Mock()
        mock_collection_info.points_count = 100
        mock_collection_info.config = {}
        mock_client.get_collection.return_value = mock_collection_info
        mock_client.get_collections.return_value = Mock(collections=[])
        mock_qdrant_client_class.return_value = mock_client
        
        # Create retriever
        retriever = QdrantRetriever(
            config=self.adapter_config_with_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Initialize the client
        await retriever.initialize_client()
        
        # Verify collection was set during initialization
        assert retriever.collection_name == 'city'
        
        # Verify get_collection was called with correct name
        mock_client.get_collection.assert_called_with('city')
        
        logger.info("✓ QdrantRetriever correctly initialized with collection from config")

    def test_fallback_to_datasource_config_collection(self):
        """Test fallback to datasource config for collection name"""
        logger.info("Testing fallback to datasource config for collection name")
        
        # Configuration without adapter_config but with collection in datasource config
        config_with_datasource_collection = {
            'general': {'verbose': True},
            'embedding': {'enabled': True},
            'datasources': {
                'chroma': {
                    'use_local': True,
                    'db_path': '/tmp/test_chroma',
                    'collection': 'fallback_collection'
                }
            }
        }
        
        # Create retriever
        retriever = ChromaRetriever(
            config=config_with_datasource_collection,
            embeddings=Mock(),
            domain_adapter=Mock()
        )
        
        # Verify collection name was read from datasource config
        assert retriever.collection_name == 'fallback_collection', f"Expected collection_name='fallback_collection', got '{retriever.collection_name}'"
        logger.info(f"✓ ChromaRetriever correctly used fallback collection name: {retriever.collection_name}")


async def run_tests():
    """Run all tests"""
    logger.info("=== Starting Vector Adapter Fix Tests ===")
    
    test_instance = TestVectorAdapterFix()
    test_instance.setup_method()
    
    try:
        # Test collection name reading
        test_instance.test_chroma_retriever_reads_collection_from_adapter_config()
        test_instance.test_qdrant_retriever_reads_collection_from_adapter_config()
        test_instance.test_qa_chroma_retriever_inherits_collection_handling()
        test_instance.test_qa_qdrant_retriever_inherits_collection_handling()
        
        # Test adapter manager
        test_instance.test_dynamic_adapter_manager_passes_collection_name()
        
        # Test initialization (async tests)
        await test_instance.test_chroma_retriever_initialization_with_collection()
        await test_instance.test_qdrant_retriever_initialization_with_collection()
        
        # Test fallback behavior
        test_instance.test_fallback_to_datasource_config_collection()
        
        logger.info("=== All Vector Adapter Fix Tests Passed! ===")
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    if success:
        print("\n✅ All tests passed! Vector retrievers are ready for the new API key system.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the logs above.")
        sys.exit(1) 