#!/usr/bin/env python3
"""
Test script to verify intent adapters can use stores from stores.yaml
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add the server directory to the Python path
server_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(server_dir))

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.implementations.intent.intent_sqlite_retriever import IntentSQLiteRetriever

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_intent_store_integration():
    """Test that intent adapters can use stores from stores.yaml"""
    
    # Test configuration
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
                    'default_config': {
                        'store_type': 'vector',
                        'connection_params': {
                            'persist_directory': './test_chroma_db',
                            'distance_function': 'cosine',
                            'allow_reset': True
                        },
                        'pool_size': 5,
                        'timeout': 30,
                        'ephemeral': False,
                        'auto_cleanup': True
                    }
                }
            }
        },
        'adapter_config': {
            'store_name': 'chroma',
            'template_collection_name': 'test_intent_templates',
            'confidence_threshold': 0.4,
            'max_templates': 5,
            'return_results': 10,
            'chroma_persist': True,
            'chroma_persist_path': './test_chroma_db/test_intent_templates',
            'reload_templates_on_start': True,
            'force_reload_templates': True,
            'domain_config_path': '../../config/sql_intent_templates/examples/classified-data/classified_data_domain.yaml',
            'template_library_path': [
                '../../config/sql_intent_templates/examples/classified-data/sqlite_classified_data_templates.yaml'
            ]
        }
    }
    
    try:
        logger.info("Testing IntentSQLiteRetriever with store integration...")
        
        # Create retriever instance
        retriever = IntentSQLiteRetriever(config=config)
        
        # Test store configuration retrieval
        store_config = retriever._get_store_config()
        logger.info(f"Store config: {store_config}")
        
        # Verify store configuration is correct
        assert store_config['type'] == 'chroma', f"Expected store type 'chroma', got '{store_config['type']}'"
        assert 'connection_params' in store_config, "Store config should have connection_params"
        assert store_config['connection_params']['collection_name'] == 'test_intent_templates', "Collection name should match"
        
        logger.info("✅ Store configuration test passed!")
        
        # Test initialization (this will test the full integration)
        logger.info("Testing retriever initialization...")
        await retriever.initialize()
        
        logger.info("✅ Retriever initialization test passed!")
        
        # Test that template store was created
        assert retriever.template_store is not None, "Template store should be initialized"
        assert retriever.store_manager is not None, "Store manager should be initialized"
        
        logger.info("✅ Template store integration test passed!")
        
        # Clean up
        await retriever.close()
        logger.info("✅ Cleanup completed!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def main():
    """Main test function"""
    logger.info("Starting intent store integration test...")
    
    success = await test_intent_store_integration()
    
    if success:
        logger.info("🎉 All tests passed! Intent adapters can now use stores from stores.yaml")
        return 0
    else:
        logger.error("💥 Tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
