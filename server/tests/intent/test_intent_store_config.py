#!/usr/bin/env python3
"""
Test script to verify intent adapters can retrieve store configuration from stores.yaml
"""

import logging
import sys
from pathlib import Path

# Add the server directory to the Python path
server_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(server_dir))

from retrievers.implementations.intent.intent_sqlite_retriever import IntentSQLiteRetriever

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_store_configuration():
    """Test that intent adapters can retrieve store configuration from stores.yaml"""
    
    # Test configuration with stores.yaml data
    config = {
        'general': {
            'verbose': True,
            'inference_provider': 'ollama_cloud'
        },
        'embedding': {
            'provider': 'ollama',
            'enabled': True
        },
        'stores': {
            'vector_stores': {
                'chroma': {
                    'enabled': True,
                    'connection_params': {
                        'persist_directory': './test_chroma_db',
                        'distance_function': 'cosine',
                        'allow_reset': True
                    },
                    'pool_size': 5,
                    'timeout': 30,
                    'ephemeral': False,
                    'auto_cleanup': True
                },
                'pinecone': {
                    'enabled': True,
                    'connection_params': {
                        'api_key': '${DATASOURCE_PINECONE_API_KEY}',
                        'namespace': '',
                        'index_name': 'orbit-index'
                    },
                    'timeout': 30,
                    'cache_ttl': 1800
                },
                'qdrant': {
                    'enabled': True,
                    'connection_params': {
                        'host': '${DATASOURCE_QDRANT_HOST}',
                        'port': '${DATASOURCE_QDRANT_PORT}',
                        'api_key': '${DATASOURCE_QDRANT_API_KEY}',
                        'prefer_grpc': False,
                        'https': False
                    },
                    'timeout': 5,
                    'cache_ttl': 1800
                }
            }
        },
        'adapter_config': {
            'store_name': 'chroma',
            'template_collection_name': 'test_intent_templates',
            'confidence_threshold': 0.4,
            'max_templates': 5,
            'return_results': 10,
            'reload_templates_on_start': True,
            'force_reload_templates': True
        }
    }
    
    try:
        logger.info("Testing store configuration retrieval...")
        
        # Create retriever instance (without initializing external services)
        retriever = IntentSQLiteRetriever(config=config)
        
        # Manually set up the store manager with the config
        from vector_stores.base.store_manager import StoreManager
        retriever.store_manager = StoreManager()
        retriever.store_manager._config = config['stores']
        
        # Test ChromaDB store configuration
        logger.info("Testing ChromaDB store configuration...")
        store_config = retriever._get_store_config()
        logger.info(f"ChromaDB store config: {store_config}")
        
        # Verify ChromaDB configuration
        assert store_config['type'] == 'chroma', f"Expected store type 'chroma', got '{store_config['type']}'"
        assert 'connection_params' in store_config, "Store config should have connection_params"
        assert store_config['connection_params']['collection_name'] == 'test_intent_templates', "Collection name should match"
        assert store_config['connection_params']['persist_directory'] == './test_chroma_db', "Persist directory should come from stores.yaml"
        assert store_config['ephemeral'] == False, "Should not be ephemeral"
        assert 'pool_size' in store_config, "Should have pool_size from stores.yaml"
        assert store_config['pool_size'] == 5, "Pool size should match stores.yaml config"
        
        logger.info("✅ ChromaDB store configuration test passed!")
        
        # Test Pinecone store configuration
        logger.info("Testing Pinecone store configuration...")
        retriever.store_name = 'pinecone'
        retriever.template_collection_name = 'test_pinecone_templates'
        pinecone_config = retriever._get_store_config()
        logger.info(f"Pinecone store config: {pinecone_config}")
        
        # Verify Pinecone configuration
        assert pinecone_config['type'] == 'pinecone', f"Expected store type 'pinecone', got '{pinecone_config['type']}'"
        assert 'connection_params' in pinecone_config, "Store config should have connection_params"
        assert pinecone_config['connection_params']['collection_name'] == 'test_pinecone_templates', "Collection name should match"
        assert 'api_key' in pinecone_config['connection_params'], "Should have API key placeholder"
        assert 'namespace' in pinecone_config['connection_params'], "Should have namespace"
        assert pinecone_config['connection_params']['namespace'] == '', "Namespace should be empty string for default"

        logger.info("✅ Pinecone store configuration test passed!")

        # Test Qdrant store configuration
        logger.info("Testing Qdrant store configuration...")
        retriever.store_name = 'qdrant'
        retriever.template_collection_name = 'test_qdrant_templates'
        qdrant_config = retriever._get_store_config()
        logger.info(f"Qdrant store config: {qdrant_config}")

        # Verify Qdrant configuration
        assert qdrant_config['type'] == 'qdrant', f"Expected store type 'qdrant', got '{qdrant_config['type']}'"
        assert 'connection_params' in qdrant_config, "Store config should have connection_params"
        assert qdrant_config['connection_params']['collection_name'] == 'test_qdrant_templates', "Collection name should match"
        assert 'host' in qdrant_config['connection_params'], "Should have host"
        assert 'port' in qdrant_config['connection_params'], "Should have port"
        assert 'prefer_grpc' in qdrant_config['connection_params'], "Should have prefer_grpc"
        assert qdrant_config['connection_params']['prefer_grpc'] == False, "prefer_grpc should be False"
        assert 'https' in qdrant_config['connection_params'], "Should have https"
        assert qdrant_config['connection_params']['https'] == False, "https should be False"

        logger.info("✅ Qdrant store configuration test passed!")

        # Test error handling for unknown store
        logger.info("Testing error handling for unknown store...")
        retriever.store_name = 'unknown_store'
        retriever.template_collection_name = 'test_unknown_templates'
        
        try:
            fallback_config = retriever._get_store_config()
            assert False, "Expected ValueError for unknown store"
        except ValueError as e:
            assert "not found in stores.yaml configuration" in str(e), f"Expected store not found error, got: {e}"
            logger.info("✅ Unknown store error handling test passed!")
        
        # Test error handling with no store manager
        logger.info("Testing error handling with no store manager...")
        retriever.store_manager = None
        retriever.store_name = 'chroma'
        retriever.template_collection_name = 'test_no_manager_templates'
        
        try:
            no_manager_config = retriever._get_store_config()
            assert False, "Expected ValueError for no store manager"
        except ValueError as e:
            assert "Store manager not initialized" in str(e), f"Expected store manager error, got: {e}"
            logger.info("✅ No manager error handling test passed!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Main test function"""
    logger.info("Starting intent store configuration test...")
    
    success = test_store_configuration()
    
    if success:
        logger.info("🎉 All tests passed! Intent adapters can now use stores from stores.yaml")
        return 0
    else:
        logger.error("💥 Tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
