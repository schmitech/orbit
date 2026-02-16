"""
Pinecone Index Query Tool
=========================

This script queries a Pinecone vector database index using semantic search.
It takes a query string, generates an embedding using the same provider as during creation,
and retrieves the most relevant Q&A pairs.

Usage:
    python query_pinecone_index.py [index_name] <query_text>

Arguments:
    index_name           (Optional) Name of the Pinecone index to query
                         If not provided, uses the first available index
    query_text           The search query text (in quotes if it contains spaces)

Examples:
    # Query Pinecone index (basic usage)
    python query_pinecone_index.py "What are the parking rules?"
    
    # Query specific index
    python query_pinecone_index.py city-faq "What are the parking rules?"

Requirements:
    - config.yaml file with embedding configuration
    - DATASOURCE_PINECONE_API_KEY environment variable set
    - Running embedding service matching what was used during creation
    - Existing Pinecone index with data

Notes:
    - Requires DATASOURCE_PINECONE_API_KEY environment variable to be set
    - The script uses embedding configuration from config.yaml and embeddings.yaml
    - This script is part of a suite of Pinecone utilities:
      * create_pinecone_index.py - Creates and populates indexes
      * query_pinecone_index.py - Queries indexes with semantic search
      * list_pinecone_indexes.py - Lists available indexes
      * delete_pinecone_index.py - Deletes indexes
"""

import yaml
import os
import sys
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[2] / "server"
sys.path.append(str(server_path))

# Load environment variables from main project directory
project_env_path = Path(__file__).resolve().parents[2] / ".env"
if project_env_path.exists():
    load_dotenv(project_env_path)
    print(f"Loading environment variables from: {project_env_path}")
else:
    print(f"Warning: .env file not found at {project_env_path}")

# Import the same embedding factory used during creation
from embeddings.base import EmbeddingServiceFactory

def load_config():
    """Load configuration files from project root"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Get the project root (2 levels up: examples -> pinecone -> project_root)
    project_root = script_dir.parents[1]
    
    # Load main config.yaml
    config_path = project_root / "config" / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")
    
    print(f"Loading config from: {config_path}")
    config = yaml.safe_load(config_path.read_text())
    
    # Load datasources.yaml
    datasources_path = project_root / "config" / "datasources.yaml"
    if not datasources_path.exists():
        raise FileNotFoundError(f"Datasources config file not found at {datasources_path}")
    
    print(f"Loading datasources config from: {datasources_path}")
    datasources_config = yaml.safe_load(datasources_path.read_text())
    
    # Load embeddings.yaml
    embeddings_path = project_root / "config" / "embeddings.yaml"
    if not embeddings_path.exists():
        raise FileNotFoundError(f"Embeddings config file not found at {embeddings_path}")
    
    print(f"Loading embeddings config from: {embeddings_path}")
    embeddings_config = yaml.safe_load(embeddings_path.read_text())
    
    # Merge datasources and embeddings into main config
    config['datasources'] = datasources_config['datasources']
    config['embeddings'] = embeddings_config['embeddings']
    
    # Also merge the embedding provider config if it exists
    if 'embedding' in embeddings_config:
        config['embedding'] = embeddings_config['embedding']
    
    return config

def get_pinecone_client():
    """Initialize and return Pinecone client"""
    api_key = os.getenv('DATASOURCE_PINECONE_API_KEY')
    if not api_key:
        raise ValueError("DATASOURCE_PINECONE_API_KEY environment variable not set")
    
    pc = Pinecone(api_key=api_key)
    return pc

async def test_pinecone_query(test_query: str, index_name: str = None):
    config = load_config()

    # Get the same embedding provider that was used during creation
    embedding_provider = config['embedding']['provider']
    
    # Print configuration variables
    print("\nConfiguration Variables:")
    print(f"Embedding Provider: {embedding_provider}")
    print(f"PINECONE_INDEX: {index_name}\n")
    
    # Initialize Pinecone client
    try:
        pc = get_pinecone_client()
        print("Connected to Pinecone service")
        
        # If no index name provided, use the first available index
        if not index_name:
            indexes = pc.list_indexes()
            if not indexes:
                print("No indexes found in Pinecone. Please create an index first.")
                return
            index_name = indexes[0].name
            print(f"No index specified, using: {index_name}")
    except Exception as e:
        print(f"Failed to connect to Pinecone service: {str(e)}")
        return
    
    # Use the same embedding service as during creation
    embedding_service = EmbeddingServiceFactory.create_embedding_service(config, embedding_provider)
    await embedding_service.initialize()
    
    print(f"Using embedding provider: {embedding_provider}")
    
    # Test connection by getting dimensions
    try:
        dimensions = await embedding_service.get_dimensions()
        print("Successfully connected to embedding service")
        print(f"Embedding dimensions: {dimensions}")
    except Exception as e:
        print(f"Failed to connect to embedding service: {str(e)}")
        return
    
    try:
        # Check if index exists and connect to it
        try:
            index = pc.Index(index_name)
            stats = index.describe_index_stats()
            print(f"Successfully connected to index: {index_name}")
            print(f"Index has {stats['total_vector_count']} vectors")
        except Exception as e:
            print(f"Error accessing index '{index_name}': {str(e)}")
            print("Please make sure the index exists. You can create it using create_pinecone_index.py")
            return
        
        # Generate embedding for query
        print(f"\nGenerating embedding for query: '{test_query}'")
        query_embedding = await embedding_service.embed_query(test_query)
        
        # Perform search
        print("\nExecuting query...")
        search_results = index.query(
            vector=query_embedding,
            top_k=3,
            include_metadata=True
        )
        
        # Print results
        print(f"\nQuery: '{test_query}'")
        
        if search_results['matches']:
            for i, match in enumerate(search_results['matches']):
                print(f"\nResult {i+1} (score: {match['score']:.4f}):")
                metadata = match.get('metadata', {})
                if 'question' in metadata and 'answer' in metadata:
                    print(f"Question: {metadata['question']}")
                    print(f"Answer: {metadata['answer']}")
                else:
                    print(f"Content: {metadata.get('content', 'N/A')}")
                    print(f"Metadata: {metadata}")
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
    load_config()
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Query a Pinecone index using semantic search')
    parser.add_argument('query_args', nargs='+', help='Index name (optional) followed by query text')
    args = parser.parse_args()
    
    # Check if first argument might be an index name
    if len(args.query_args) > 1:
        index_name = args.query_args[0]
        test_query = " ".join(args.query_args[1:])
    else:
        # Use default index or first available
        index_name = None
        test_query = args.query_args[0]
    
    await test_pinecone_query(test_query, index_name)

if __name__ == "__main__":
    asyncio.run(main())