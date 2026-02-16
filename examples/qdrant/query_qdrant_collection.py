"""
Qdrant Collection Query Tool
============================

This script queries a Qdrant vector database collection using semantic search.
It takes a query string, generates an embedding using the same provider as during creation,
and retrieves the most relevant Q&A pairs.

Usage:
    python query_qdrant_collection.py [collection_name] <query_text> [--cloud]

Arguments:
    collection_name      (Optional) Name of the Qdrant collection to query
                         If not provided, uses the collection specified in config.yaml
    query_text           The search query text (in quotes if it contains spaces)
    --cloud              Use Qdrant Cloud instead of self-hosted Qdrant

Examples:
    # Query self-hosted Qdrant server (uses DATASOURCE_QDRANT_HOST/PORT from .env)
    python query_qdrant_collection.py city_faq "What are the parking rules?"
    
    # Query Qdrant Cloud (uses DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY from .env)
    python query_qdrant_collection.py city_faq "What are the parking rules?" --cloud

Requirements:
    - config.yaml file with embedding and Qdrant configuration
    - Running embedding service matching what was used during creation
    - Running Qdrant server with an existing collection

Environment Variables:
    For self-hosted Qdrant (default):
        DATASOURCE_QDRANT_HOST - Qdrant server host (default: localhost)
        DATASOURCE_QDRANT_PORT - Qdrant server port (default: 6333)
    
    For Qdrant Cloud (--cloud flag):
        DATASOURCE_QDRANT_URL  - Qdrant Cloud URL (required)
        DATASOURCE_QDRANT_API_KEY - Qdrant Cloud API key (required)

Notes:
    - The script uses server connection details from config.yaml and .env file
    - This script is part of a suite of Qdrant utilities:
      * create_qdrant_collection.py - Creates and populates collections
      * query_qdrant_collection.py - Queries collections with semantic search
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
    
    # Get the project root (2 levels up: scripts -> qdrant -> project_root)
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

def resolve_env_placeholder(value):
    """Resolve environment variable placeholders like ${VAR_NAME} or ${VAR_NAME:-default}"""
    if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
        inner = value[2:-1]  # Remove ${ and }
        # Handle ${VAR:-default} syntax
        if ':-' in inner:
            env_var, default = inner.split(':-', 1)
            return os.getenv(env_var, default)
        else:
            return os.getenv(inner, '')  # Return empty string if env var not found
    return value

def get_qdrant_config(use_cloud: bool = False):
    """Get Qdrant configuration with proper fallbacks
    
    Args:
        use_cloud: If True, use cloud configuration (URL + API key), 
                   otherwise use self-hosted (host + port)
    
    Returns:
        For cloud mode: tuple(url, api_key, None, None)
        For self-hosted: tuple(None, None, host, port)
    """
    # Load environment variables from main project directory
    project_env_path = Path(__file__).resolve().parents[2] / ".env"
    if project_env_path.exists():
        load_dotenv(project_env_path, override=True)
        print(f"Loading environment variables from: {project_env_path}")
    else:
        print(f"Warning: .env file not found at {project_env_path}")
    
    # Load configuration
    config = load_config()
    
    # Get Qdrant config with fallbacks
    qdrant_config = config.get('datasources', {}).get('qdrant', {})
    
    if use_cloud:
        # Cloud mode: use URL and API key
        url = resolve_env_placeholder(qdrant_config.get('url', ''))
        api_key = resolve_env_placeholder(qdrant_config.get('api_key', ''))
        
        # Also check direct environment variables as fallback
        if not url:
            url = os.getenv('DATASOURCE_QDRANT_URL', '')
        if not api_key:
            api_key = os.getenv('DATASOURCE_QDRANT_API_KEY', '')
        
        if not url:
            raise ValueError("DATASOURCE_QDRANT_URL is required for cloud mode. "
                           "Please set it in your .env file.")
        if not api_key:
            raise ValueError("DATASOURCE_QDRANT_API_KEY is required for cloud mode. "
                           "Please set it in your .env file.")
        
        print(f"Qdrant Cloud config: url={url[:50]}...")
        return url, api_key, None, None
    else:
        # Self-hosted mode: use host and port
        host = resolve_env_placeholder(qdrant_config.get('host', 'localhost'))
        port = resolve_env_placeholder(qdrant_config.get('port', 6333))
        
        # Also check direct environment variables as fallback
        if not host or host == 'localhost':
            env_host = os.getenv('DATASOURCE_QDRANT_HOST')
            if env_host:
                host = env_host
        
        env_port = os.getenv('DATASOURCE_QDRANT_PORT')
        if env_port:
            port = env_port
        
        # Debug output to show what values are being used
        print(f"Qdrant config from config.yaml: host={qdrant_config.get('host')}, port={qdrant_config.get('port')}")
        print(f"Resolved values: host={host}, port={port}")
        
        # Convert port to int if it's a string
        if isinstance(port, str):
            try:
                port = int(port)
            except ValueError:
                print(f"Warning: Invalid port value '{port}', using default port 6333")
                port = 6333
        
        return None, None, host, port

async def test_qdrant_query(test_query: str, collection_name: str = None, use_cloud: bool = False):
    config = load_config()

    # Get the same embedding provider that was used during creation
    embedding_provider = config['embedding']['provider']
    
    # Get Qdrant connection details
    qdrant_url, qdrant_api_key, qdrant_host, qdrant_port = get_qdrant_config(use_cloud=use_cloud)
    
    # Print configuration variables
    print("\nConfiguration Variables:")
    print(f"Embedding Provider: {embedding_provider}")
    if use_cloud:
        print("Qdrant Cloud mode enabled")
    else:
        print(f"QDRANT_HOST: {qdrant_host}")
        print(f"QDRANT_PORT: {qdrant_port}")
    print(f"QDRANT_COLLECTION: {collection_name}\n")
    
    # Initialize Qdrant client based on cloud or self-hosted mode
    try:
        if qdrant_url and qdrant_api_key:
            # Cloud mode: use URL and API key
            client = QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=30
            )
            print(f"Connected to Qdrant Cloud at {qdrant_url[:50]}...")
        else:
            # Self-hosted mode: use host and port
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
        print("Successfully connected to embedding service")
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
        
        # Perform search (using v1.16+ API)
        print("\nExecuting query...")
        result = client.query_points(
            collection_name=collection_name,
            query=query_embedding,  # Changed from query_vector to query
            limit=3,
            with_payload=True
        )
        # Extract points from QueryResponse (v1.16+ returns QueryResponse object)
        search_results = result.points if hasattr(result, 'points') else result
        
        # Print results
        print(f"\nQuery: '{test_query}'")
        
        if search_results:
            for i, result in enumerate(search_results):
                # Calculate confidence the same way as QAQdrantRetriever
                # Qdrant returns similarity scores (0-1), confidence = score * score_scaling_factor
                score = result.score
                score_scaling_factor = 1.0  # Same as in config/adapters.yaml
                confidence = score * score_scaling_factor
                
                print(f"\nResult {i+1}:")
                print(f"  Raw Score: {score:.4f}")
                print(f"  Confidence: {confidence:.4f} (score * {score_scaling_factor})")
                print(f"  Would pass threshold 0.3: {'YES' if confidence >= 0.3 else 'NO'}")
                
                payload = result.payload
                if 'question' in payload and 'answer' in payload:
                    print(f"  Question: {payload['question']}")
                    print(f"  Answer: {payload['answer']}")
                else:
                    print(f"  Content: {payload.get('content', 'N/A')}")
                    print(f"  Payload: {payload}")
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
    parser = argparse.ArgumentParser(description='Query a Qdrant collection using semantic search')
    parser.add_argument('query_args', nargs='+', help='Collection name (optional) followed by query text')
    parser.add_argument('--cloud', action='store_true', 
                        help='Use Qdrant Cloud (requires DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY in .env)')
    args = parser.parse_args()
    
    # Check if first argument might be a collection name
    if len(args.query_args) > 1:
        collection_name = args.query_args[0]
        test_query = " ".join(args.query_args[1:])
    else:
        # Use default collection from config or a default name
        collection_name = "default_collection"  # You might want to set this in config
        test_query = args.query_args[0]
    
    await test_qdrant_query(test_query, collection_name, use_cloud=args.cloud)

if __name__ == "__main__":
    asyncio.run(main())