"""
Pinecone Index Creator for RAG
==============================

This script creates an optimized vector database index in Pinecone from a JSON file containing Q&A pairs.
It processes questions, generates embeddings, and stores them with associated answers as metadata.

Usage:
    python create_pinecone_index.py <index_name> <json_file_path>

Arguments:
    index_name           Name of the Pinecone index to create
    json_file_path       Path to the JSON file containing Q&A pairs

Examples:
    # Create index on Pinecone cloud
    python create_pinecone_index.py city-faq data/city_faq.json

Key features:
    1. Embeds only questions for focused semantic search
    2. Stores complete answers as metadata for retrieval
    3. Optimizes metadata structure for retrieval
    4. Uses Pinecone's efficient cloud-based vector storage and retrieval
    5. Supports serverless and pod-based deployments

Notes:
    - Requires DATASOURCE_PINECONE_API_KEY environment variable to be set
    - The script uses embedding configuration from config.yaml and embeddings.yaml
    - This script is part of a suite of Pinecone utilities:
      * create_pinecone_index.py - Creates and populates indexes
      * query_pinecone_index.py - Queries indexes with semantic search
      * list_pinecone_indexes.py - Lists available indexes
      * delete_pinecone_index.py - Deletes indexes
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
from pinecone import Pinecone, ServerlessSpec
import time

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[2] / "server"
sys.path.append(str(server_path))

# Load environment variables from .env file in the project root directory
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=dotenv_path)
print(f"Loading environment variables from: {dotenv_path}")

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

async def ingest_to_pinecone(
    json_file_path: str,
    config: dict,
    embedding_provider: str,
    index_name: str,
    batch_size: int = 100
):
    
    # Initialize Pinecone client
    pc = get_pinecone_client()
    print(f"Connected to Pinecone")
    
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
    
    # Create or recreate index
    try:
        # Check if index exists
        existing_indexes = pc.list_indexes()
        index_exists = any(idx.name == index_name for idx in existing_indexes)
        
        if index_exists:
            print(f"Deleting existing index: {index_name}")
            pc.delete_index(index_name)
            # Wait for deletion to complete
            time.sleep(5)
        
        # Create new index with serverless spec
        print(f"Creating new index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=dimensions,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        
        # Wait for index to be ready
        print("Waiting for index to be ready...")
        while not pc.describe_index(index_name).status['ready']:
            time.sleep(1)
        
        print(f"Successfully created index: {index_name}")
        
    except Exception as e:
        print(f"Error creating index: {str(e)}")
        raise
    
    # Connect to the index
    index = pc.Index(index_name)
    
    # Create data directory if it doesn't exist
    data_dir = Path(json_file_path).parent
    os.makedirs(data_dir, exist_ok=True)
    
    # Load Q&A pairs
    with open(json_file_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"Loaded {len(qa_pairs)} Q&A pairs")
    
    # Process and upload in batches
    vectors = []
    
    # Process each Q&A pair
    for idx, qa in enumerate(tqdm(qa_pairs, desc="Processing Q&A pairs")):
        question = qa["question"]
        answer = qa["answer"]
        
        try:
            # Generate embedding for the question
            embedding = await embedding_service.embed_query(question)
            
            # Create vector with metadata
            vector = {
                "id": f"qa_{idx}",
                "values": embedding,
                "metadata": {
                    "question": question,
                    "answer": answer,
                    "content": question,  # For compatibility with search
                    "source": index_name,
                    "original_id": idx
                }
            }
            vectors.append(vector)
            
            # Upload in batches
            if len(vectors) >= batch_size:
                index.upsert(vectors=vectors)
                print(f"Uploaded batch of {len(vectors)} vectors")
                vectors = []
                
        except Exception as e:
            print(f"Error processing Q&A pair {idx}: {str(e)}")
            continue
    
    # Upload remaining vectors
    if vectors:
        index.upsert(vectors=vectors)
        print(f"Uploaded final batch of {len(vectors)} vectors")
    
    # Get index stats
    stats = index.describe_index_stats()
    print(f"\nIngestion complete!")
    print(f"Total vectors in index: {stats['total_vector_count']}")
    
    # Test retrieval with a sample query
    print("\nTesting retrieval with a sample query...")
    test_query = "How do I pay my property taxes?"
    
    try:
        test_embedding = await embedding_service.embed_query(test_query)
        
        # Perform search
        search_results = index.query(
            vector=test_embedding,
            top_k=3,
            include_metadata=True
        )
        
        print(f"Query: {test_query}")
        for i, match in enumerate(search_results['matches']):
            print(f"\nResult {i+1} (score: {match['score']:.4f}):")
            print(f"Question: {match['metadata']['question']}")
            print(f"Answer: {match['metadata']['answer']}")
            
    except Exception as e:
        print(f"Error during test query: {str(e)}")
    
    # Close the embedding service
    await embedding_service.close()

async def main():
    config = load_config()

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Ingest Q&A pairs into Pinecone database')
    parser.add_argument('index_name', help='Name of the Pinecone index to create')
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs')
    args = parser.parse_args()
    
    # Get configuration values
    embedding_provider = config['embedding']['provider']
    
    print(f"Using embedding provider: {embedding_provider}")
    
    # Run ingestion with Pinecone
    await ingest_to_pinecone(
        json_file_path=args.json_file_path,
        config=config,
        embedding_provider=embedding_provider,
        index_name=args.index_name,
        batch_size=100
    )

if __name__ == "__main__":
    asyncio.run(main())