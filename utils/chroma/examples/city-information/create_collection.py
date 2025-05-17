"""
Enhanced Chroma Collection Creator for City Information RAG
=========================================

This script creates an optimized vector database collection in Chroma from a JSON file containing
city information with rich metadata. It includes semantic chunking and advanced metadata handling.

Usage:
    python create_collection.py <collection_name> <json_file_path> [--local] [--db-path PATH]

Arguments:
    collection_name      Name of the Chroma collection to create
    json_file_path       Path to the JSON file containing city information with metadata
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"

Examples:
    # Create collection on remote Chroma server (defined in config.yaml)
    python create_collection.py city_info utils/sample-data/city-qa-pairs-enhanced.json
    
    # Create collection in local filesystem database
    python create_collection.py city_info utils/sample-data/city-qa-pairs-enhanced.json --local
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
from typing import List, Dict, Any
from dataclasses import dataclass

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[4] / "server"
sys.path.append(str(server_path))

# Load environment variables from .env file in the server directory
dotenv_path = server_path / ".env"
load_dotenv(dotenv_path=dotenv_path)
print(f"Loading environment variables from: {dotenv_path}")

from embeddings.base import EmbeddingServiceFactory

@dataclass
class ChunkedDocument:
    text: str
    metadata: Dict[str, Any]
    chunk_id: str

def flatten_nested_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """Flatten nested dictionary for better metadata handling."""
    items: List[tuple] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_nested_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Convert list to string representation
            items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, v))
    return dict(items)

def create_semantic_chunks(data: Dict[str, Any], chunk_id: str) -> List[ChunkedDocument]:
    """Create semantic chunks from a single city information record."""
    chunks = []
    
    # Create a base chunk with the question and basic info
    base_metadata = {
        'question': data['question'],
        'department': data['department'],
        'chunk_id': chunk_id,
        'chunk_type': 'base'
    }
    
    # Add flattened metadata
    flat_data = flatten_nested_dict(data)
    for key, value in flat_data.items():
        if key not in ['question', 'department']:
            base_metadata[key] = value
    
    # Create the main text chunk
    main_text = f"Question: {data['question']}\nDepartment: {data['department']}\n"
    
    # Add structured information in a readable format
    for key, value in flat_data.items():
        if key not in ['question', 'department']:
            if isinstance(value, (list, dict)):
                main_text += f"{key.replace('_', ' ').title()}: {json.dumps(value, indent=2)}\n"
            else:
                main_text += f"{key.replace('_', ' ').title()}: {value}\n"
    
    chunks.append(ChunkedDocument(
        text=main_text.strip(),
        metadata=base_metadata,
        chunk_id=chunk_id
    ))
    
    # Create additional chunks for nested structures
    for key, value in data.items():
        if isinstance(value, dict):
            nested_chunk = f"Question: {data['question']}\nDepartment: {data['department']}\n"
            nested_chunk += f"Details about {key.replace('_', ' ').title()}:\n"
            nested_chunk += json.dumps(value, indent=2)
            
            nested_metadata = base_metadata.copy()
            nested_metadata['chunk_type'] = f'nested_{key}'
            
            chunks.append(ChunkedDocument(
                text=nested_chunk,
                metadata=nested_metadata,
                chunk_id=f"{chunk_id}_{key}"
            ))
    
    return chunks

def load_config():
    """Load configuration file from project root"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Get the project root (3 levels up: examples -> chroma -> utils -> project_root)
    project_root = script_dir.parents[3]
    
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
    """Ingest optimized city information data into Chroma DB."""
    
    # Initialize Chroma client based on mode
    if use_local:
        local_db_path = Path(db_path).resolve()
        os.makedirs(local_db_path, exist_ok=True)
        client = chromadb.PersistentClient(path=str(local_db_path))
        print(f"Using local filesystem persistence at: {local_db_path}")
    else:
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
        print(f"Connected to Chroma server at {chroma_host}:{chroma_port}")
    
    # Create or get collection
    if not collection_name:
        raise ValueError("Collection name cannot be empty.")
    
    print("Creating or accessing collection...")
    
    try:
        try:
            collection = client.get_collection(name=collection_name)
            print(f"Accessing existing collection: {collection_name}")
            if use_local:
                client.delete_collection(name=collection_name)
                print(f"Deleted existing collection: {collection_name}")
                collection = client.create_collection(name=collection_name)
                print(f"Successfully recreated collection: {collection_name}")
        except Exception:
            collection = client.create_collection(name=collection_name)
            print(f"Successfully created new collection: {collection_name}")
    except Exception as e:
        if "already exists" in str(e) or "already used" in str(e):
            print(f"Collection '{collection_name}' seems to already exist. Trying to access it...")
            try:
                collection = client.get_collection(name=collection_name)
                print(f"Successfully accessed existing collection: {collection_name}")
                client.delete_collection(name=collection_name)
                print(f"Deleted existing collection: {collection_name}")
                collection = client.create_collection(name=collection_name)
                print(f"Successfully recreated collection: {collection_name}")
            except Exception as inner_e:
                print(f"Error accessing existing collection: {str(inner_e)}")
                raise Exception(f"Cannot create or access collection: {str(e)}")
        else:
            raise Exception(f"Failed to create collection: {str(e)}")
    
    if not collection:
        raise Exception("Failed to obtain a valid collection object")
    
    # Initialize Embedding service
    embedding_service = EmbeddingServiceFactory.create_embedding_service(config, embedding_provider)
    initialized = await embedding_service.initialize()
    if not initialized:
        raise ValueError(f"Failed to initialize {embedding_provider} embedding service")
    
    print(f"\nEmbedding Service Details:")
    print(f"Provider: {embedding_provider}")
    model_name = config['embeddings'][embedding_provider]['model']
    print(f"Model: {model_name}")
    dimensions = await embedding_service.get_dimensions()
    print(f"Dimensions: {dimensions}")
    print("-" * 50)
    
    # Load and process city information data
    with open(json_file_path, 'r', encoding='utf-8') as f:
        city_data = json.load(f)
    
    print(f"Loaded {len(city_data)} city information records")
    
    # Process and chunk the data
    all_chunks = []
    for idx, item in enumerate(city_data):
        chunk_id = f"city_{idx}"
        chunks = create_semantic_chunks(item, chunk_id)
        all_chunks.extend(chunks)
    
    print(f"Created {len(all_chunks)} semantic chunks")
    
    # Process chunks in batches
    for i in tqdm(range(0, len(all_chunks), batch_size), desc="Processing chunks"):
        batch = all_chunks[i:i + batch_size]
        
        batch_ids = []
        batch_embeddings = []
        batch_metadatas = []
        batch_documents = []
        
        # Generate embeddings for the batch
        batch_contents = [chunk.text for chunk in batch]
        try:
            all_embeddings = await embedding_service.embed_documents(batch_contents)
            
            for j, chunk in enumerate(batch):
                batch_ids.append(chunk.chunk_id)
                batch_embeddings.append(all_embeddings[j])
                batch_metadatas.append(chunk.metadata)
                batch_documents.append(chunk.text)
                
        except Exception as e:
            print(f"Error with batch embedding, falling back to individual embedding: {str(e)}")
            
            for chunk in batch:
                try:
                    embedding = await embedding_service.embed_query(chunk.text)
                    
                    batch_ids.append(chunk.chunk_id)
                    batch_embeddings.append(embedding)
                    batch_metadatas.append(chunk.metadata)
                    batch_documents.append(chunk.text)
                    
                except Exception as e:
                    print(f"Error processing chunk {chunk.chunk_id}: {str(e)}")
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
    
    # Test retrieval
    print("\nTesting retrieval with sample queries...")
    test_queries = [
        "What are the property tax rates?",
        "How do I report a pothole?",
        "What are the parking permit fees?",
        "Tell me about sustainability initiatives"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        test_embedding = await embedding_service.embed_query(query)
        
        try:
            results = collection.query(
                query_embeddings=[test_embedding],
                n_results=3,
                include=["documents", "metadatas", "distances"]
            )
            
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                print(f"\nResult {i+1} (similarity: {1-distance:.4f}):")
                print(f"Department: {metadata['department']}")
                print(f"Question: {metadata['question']}")
                print("-" * 30)
        except Exception as e:
            print(f"Error during test query: {str(e)}")
    
    # Close the embedding service
    await embedding_service.close()

async def main():
    config = load_config()

    parser = argparse.ArgumentParser(description='Ingest city information into Chroma database')
    parser.add_argument('collection_name', help='Name of the Chroma collection to create')
    parser.add_argument('json_file_path', help='Path to the JSON file containing city information')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    args = parser.parse_args()
    
    embedding_provider = config['embedding']['provider']
    print(f"Using embedding provider: {embedding_provider}")
    
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