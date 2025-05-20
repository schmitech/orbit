"""
Chroma Collection Creator for RAG
=========================================

This script creates an optimized vector database collection in Chroma from a JSON file containing Q&A pairs.
It processes questions, generates embeddings, and stores them with associated answers as metadata.

Usage:
    python create_qa_pairs_collection.py <collection_name> <json_file_path> [--local] [--db-path PATH]

Arguments:
    collection_name      Name of the Chroma collection to create
    json_file_path       Path to the JSON file containing Q&A pairs
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"

Examples:
    # Create collection on remote Chroma server (defined in config.yaml)
    python create_qa_pairs_collection.py city_faq data/city_faq.json
    
    # Create collection in local filesystem database
    python create_qa_pairs_collection.py city_faq data/city_faq.json --local
    
    # Create collection in a specific local database path
    python create_qa_pairs_collection.py city_faq data/city_faq.json --local --db-path /path/to/my/chroma_db

Key features:
    1. Embeds only questions for focused semantic search
    2. Stores complete answers as metadata for retrieval
    3. Optimizes metadata structure for retrieval
    4. Includes content and metadata indexing for hybrid search
    5. Supports both remote Chroma server and local filesystem persistence

Notes:
    - For remote mode, the script uses server connection details from config.yaml
    - For local mode, it creates a PersistentClient at the specified path
    - This script is part of a suite of Chroma utilities that all support both modes:
      * create_qa_pairs_collection.py - Creates and populates collections
      * query_qa-pairs.py - Queries collections with semantic search
      * list_chroma_collections.py - Lists available collections
"""
import json
import yaml
import sys
import asyncio
import os
from tqdm import tqdm
import chromadb
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[2] / "server"
sys.path.append(str(server_path))

# Load environment variables from .env file in the project root directory
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=dotenv_path)
print(f"Loading environment variables from: {dotenv_path}")

from embeddings.base import EmbeddingServiceFactory

def load_config():
    """Load configuration file from project root"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Get the project root (2 levels up: scripts -> chroma -> project_root)
    project_root = script_dir.parents[1]
    
    # Try to find config.yaml in project root first, then in config subdirectory
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        config_path = project_root / "config" / "config.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found in {project_root} or {project_root}/config/")
    
    print(f"Loading config from: {config_path}")
    return yaml.safe_load(config_path.read_text())

async def ingest_to_chroma(
    json_file_path: str,
    config: dict,
    embedding_provider: str,
    chroma_host: str,
    chroma_port: str,
    collection_name: str,
    use_local: bool = False,
    db_path: str = "./chroma_db",
    batch_size: int = 50
):
    
    # Initialize Chroma client based on mode
    if use_local:
        # Create a local directory for persistence if it doesn't exist
        local_db_path = Path(db_path).resolve()
        os.makedirs(local_db_path, exist_ok=True)
        client = chromadb.PersistentClient(path=str(local_db_path))
        print(f"Using local filesystem persistence at: {local_db_path}")
    else:
        # Initialize Chroma client with HTTP connection
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
        print(f"Connected to Chroma server at {chroma_host}:{chroma_port}")
    
    # Create or get collection
    if not collection_name:
        raise ValueError("Collection name cannot be empty.")
    
    # Collection creation approach
    print("Creating or accessing collection...")
    
    try:
        # First try to get the collection (it might already exist)
        try:
            collection = client.get_collection(name=collection_name)
            print(f"Accessing existing collection: {collection_name}")
            # Delete and recreate if using local mode
            if use_local:
                client.delete_collection(name=collection_name)
                print(f"Deleted existing collection: {collection_name}")
                collection = client.create_collection(name=collection_name)
                print(f"Successfully recreated collection: {collection_name}")
        except Exception:
            # Collection doesn't exist, create it
            collection = client.create_collection(name=collection_name)
            print(f"Successfully created new collection: {collection_name}")
        
    except Exception as e:
        # If creation fails but contains a specific error about collection already existing
        if "already exists" in str(e) or "already used" in str(e):
            # Try direct access
            print(f"Collection '{collection_name}' seems to already exist. Trying to access it...")
            try:
                collection = client.get_collection(name=collection_name)
                print(f"Successfully accessed existing collection: {collection_name}")
                # Now delete and recreate
                client.delete_collection(name=collection_name)
                print(f"Deleted existing collection: {collection_name}")
                collection = client.create_collection(name=collection_name)
                print(f"Successfully recreated collection: {collection_name}")
            except Exception as inner_e:
                print(f"Error accessing existing collection: {str(inner_e)}")
                raise Exception(f"Cannot create or access collection: {str(e)}")
        elif not use_local:
            # For other errors with the remote server, try a different approach
            print(f"Error creating collection with standard method: {str(e)}")
            print("Trying alternative API access method...")
            
            try:
                # Try the low-level API directly (last resort)
                import requests
                url = f"http://{chroma_host}:{chroma_port}/api/v2/tenants/default_tenant/databases/default_database/collections"
                response = requests.post(url, json={"name": collection_name})
                print(f"Direct API response: {response.status_code} - {response.text}")
                
                if response.status_code in (200, 201):
                    print("Collection created via direct API call")
                    collection = client.get_collection(name=collection_name)
                elif response.status_code == 409:  # Conflict/already exists
                    print("Collection exists, getting reference")
                    collection = client.get_collection(name=collection_name)
                else:
                    raise Exception(f"Failed to create collection via direct API: {response.text}")
            except Exception as api_e:
                print(f"All collection creation methods failed: {str(api_e)}")
                raise Exception(f"Cannot create collection with any method: {str(e)}, {str(api_e)}")
        else:
            raise Exception(f"Failed to create local collection: {str(e)}")
    
    # Confirm we have a valid collection object
    if not collection:
        raise Exception("Failed to obtain a valid collection object")
    
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
    
    # Create data directory if it doesn't exist
    data_dir = Path(json_file_path).parent
    os.makedirs(data_dir, exist_ok=True)
    
    # Load Q&A pairs
    with open(json_file_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"Loaded {len(qa_pairs)} Q&A pairs")
    
    all_items = []
    
    # Process each Q&A pair 
    for idx, qa in enumerate(qa_pairs):
        question = qa["question"]
        answer = qa["answer"]
        
        # Store each question with its answer as metadata
        all_items.append({
            "id": f"qa_{idx}",
            "content": question,  # Only embed the question
            "metadata": {
                "question": question,
                "answer": answer,
                "source": collection_name,
                "original_id": idx
            }
        })
    
    # Generate embeddings and add to collection in batches
    for i in tqdm(range(0, len(all_items), batch_size), desc="Processing items"):
        batch = all_items[i:i + batch_size]
        
        batch_ids = []
        batch_embeddings = []
        batch_metadatas = []
        batch_documents = []
        
        # Generate embeddings for the batch
        batch_contents = [item["content"] for item in batch]
        try:
            # Use embed_documents for batch processing if possible
            all_embeddings = await embedding_service.embed_documents(batch_contents)
            
            for j, item in enumerate(batch):
                batch_ids.append(item["id"])
                batch_embeddings.append(all_embeddings[j])
                batch_metadatas.append(item["metadata"])
                batch_documents.append(item["content"])
                
        except Exception as e:
            print(f"Error with batch embedding, falling back to individual embedding: {str(e)}")
            
            # Fallback to individual embedding if batch fails
            for item in batch:
                try:
                    embedding = await embedding_service.embed_query(item["content"])
                    
                    batch_ids.append(item["id"])
                    batch_embeddings.append(embedding)
                    batch_metadatas.append(item["metadata"])
                    batch_documents.append(item["content"])
                    
                except Exception as e:
                    print(f"Error processing item {item['id']}: {str(e)}")
                    continue

        # Add batch to collection
        if batch_ids:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # In newer versions of Chroma, the upsert API might have changed
                    # Try with simpler parameters first
                    collection.upsert(
                        ids=batch_ids,
                        embeddings=batch_embeddings,
                        metadatas=batch_metadatas,
                        documents=batch_documents
                    )
                    print(f"Uploaded batch of {len(batch_ids)} vectors")
                    break
                except Exception as e:
                    print(f"Attempt {attempt+1}/{max_retries} - Error uploading batch: {str(e)}")
                    if "_type" in str(e):
                        print("Trying alternative upsert method without metadata...")
                        try:
                            # Try without metadata if that's causing issues
                            collection.upsert(
                                ids=batch_ids,
                                embeddings=batch_embeddings,
                                documents=batch_documents
                            )
                            print(f"Uploaded batch without metadata (simplification)")
                            break
                        except Exception as simple_e:
                            print(f"Simplified upsert also failed: {str(simple_e)}")
                    
                    if attempt == max_retries - 1:
                        print(f"Failed to upload batch after {max_retries} attempts")
                    else:
                        import time
                        time.sleep(1)  # Wait before retry

    # Print stats
    print("\nIngestion complete!")
    print(f"Total vectors in collection: {collection.count()}")
    
    # Add a demonstration query to test retrieval
    print("\nTesting retrieval with a sample query...")
    test_query = "How do I pay my property taxes?"
    test_embedding = await embedding_service.embed_query(test_query)
    
    try:
        # Make sure we can access the collection
        count = collection.count()
        print(f"Collection contains {count} items")
        
        if count == 0:
            print("Collection is empty. Skipping test query.")
        else:
            results = collection.query(
                query_embeddings=[test_embedding],
                n_results=min(3, count),  # Ensure we don't request more results than available
                include=["documents", "metadatas", "distances"]
            )
            
            print(f"Query: {test_query}")
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0], 
                results['metadatas'][0],
                results['distances'][0]
            )):
                print(f"\nResult {i+1} (similarity: {1-distance:.4f}):")
                print(f"Question: {metadata['question']}")
                print(f"Answer: {metadata['answer']}")
    except Exception as e:
        print(f"Error during test query: {str(e)}")
        print("This may be due to the collection not being properly initialized or empty.")
    
    # Close the embedding service
    await embedding_service.close()

async def main():
    config = load_config()  # Load the config

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Ingest Q&A pairs into Chroma database')
    parser.add_argument('collection_name', help='Name of the Chroma collection to create')
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    args = parser.parse_args()
    
    # Get the embedding provider from the config
    embedding_provider = config['embedding']['provider']
    print(f"Using embedding provider: {embedding_provider}")
    
    # Run ingestion with Chroma
    await ingest_to_chroma(
        json_file_path=args.json_file_path,
        config=config,
        embedding_provider=embedding_provider,
        chroma_host=config['datasources']['chroma']['host'],
        chroma_port=config['datasources']['chroma']['port'],
        collection_name=args.collection_name,
        use_local=args.local,
        db_path=args.db_path,
        batch_size=50
    )

if __name__ == "__main__":
    asyncio.run(main())