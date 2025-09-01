#!/usr/bin/env python3
"""
Test script to verify intent adapter integration with the new vector store system.
"""

import asyncio
import logging
import sys
import os

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from retrievers.adapters.intent.intent_adapter import IntentAdapter
from vector_stores.base.store_manager import StoreManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_intent_adapter_integration():
    """Test the intent adapter with vector store integration."""
    
    print("\n=== Testing Intent Adapter with Vector Store System ===\n")
    
    # 1. Create the intent adapter
    print("1. Creating intent adapter...")
    adapter = IntentAdapter(
        domain_config_path="config/intent/domain_config.yaml",
        template_library_path="config/intent/template_library.yaml",
        confidence_threshold=0.75,
        verbose=True
    )
    
    # Check if templates were loaded
    templates = adapter.get_all_templates()
    print(f"   - Loaded {len(templates)} templates")
    
    # 2. Create store manager
    print("\n2. Creating store manager...")
    store_manager = StoreManager()
    print("   - Store manager created")
    
    # 3. Initialize embeddings with store manager
    print("\n3. Initializing embeddings...")
    try:
        await adapter.initialize_embeddings(store_manager)
        print("   - Embeddings initialized successfully")
        
        # Check if template store was created
        if hasattr(adapter, 'template_store'):
            print("   - Template store is available")
        else:
            print("   - Warning: Template store not available")
            
    except Exception as e:
        print(f"   - Error initializing embeddings: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. Check store manager status
    print("\n4. Checking store manager status...")
    stats = store_manager.get_statistics()
    print(f"   - Registered stores: {stats.get('store_count', 0)}")
    print(f"   - Available store types: {stats.get('available_store_types', [])}")
    
    print("\n=== Test Complete ===\n")
    
    return adapter, store_manager


async def test_intent_sql_retriever():
    """Test the intent SQL retriever with vector store integration."""
    
    print("\n=== Testing Intent SQL Retriever with Vector Store System ===\n")
    
    try:
        from retrievers.implementations.intent.intent_postgresql_retriever import IntentPostgreSQLRetriever
        
        # Create configuration
        config = {
            'datasource': 'postgresql',
            'config': {
                'host': 'localhost',
                'port': 5432,
                'database': 'test_db',
                'username': 'postgres',
                'password': 'postgres',
                'template_collection_name': 'intent_templates',
                'confidence_threshold': 0.75,
                'domain_config_path': 'config/intent/domain_config.yaml',
                'template_library_path': 'config/intent/template_library.yaml',
                'vector_store': {
                    'type': 'chroma',
                    'ephemeral': True,
                    'collection_name': 'intent_templates'
                }
            },
            'inference': {
                'default_provider': 'openai'
            },
            'embeddings': {
                'default_provider': 'openai'
            }
        }
        
        print("1. Creating PostgreSQL intent retriever...")
        retriever = IntentPostgreSQLRetriever(config)
        
        print("\n2. Checking if vector store integration is active...")
        if hasattr(retriever, 'template_store'):
            print("   - Template store is available")
        else:
            print("   - Template store not initialized (will work without vector search)")
            
        if hasattr(retriever, 'store_manager'):
            print("   - Store manager is available")
        else:
            print("   - Store manager not initialized")
            
        print("\n=== Test Complete ===\n")
        
    except ImportError as e:
        print(f"Could not import IntentPostgreSQLRetriever: {e}")
        print("This is expected if the PostgreSQL retriever is not available")
    except Exception as e:
        print(f"Error testing retriever: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the tests
    asyncio.run(test_intent_adapter_integration())
    asyncio.run(test_intent_sql_retriever())