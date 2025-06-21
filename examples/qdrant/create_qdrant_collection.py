"""
Qdrant Collection Creator for RAG
=================================

This script creates an optimized vector database collection in Qdrant from a JSON file containing Q&A pairs.
It processes questions, generates embeddings, and stores them with associated answers as metadata.

Usage:
    python create_qa_pairs_collection_qdrant.py <collection_name> <json_file_path>

Arguments:
    collection_name      Name of the Qdrant collection to create
    json_file_path       Path to the JSON file containing Q&A pairs

Examples:
    # Create collection on Qdrant server (defined in config.yaml)
    python create_qa_pairs_collection_qdrant.py city_faq data/city_faq.json

Key features:
    1. Embeds only questions for focused semantic search
    2. Stores complete answers as metadata for retrieval
    3. Optimizes metadata structure for retrieval
    4. Includes content and metadata indexing for hybrid search
    5. Uses Qdrant's efficient vector storage and retrieval

Notes:
    - The script uses server connection details from config.yaml and .env file
    - This script is part of a suite of Qdrant utilities:
      * create_qa_pairs_collection_qdrant.py - Creates and populates collections
      * query_qa_pairs_qdrant.py - Queries collections with semantic search
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
    """Resolve environment variable placeholders like ${VAR_NAME}"""
    if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
        env_var = value[2:-1]  # Remove ${ and }
        return os.getenv(env_var, value)  # Return original if env var not found
    return value

def get_qdrant_config():
    """Get Qdrant configuration with proper fallbacks"""
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
    
    # Resolve environment variable placeholders
    host = resolve_env_placeholder(qdrant_config.get('host', 'localhost'))
    port = resolve_env_placeholder(qdrant_config.get('port', 6333))
    
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
    
    return host, port

def load_config():
    """Load configuration file from project root"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Get the project root (2 levels up: scripts -> qdrant -> project_root)
    project_root = script_dir.parents[1]
    
    # Try to find config.yaml in project root first, then in config subdirectory
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        config_path = project_root / "config" / "config.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found in {project_root} or {project_root}/config/")
    
    print(f"Loading config from: {config_path}")
    return yaml.safe_load(config_path.read_text())

async def ingest_to_qdrant(
    json_file_path: str,
    config: dict,
    embedding_provider: str,
    qdrant_host: str,
    qdrant_port: int,
    collection_name: str,
    batch_size: int = 50
):
    
    # Initialize Qdrant client
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
    
    print(f"\nEmbedding Service Details:")
    print(f"Provider: {embedding_provider}")
    # Get model name from config
    model_name = config['embeddings'][embedding_provider]['model']
    print(f"Model: {model_name}")
    
    # Get dimensions to verify connection
    dimensions = await embedding_service.get_dimensions()
    print(f"Dimensions: {dimensions}")
    print("-" * 50)
    
    # Create or recreate collection
    try:
        # Check if collection exists and delete it if it does
        collections = client.get_collections().collections
        collection_exists = any(col.name == collection_name for col in collections)
        
        if collection_exists:
            print(f"Deleting existing collection: {collection_name}")
            client.delete_collection(collection_name)
        
        # Create new collection with proper vector configuration
        print(f"Creating new collection: {collection_name}")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=dimensions,
                distance=Distance.COSINE
            )
        )
        print(f"Successfully created collection: {collection_name}")
        
    except Exception as e:
        print(f"Error creating collection: {str(e)}")
        raise
    
    # Create data directory if it doesn't exist
    data_dir = Path(json_file_path).parent
    os.makedirs(data_dir, exist_ok=True)
    
    # Load Q&A pairs
    with open(json_file_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"Loaded {len(qa_pairs)} Q&A pairs")
    
    # Process and upload in batches
    points = []
    
    # Process each Q&A pair
    for idx, qa in enumerate(tqdm(qa_pairs, desc="Processing Q&A pairs")):
        question = qa["question"]
        answer = qa["answer"]
        
        try:
            # Generate embedding for the question
            embedding = await embedding_service.embed_query(question)
            
            # Create point with metadata
            point = PointStruct(
                id=idx,
                vector=embedding,
                payload={
                    "question": question,
                    "answer": answer,
                    "content": question,  # For compatibility with search
                    "source": collection_name,
                    "original_id": idx
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
    print(f"\nIngestion complete!")
    print(f"Total vectors in collection: {collection_info.points_count}")
    
    # Test retrieval with a sample query
    print("\nTesting retrieval with a sample query...")
    test_query = "How do I pay my property taxes?"
    
    try:
        test_embedding = await embedding_service.embed_query(test_query)
        
        # Perform search
        search_results = client.search(
            collection_name=collection_name,
            query_vector=test_embedding,
            limit=3,
            with_payload=True
        )
        
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
    parser.add_argument('collection_name', help='Name of the Qdrant collection to create')
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs')
    args = parser.parse_args()
    
    # Get configuration values
    embedding_provider = config['embedding']['provider']
    qdrant_host, qdrant_port = get_qdrant_config()
    
    print(f"Using embedding provider: {embedding_provider}")
    print(f"Qdrant server: {qdrant_host}:{qdrant_port}")
    
    # Run ingestion with Qdrant
    await ingest_to_qdrant(
        json_file_path=args.json_file_path,
        config=config,
        embedding_provider=embedding_provider,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        collection_name=args.collection_name,
        batch_size=50
    )

if __name__ == "__main__":
    asyncio.run(main())