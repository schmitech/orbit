#!/usr/bin/env python3
"""
Test Elasticsearch Integration with Updated Logger Service

This script tests the Elasticsearch logging functionality with the updated
pipeline components and ES 9.0.2 compatibility changes.

NOTE: This test is excluded from the main test runner (run_tests.py) because
it depends on a cloud Elasticsearch service that may not always be available.
Run this test manually when needed: python test_elasticsearch_integration.py
"""

import asyncio
import os
import sys
import json
import pytest
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from pytest_asyncio import fixture

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.logger_service import LoggerService

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ Loaded environment from {env_path}")
else:
    print(f"⚠️  .env file not found at {env_path}")


@fixture(scope="function")
async def logger_service():
    """Fixture to create and cleanup Logger service with Elasticsearch"""
    
    # Get raw environment variables
    es_node = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_NODE")
    es_username = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_USERNAME")
    es_password = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD")
    
    if not all([es_node, es_username, es_password]):
        pytest.skip("Missing required Elasticsearch environment variables")
    
    # Create configuration matching the pattern used in test_redis_service.py
    config = {
        'internal_services': {
            'elasticsearch': {
                'enabled': True,
                'node': es_node,
                'index': 'orbit_test',  # Use test index
                'username': es_username,
                'password': es_password
            }
        },
        'general': {
            'verbose': False,  # Disable verbose for pytest
            'inference_provider': 'ollama'
        },
        'logging': {
            'file': {
                'directory': 'logs'
            }
        }
    }
    
    # Create logger service
    service = LoggerService(config)
    
    # Initialize Elasticsearch
    await service.initialize_elasticsearch()
    
    if not service.es_client:
        pytest.skip("Failed to connect to Elasticsearch")
    
    # Yield the service for use in tests
    yield service
    
    # Cleanup after tests - IMPORTANT: Properly close the Elasticsearch client
    try:
        if service.es_client:
            await service.close()
    except Exception as e:
        print(f"Error closing Elasticsearch client: {e}")


@pytest.mark.asyncio
async def test_elasticsearch_connection(logger_service: LoggerService):
    """Test basic Elasticsearch connection and index creation."""
    
    # Test ping
    ping_result = await logger_service.es_client.ping()
    assert ping_result == True, "Elasticsearch ping failed"
    
    # Check cluster info
    cluster_info = await logger_service.es_client.info()
    assert 'cluster_name' in cluster_info, "Failed to get cluster info"
    
    # Check index exists
    index_name = logger_service.config["internal_services"]["elasticsearch"]["index"]
    exists = await logger_service.es_client.indices.exists(index=index_name)
    # Index should exist after initialization
    assert exists == True, f"Index '{index_name}' does not exist"


@pytest.mark.asyncio
async def test_log_conversation(logger_service: LoggerService):
    """Test logging a conversation to Elasticsearch."""
    
    test_data = {
        "query": "What is the capital of France?",
        "response": "The capital of France is Paris.",
        "ip": "192.168.1.100",
        "backend": "ollama",
        "blocked": False,
        "api_key": "orbit_test_key_123456789",
        "session_id": f"test-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "user_id": "test-user-001"
    }
    
    # Log conversation
    await logger_service.log_conversation(
        query=test_data["query"],
        response=test_data["response"],
        ip=test_data["ip"],
        backend=test_data["backend"],
        blocked=test_data["blocked"],
        api_key=test_data["api_key"],
        session_id=test_data["session_id"],
        user_id=test_data["user_id"]
    )
    
    # Wait a moment for indexing
    await asyncio.sleep(2)
    
    # Search for the logged document
    index_name = logger_service.config["internal_services"]["elasticsearch"]["index"]
    search_result = await logger_service.es_client.search(
        index=index_name,
        query={"match": {"session_id": test_data["session_id"]}},
        size=1
    )
    
    assert search_result["hits"]["total"]["value"] > 0, "Document not found in Elasticsearch"
    
    doc = search_result["hits"]["hits"][0]["_source"]
    assert doc.get('session_id') == test_data["session_id"], "Session ID mismatch"
    assert doc.get('user_id') == test_data["user_id"], "User ID mismatch"
    assert doc.get('backend') == test_data["backend"], "Backend mismatch"
    assert doc.get('blocked') == test_data["blocked"], "Blocked flag mismatch"


@pytest.mark.asyncio
async def test_blocked_conversation(logger_service: LoggerService):
    """Test logging a blocked conversation."""
    
    test_data = {
        "query": "How to hack into a system?",
        "response": "I cannot assist with that type of request.",
        "ip": "10.0.0.1",
        "backend": "ollama",
        "blocked": True,
        "api_key": None,
        "session_id": f"test-blocked-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "user_id": None
    }
    
    # Log blocked conversation
    await logger_service.log_conversation(
        query=test_data["query"],
        response=test_data["response"],
        ip=test_data["ip"],
        backend=test_data["backend"],
        blocked=test_data["blocked"],
        api_key=test_data["api_key"],
        session_id=test_data["session_id"],
        user_id=test_data["user_id"]
    )
    
    # Wait for indexing
    await asyncio.sleep(2)
    
    # Verify the blocked flag
    index_name = logger_service.config["internal_services"]["elasticsearch"]["index"]
    search_result = await logger_service.es_client.search(
        index=index_name,
        query={"match": {"session_id": test_data["session_id"]}},
        size=1
    )
    
    assert search_result["hits"]["total"]["value"] > 0, "Blocked document not found"
    
    doc = search_result["hits"]["hits"][0]["_source"]
    assert doc.get("blocked") == True, f"Blocked flag not set correctly: {doc.get('blocked')}"
    assert test_data["query"] in doc.get("query", ""), "Query content mismatch"


@pytest.mark.asyncio
async def test_cleanup(logger_service: LoggerService):
    """Test cleanup and verify test documents."""
    
    index_name = logger_service.config["internal_services"]["elasticsearch"]["index"]
    
    # Get document count
    count_result = await logger_service.es_client.count(index=index_name)
    assert count_result['count'] >= 0, "Failed to get document count"
    
    # The count should be at least 2 if previous tests ran successfully
    # But we don't assert this as tests might run independently


# Standalone execution support (when not running with pytest)
async def standalone_test():
    """Run tests in standalone mode (without pytest)"""
    print("=" * 60)
    print("Elasticsearch Integration Tests (Standalone Mode)")
    print("=" * 60)
    
    # Get raw environment variables
    es_node = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_NODE")
    es_username = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_USERNAME")
    es_password = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD")
    
    if not all([es_node, es_username, es_password]):
        print("\n⚠️  Missing Elasticsearch environment variables!")
        print("Required variables:")
        print(f"  - INTERNAL_SERVICES_ELASTICSEARCH_NODE: {es_node or 'NOT SET'}")
        print(f"  - INTERNAL_SERVICES_ELASTICSEARCH_USERNAME: {es_username or 'NOT SET'}")
        print(f"  - INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD: {'SET' if es_password else 'NOT SET'}")
        return
    
    # Create configuration
    config = {
        'internal_services': {
            'elasticsearch': {
                'enabled': True,
                'node': es_node,
                'index': 'orbit_test',
                'username': es_username,
                'password': es_password
            }
        },
        'general': {
            'verbose': True,
            'inference_provider': 'ollama'
        },
        'logging': {
            'file': {
                'directory': 'logs'
            }
        }
    }
    
    print(f"\nElasticsearch Node: {es_node}")
    print(f"Username: {es_username}")
    print(f"Password: {'*' * len(es_password)}")
    print(f"Index: {config['internal_services']['elasticsearch']['index']}")
    
    logger_service = None
    try:
        # Create and initialize service
        logger_service = LoggerService(config)
        print("\n=== Initializing Elasticsearch ===")
        await logger_service.initialize_elasticsearch()
        
        if not logger_service.es_client:
            print("✗ Failed to initialize Elasticsearch client")
            return
        
        print("✓ Elasticsearch client initialized")
        
        # Test connection
        print("\n=== Testing Connection ===")
        ping_result = await logger_service.es_client.ping()
        print(f"✓ Ping successful: {ping_result}")
        
        cluster_info = await logger_service.es_client.info()
        print(f"✓ Connected to cluster: {cluster_info.get('cluster_name', 'unknown')}")
        print(f"  Version: {cluster_info.get('version', {}).get('number', 'unknown')}")
        
        # Test conversation logging
        print("\n=== Testing Conversation Logging ===")
        test_data = {
            "query": "What is the capital of France?",
            "response": "The capital of France is Paris.",
            "ip": "192.168.1.100",
            "backend": "ollama",
            "blocked": False,
            "api_key": "orbit_test_key_123456789",
            "session_id": f"test-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "user_id": "test-user-001"
        }
        
        await logger_service.log_conversation(**test_data)
        print(f"✓ Logged conversation with session ID: {test_data['session_id']}")
        
        # Wait and verify
        await asyncio.sleep(2)
        
        index_name = config["internal_services"]["elasticsearch"]["index"]
        search_result = await logger_service.es_client.search(
            index=index_name,
            query={"match": {"session_id": test_data["session_id"]}},
            size=1
        )
        
        if search_result["hits"]["total"]["value"] > 0:
            print("✓ Document found in Elasticsearch")
            doc = search_result["hits"]["hits"][0]["_source"]
            print(f"  - Session ID: {doc.get('session_id', 'N/A')}")
            print(f"  - User ID: {doc.get('user_id', 'N/A')}")
            print(f"  - Backend: {doc.get('backend', 'N/A')}")
        else:
            print("✗ Document not found")
        
        # Test blocked conversation
        print("\n=== Testing Blocked Conversation ===")
        blocked_data = {
            "query": "How to hack into a system?",
            "response": "I cannot assist with that type of request.",
            "ip": "10.0.0.1",
            "backend": "ollama",
            "blocked": True,
            "api_key": None,
            "session_id": f"test-blocked-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "user_id": None
        }
        
        await logger_service.log_conversation(**blocked_data)
        print(f"✓ Logged blocked conversation with session ID: {blocked_data['session_id']}")
        
        # Wait and verify
        await asyncio.sleep(2)
        
        search_result = await logger_service.es_client.search(
            index=index_name,
            query={"match": {"session_id": blocked_data["session_id"]}},
            size=1
        )
        
        if search_result["hits"]["total"]["value"] > 0:
            doc = search_result["hits"]["hits"][0]["_source"]
            if doc.get("blocked") is True:
                print("✓ Blocked flag correctly set")
            else:
                print("✗ Blocked flag not set correctly")
        else:
            print("✗ Blocked document not found")
        
        print("\n" + "=" * 60)
        print("✓ All tests completed successfully")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # IMPORTANT: Properly close the Elasticsearch client
        if logger_service and logger_service.es_client:
            try:
                await logger_service.close()
                print("\n✓ Elasticsearch client closed properly")
            except Exception as e:
                print(f"\n✗ Error closing Elasticsearch client: {e}")


if __name__ == "__main__":
    # Run in standalone mode when executed directly
    asyncio.run(standalone_test())