"""
Qdrant Collection Query Tool
============================

This script queries a Qdrant vector database collection using semantic search.
It takes a query string, generates an embedding using the same provider as during creation,
and retrieves the most relevant Q&A pairs.

Usage:
    python query_qa_pairs_qdrant.py [collection_name] <query_text>

Arguments:
    collection_name      (Optional) Name of the Qdrant collection to query
                         If not provided, uses the collection specified in config.yaml
    query_text           The search query text (in quotes if it contains spaces)

Examples:
    # Query Qdrant server (basic usage)
    python query_qa_pairs_qdrant.py "What are the parking rules?"
    
    # Query specific collection on server
    python query_qa_pairs_qdrant.py city_faq "What are the parking rules?"

Requirements:
    - config.yaml file with embedding and Qdrant configuration
    - Running embedding service matching what was used during creation
    - Running Qdrant server with an existing collection

Notes:
    - The script uses server connection details from config.yaml and .env file
    - This script is part of a suite of Qdrant utilities:
      * create_qa_pairs_collection_qdrant.py - Creates and populates collections
      * query_qa_pairs_qdrant.py - Queries collections with semantic search
      * list_qdrant_collections.py - Lists available collections
      * delete_qdrant_collection.py - Deletes collections
"""

import yaml
import os
import sys
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[3] / "server"
sys.path.append(str(server_path))

# Load environment variables from server's .env file
server_env_path = server_path / ".env"
if server_env_path.exists():
    load_dotenv(server_env_path)
else:
    print(f"Warning: .env file not found at {server_env_path}")

# Import the same embedding factory used during creation
from embeddings.base import EmbeddingServiceFactory

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "server" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

async def test_qdrant_query(test_query: str, collection_name: str = None):
    config = load_config()

    # Get the same embedding provider that was used during creation
    embedding_provider = config['embedding']['provider']
    
    # Get Qdrant connection details
    qdrant_host = os.getenv('QDRANT_HOST', config['datasources']['qdrant']['host'])
    qdrant_port = int(os.getenv('QDRANT_PORT', config['datasources']['qdrant']['port']))
    
    # Print configuration variables
    print("\nConfiguration Variables:")
    print(f"Embedding Provider: {embedding_provider}")
    print(f"QDRANT_HOST: {qdrant_host}")
    print(f"QDRANT_PORT: {qdrant_port}")
    print(f"QDRANT_COLLECTION: {collection_name}\n")
    
    # Initialize Qdrant client
    try:
        client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            timeout=30
        )
        print(f"Using Qdrant server at: {qdrant_host}:{qdrant_port}")
    except Exception as e:
        print(f"Failed to connect to Qdrant server: {str(e)}")
        return
    
    # Use the same embedding service as during creation
    embedding_service = EmbeddingServiceFactory.create_embedding_service(config, embedding_provider)
    await embedding_service.initialize()
    
    print(f"Using embedding provider: {embedding_provider}")
    
    # Test connection by getting dimensions
    try:
        dimensions = await embedding_service.get_dimensions()
        print(f"Successfully connected to embedding service")
        print(f"Embedding dimensions: {dimensions}")
    except Exception as e:
        print(f"Failed to connect to embedding service: {str(e)}")
        return
    
    try:
        # Check if collection exists
        try:
            collection_info = client.get_collection(collection_name)
            print(f"Successfully connected to collection: {collection_name}")
            print(f"Collection has {collection_info.points_count} vectors")
        except Exception as e:
            print(f"Error accessing collection '{collection_name}': {str(e)}")
            print("Please make sure the collection exists. You can create it using create_qa_pairs_collection_qdrant.py")
            return
        
        # Generate embedding for query
        print(f"\nGenerating embedding for query: '{test_query}'")
        query_embedding = await embedding_service.embed_query(test_query)
        
        # Perform search
        print("\nExecuting query...")
        search_results = client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            limit=3,
            with_payload=True
        )
        
        # Print results
        print(f"\nQuery: '{test_query}'")
        
        if search_results:
            for i, result in enumerate(search_results):
                print(f"\nResult {i+1} (score: {result.score:.4f}):")
                payload = result.payload
                if 'question' in payload and 'answer' in payload:
                    print(f"Question: {payload['question']}")
                    print(f"Answer: {payload['answer']}")
                else:
                    print(f"Content: {payload.get('content', 'N/A')}")
                    print(f"Payload: {payload}")
        else:
            print("No results found")
            
    except Exception as e:
        print(f"Error during query execution: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up
        await embedding_service.close()

async def main():
    config = load_config()
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Query a Qdrant collection using semantic search')
    parser.add_argument('query_args', nargs='+', help='Collection name (optional) followed by query text')
    args = parser.parse_args()
    
    # Check if first argument might be a collection name
    if len(args.query_args) > 1:
        collection_name = args.query_args[0]
        test_query = " ".join(args.query_args[1:])
    else:
        # Use default collection from config or a default name
        collection_name = "default_collection"  # You might want to set this in config
        test_query = args.query_args[0]
    
    await test_qdrant_query(test_query, collection_name)

if __name__ == "__main__":
    asyncio.run(main())