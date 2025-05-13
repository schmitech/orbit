"""
Enhanced Chroma Collection Creator for RAG with LLM Answer Generation
=========================================

This script creates an optimized vector database collection in Chroma from a JSON file containing
Q&A pairs with rich metadata. The LLM will generate answers using the metadata.

Usage:
    python create_enhanced_qa_collection.py <collection_name> <json_file_path> [--local] [--db-path PATH]

Arguments:
    collection_name      Name of the Chroma collection to create
    json_file_path       Path to the JSON file containing Q&A pairs with metadata
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"

Examples:
    # Create collection on remote Chroma server (defined in config.yaml)
    python create_enhanced_qa_collection.py city_qa_enhanced utils/sample-data/city-qa-pairs-enhanced.json
    
    # Create collection in local filesystem database
    python create_enhanced_qa_collection.py city_qa_enhanced utils/sample-data/city-qa-pairs-enhanced.json --local
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
server_path = Path(__file__).resolve().parents[3] / "server"
sys.path.append(str(server_path))

# Load environment variables from .env file in the server directory
dotenv_path = server_path / ".env"
load_dotenv(dotenv_path=dotenv_path)
print(f"Loading environment variables from: {dotenv_path}")

from embeddings.base import EmbeddingServiceFactory

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "server" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

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
        else:
            raise Exception(f"Failed to create collection: {str(e)}")
    
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
    
    # Load Q&A pairs
    with open(json_file_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"Loaded {len(qa_pairs)} Q&A pairs with metadata")
    
    # Count metadata fields for reporting
    metadata_fields = set()
    for qa in qa_pairs:
        for key in qa.keys():
            if key != "question":
                metadata_fields.add(key)
    
    print(f"Found {len(metadata_fields)} metadata fields per record")
    print(f"Metadata fields: {', '.join(metadata_fields)}")
    
    all_items = []
    
    # Process each Q&A pair 
    for idx, qa in enumerate(qa_pairs):
        question = qa["question"]
        
        # Initialize metadata with base fields
        metadata = {
            "question": question,
            "source": collection_name,
            "original_id": idx
        }
        
        # Add all metadata fields
        for key, value in qa.items():
            if key != "question":
                metadata[key] = value
        
        # Store each question with its metadata
        all_items.append({
            "id": f"qa_{idx}",
            "content": question,  # Only embed the question
            "metadata": metadata
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
            try:
                collection.upsert(
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas,
                    documents=batch_documents
                )
                print(f"Uploaded batch of {len(batch_ids)} vectors")
            except Exception as e:
                print(f"Error uploading batch: {str(e)}")

    # Print stats
    print("\nIngestion complete!")
    print(f"Total vectors in collection: {collection.count()}")
    
    # Add a demonstration query to test retrieval
    print("\nTesting retrieval with a sample query...")
    test_query = "How do I pay my water bill online?"
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
                
                # Print metadata fields
                print("Metadata fields:")
                for key, value in metadata.items():
                    if key not in ["question", "source", "original_id"]:
                        print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error during test query: {str(e)}")
    
    # Close the embedding service
    await embedding_service.close()

async def main():
    config = load_config()  # Load the config

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Ingest Q&A pairs with metadata into Chroma database')
    parser.add_argument('collection_name', help='Name of the Chroma collection to create')
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs with metadata')
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