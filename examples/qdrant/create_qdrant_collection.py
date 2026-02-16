"""
Qdrant Collection Creator for RAG
=================================

This script creates an optimized vector database collection in Qdrant from a JSON file containing Q&A pairs.
It processes questions, generates embeddings, and stores them with associated answers as metadata.

Usage:
    python create_qdrant_collection.py <collection_name> <json_file_path> [--cloud] [--update]

Arguments:
    collection_name      Name of the Qdrant collection to create
    json_file_path       Path to the JSON file containing Q&A pairs
    --cloud              Use Qdrant Cloud instead of self-hosted Qdrant
    --update             Add records to existing collection instead of recreating it
                         (saves embedding costs by only processing new records)

Examples:
    # Create collection on self-hosted Qdrant server (uses DATASOURCE_QDRANT_HOST/PORT from .env)
    python create_qdrant_collection.py city_faq data/city_faq.json

    # Create collection on Qdrant Cloud (uses DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY from .env)
    python create_qdrant_collection.py city_faq data/city_faq.json --cloud

    # Add more records to an existing collection (without deleting existing data)
    python create_qdrant_collection.py city_faq data/new_qa_pairs.json --update

    # Add more records to Qdrant Cloud collection
    python create_qdrant_collection.py city_faq data/new_qa_pairs.json --cloud --update

Key features:
    1. Embeds only questions for focused semantic search
    2. Stores complete answers as metadata for retrieval
    3. Optimizes metadata structure for retrieval
    4. Includes content and metadata indexing for hybrid search
    5. Uses Qdrant's efficient vector storage and retrieval
    6. Supports both self-hosted Qdrant and Qdrant Cloud
    7. Update mode: append records without re-embedding existing data (cost-saving)

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
import json
import yaml
import sys
import asyncio
import os
from tqdm import tqdm
import argparse
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.http import models

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[2] / "server"
sys.path.append(str(server_path))

# Load environment variables from .env file in the project root directory
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=dotenv_path)
print(f"Loading environment variables from: {dotenv_path}")

from embeddings.base import EmbeddingServiceFactory

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

async def ingest_to_qdrant(
    json_file_path: str,
    config: dict,
    embedding_provider: str,
    collection_name: str,
    batch_size: int = 50,
    qdrant_url: str = None,
    qdrant_api_key: str = None,
    qdrant_host: str = None,
    qdrant_port: int = None,
    update_mode: bool = False
):
    
    # Initialize Qdrant client based on cloud or self-hosted mode
    if qdrant_url and qdrant_api_key:
        # Cloud mode: use URL and API key
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=60
        )
        print(f"Connected to Qdrant Cloud at {qdrant_url[:50]}...")
    else:
        # Self-hosted mode: use host and port
        client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            timeout=60
        )
        print(f"Connected to Qdrant server at {qdrant_host}:{qdrant_port}")
    
    # Initialize Embedding service based on config
    embedding_service = EmbeddingServiceFactory.create_embedding_service(config, embedding_provider)
    
    # Initialize the embedding service
    initialized = await embedding_service.initialize()
    if not initialized:
        raise ValueError(f"Failed to initialize {embedding_provider} embedding service")
    
    print("\nEmbedding Service Details:")
    print(f"Provider: {embedding_provider}")
    # Get model name from config
    model_name = config['embeddings'][embedding_provider]['model']
    print(f"Model: {model_name}")
    
    # Get dimensions to verify connection
    dimensions = await embedding_service.get_dimensions()
    print(f"Dimensions: {dimensions}")
    print("-" * 50)
    
    # Check if collection exists
    collections = client.get_collections().collections
    collection_exists = any(col.name == collection_name for col in collections)
    
    # Determine starting ID for new records
    start_id = 0
    
    if update_mode:
        # Update mode: add to existing collection
        if not collection_exists:
            print(f"Error: Collection '{collection_name}' does not exist.")
            print("Use without --update flag to create a new collection.")
            await embedding_service.close()
            return
        
        # Get collection info and find the next available ID
        collection_info = client.get_collection(collection_name)
        current_count = collection_info.points_count
        print(f"\nUpdate mode: Adding records to existing collection '{collection_name}'")
        print(f"Current vectors in collection: {current_count}")
        
        # Get the max ID currently in the collection to avoid conflicts
        # We'll scroll through to find the highest ID
        if current_count > 0:
            # Scroll to get existing IDs and find the max
            scroll_result = client.scroll(
                collection_name=collection_name,
                limit=10000,  # Get a large batch to find max ID
                with_payload=False,
                with_vectors=False
            )
            existing_ids = [point.id for point in scroll_result[0]]
            if existing_ids:
                # Handle both int and string IDs
                int_ids = [id for id in existing_ids if isinstance(id, int)]
                if int_ids:
                    start_id = max(int_ids) + 1
                else:
                    start_id = current_count
            else:
                start_id = current_count
        
        print(f"Starting ID for new records: {start_id}")
    else:
        # Create mode: delete and recreate collection
        try:
            if collection_exists:
                print(f"Deleting existing collection: {collection_name}")
                client.delete_collection(collection_name)
            
            # Create new collection with an optimized configuration
            print(f"Creating new collection: {collection_name}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=dimensions,
                    distance=Distance.COSINE,
                    on_disk=True  # Use on-disk storage for larger datasets
                ),
                # HNSW config for tuning performance-accuracy trade-off
                hnsw_config=models.HnswConfigDiff(
                    m=16,  # Number of bi-directional links for each new element
                    ef_construct=100  # Number of candidates for best neighbors search
                ),
                # Scalar quantization for memory optimization
                quantization_config=models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(
                        type=models.ScalarType.INT8,
                        quantile=0.99,  # Use 99th percentile for quantization
                        always_ram=True  # Keep quantized vectors in RAM
                    )
                )
            )
            print(f"Successfully created collection: {collection_name}")

            # Create a payload index on the 'question' field for hybrid search
            print("Creating payload index for 'question' field...")
            client.create_payload_index(
                collection_name=collection_name,
                field_name="question",
                field_schema=models.TextIndexParams(
                    type="text",
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=20,
                    lowercase=True
                )
            )
            print("Successfully created payload index for 'question'.")
            
        except Exception as e:
            print(f"Error creating collection: {str(e)}")
            raise
    
    # Create data directory if it doesn't exist
    data_dir = Path(json_file_path).parent
    os.makedirs(data_dir, exist_ok=True)
    
    # Load Q&A pairs
    with open(json_file_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"Loaded {len(qa_pairs)} Q&A pairs from {json_file_path}")
    
    # Process and upload in batches
    points = []
    
    # Process each Q&A pair
    for idx, qa in enumerate(tqdm(qa_pairs, desc="Processing Q&A pairs")):
        question = qa["question"]
        answer = qa["answer"]
        
        # Calculate the actual ID (offset by start_id for update mode)
        point_id = start_id + idx
        
        try:
            # Generate embedding for the question
            embedding = await embedding_service.embed_query(question)
            
            # Create point with metadata
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "question": question,
                    "answer": answer,
                    "content": question,  # For compatibility with search
                    "source": collection_name,
                    "original_id": point_id
                }
            )
            points.append(point)
            
            # Upload in batches
            if len(points) >= batch_size:
                client.upsert(
                    collection_name=collection_name,
                    points=points
                )
                print(f"Uploaded batch of {len(points)} vectors")
                points = []
                
        except Exception as e:
            print(f"Error processing Q&A pair {idx}: {str(e)}")
            continue
    
    # Upload remaining points
    if points:
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        print(f"Uploaded final batch of {len(points)} vectors")
    
    # Get collection info
    collection_info = client.get_collection(collection_name)
    print("\nIngestion complete!")
    print(f"Total vectors in collection: {collection_info.points_count}")
    
    # Test retrieval with a sample query
    print("\nTesting retrieval with a sample query...")
    test_query = "How do I pay my property taxes?"
    
    try:
        test_embedding = await embedding_service.embed_query(test_query)
        
        # Perform search (using v1.16+ API)
        result = client.query_points(
            collection_name=collection_name,
            query=test_embedding,  # Changed from query_vector to query
            limit=3,
            with_payload=True
        )
        # Extract points from QueryResponse (v1.16+ returns QueryResponse object)
        search_results = result.points if hasattr(result, 'points') else result
        
        print(f"Query: {test_query}")
        for i, result in enumerate(search_results):
            print(f"\nResult {i+1} (score: {result.score:.4f}):")
            print(f"Question: {result.payload['question']}")
            print(f"Answer: {result.payload['answer']}")
            
    except Exception as e:
        print(f"Error during test query: {str(e)}")
    
    # Close the embedding service
    await embedding_service.close()

async def main():
    config = load_config()

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Ingest Q&A pairs into Qdrant database')
    parser.add_argument('collection_name', help='Name of the Qdrant collection to create or update')
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs')
    parser.add_argument('--cloud', action='store_true', 
                        help='Use Qdrant Cloud (requires DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY in .env)')
    parser.add_argument('--update', action='store_true',
                        help='Add records to existing collection instead of recreating it (saves embedding costs)')
    args = parser.parse_args()
    
    # Get configuration values
    embedding_provider = config['embedding']['provider']
    qdrant_url, qdrant_api_key, qdrant_host, qdrant_port = get_qdrant_config(use_cloud=args.cloud)
    
    print(f"Using embedding provider: {embedding_provider}")
    if args.cloud:
        print("Qdrant Cloud mode enabled")
    else:
        print(f"Qdrant server: {qdrant_host}:{qdrant_port}")
    
    if args.update:
        print("Update mode: Will add records to existing collection")
    
    # Run ingestion with Qdrant
    await ingest_to_qdrant(
        json_file_path=args.json_file_path,
        config=config,
        embedding_provider=embedding_provider,
        collection_name=args.collection_name,
        batch_size=50,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        update_mode=args.update
    )

if __name__ == "__main__":
    asyncio.run(main())