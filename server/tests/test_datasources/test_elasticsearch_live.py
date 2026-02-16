#!/usr/bin/env python3
"""
Live test for Elasticsearch logging through the actual server endpoint.

This script tests if Elasticsearch is properly logging conversations when
the server is running.

NOTE: This test is excluded from the main test runner (run_tests.py) because
it depends on a running server and cloud Elasticsearch service. Run this test
manually when needed: python test_elasticsearch_live.py
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime, UTC
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import AsyncElasticsearch

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent.parent
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Configuration
SERVER_URL = "http://localhost:3001"  # Adjust port if needed
ES_NODE = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_NODE")
ES_USERNAME = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_USERNAME")
ES_PASSWORD = os.getenv("INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD")


async def test_chat_endpoint():
    """Test the chat endpoint and verify Elasticsearch logging."""
    
    print("=" * 60)
    print("Live Elasticsearch Logging Test")
    print("=" * 60)
    
    # Create test session ID
    session_id = f"test-live-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    
    # Test message
    test_message = "What is 2 + 2?"
    
    print(f"\nServer URL: {SERVER_URL}")
    print(f"Session ID: {session_id}")
    print(f"Message: {test_message}")
    
    # Make request to chat endpoint
    async with aiohttp.ClientSession() as session:
        headers = {
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
            # Optionally add API key if you have one
            # "X-API-Key": "your-api-key-here"
        }
        
        # JSON-RPC 2.0 format for MCP protocol
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat",
                "arguments": {
                    "messages": [
                        {
                            "role": "user",
                            "content": test_message
                        }
                    ],
                    "stream": False
                }
            },
            "id": "test-1"
        }
        
        print("\n=== Sending chat request ===")
        try:
            async with session.post(
                f"{SERVER_URL}/v1/chat",
                json=payload,
                headers=headers
            ) as response:
                response_data = await response.json()
                print(f"Status: {response.status}")
                print(f"Response: {json.dumps(response_data, indent=2)[:200]}...")
                
                if response.status != 200:
                    print(f"Error: Unexpected status code {response.status}")
                    return False
                
        except Exception as e:
            print(f"Error making request: {e}")
            return False
    
    # Wait a moment for Elasticsearch to index the document
    print("\n=== Waiting for Elasticsearch indexing ===")
    await asyncio.sleep(3)
    
    # Check Elasticsearch for the logged conversation
    print("\n=== Checking Elasticsearch ===")
    
    if not all([ES_NODE, ES_USERNAME, ES_PASSWORD]):
        print("Missing Elasticsearch environment variables!")
        return False
    
    # Create Elasticsearch client
    es_client = AsyncElasticsearch(
        ES_NODE,
        basic_auth=(ES_USERNAME, ES_PASSWORD),
        verify_certs=False,
        ssl_show_warn=False
    )
    
    try:
        # Check if connected
        if not await es_client.ping():
            print("Failed to connect to Elasticsearch")
            return False
        
        print(f"Connected to Elasticsearch at {ES_NODE}")
        
        # Search for the conversation
        search_result = await es_client.search(
            index="orbit",  # Use production index
            query={
                "bool": {
                    "must": [
                        {"match": {"session_id": session_id}}
                    ]
                }
            },
            size=10,
            sort=[{"timestamp": {"order": "desc"}}]
        )
        
        hits = search_result["hits"]["total"]["value"]
        print(f"\nFound {hits} document(s) with session ID: {session_id}")
        
        if hits > 0:
            print("\n✓ SUCCESS: Conversation was logged to Elasticsearch!")
            for i, hit in enumerate(search_result["hits"]["hits"], 1):
                doc = hit["_source"]
                print(f"\nDocument {i}:")
                print(f"  - Timestamp: {doc.get('timestamp', 'N/A')}")
                print(f"  - Session ID: {doc.get('session_id', 'N/A')}")
                print(f"  - Query: {doc.get('query', 'N/A')[:50]}...")
                print(f"  - Response: {doc.get('response', 'N/A')[:50]}...")
                print(f"  - Backend: {doc.get('backend', 'N/A')}")
                print(f"  - IP: {doc.get('ip', 'N/A')}")
                print(f"  - API Key: {doc.get('api_key', {}).get('key', 'N/A')}")
                print(f"  - User ID: {doc.get('user_id', 'N/A')}")
        else:
            print("\n✗ FAILED: No documents found in Elasticsearch")
            print("\nPossible issues:")
            print("  1. Elasticsearch logging might not be enabled")
            print("  2. The logger service might not be initialized")
            print("  3. The conversation might not have been logged")
            
            # Try to get all recent documents
            print("\n=== Recent documents in index ===")
            all_docs = await es_client.search(
                index="orbit",
                query={"match_all": {}},
                size=5,
                sort=[{"timestamp": {"order": "desc"}}]
            )
            
            total_docs = all_docs["hits"]["total"]["value"]
            print(f"Total documents in index: {total_docs}")
            
            if total_docs > 0:
                print("\nMost recent documents:")
                for i, hit in enumerate(all_docs["hits"]["hits"], 1):
                    doc = hit["_source"]
                    print(f"  {i}. Session: {doc.get('session_id', 'N/A')[:30]}... - Time: {doc.get('timestamp', 'N/A')}")
        
    except Exception as e:
        print(f"Error querying Elasticsearch: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await es_client.close()
    
    print("\n" + "=" * 60)
    return True


async def main():
    """Run the live test."""
    success = await test_chat_endpoint()
    
    if success:
        print("✓ Elasticsearch logging is working correctly!")
    else:
        print("✗ Elasticsearch logging test failed")
        print("\nTroubleshooting steps:")
        print("  1. Ensure the server is running on port 3001")
        print("  2. Check that Elasticsearch is enabled in config.yaml")
        print("  3. Verify Elasticsearch credentials in .env file")
        print("  4. Check server logs for any errors")


if __name__ == "__main__":
    asyncio.run(main())