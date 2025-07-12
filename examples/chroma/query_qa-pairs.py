"""
Chroma Collection Query Tool
===========================

This script queries a Chroma vector database collection using semantic search.
It takes a query string, generates an embedding using the same provider as during creation,
and retrieves the most relevant Q&A pairs.

Usage:
    python query_qa-pairs.py [collection_name] <query_text> [--local] [--db-path PATH]

Arguments:
    collection_name      (Optional) Name of the Chroma collection to query
                         If not provided, uses the collection specified in config.yaml
    query_text           The search query text (in quotes if it contains spaces)
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"

Examples:
    # Query specific collection on remote server
    python query_qa-pairs.py city_faq "What are the parking rules?"
    
    # Query from a specific local database path
    python query_qa-pairs.py city_faq "What are the parking rules?" --local --db-path /path/to/my/chroma_db

Requirements:
    - config.yaml file with Ollama and Chroma configuration
    - Running embedding service matching what was used during creation
    - Running Chroma server with an existing collection (or local filesystem DB if using --local)

Notes:
    - For remote mode, the script uses server connection details from config.yaml
    - For local mode, it connects to a PersistentClient at the specified path
    - This script is part of a suite of Chroma utilities that all support both modes:
      * create_qa_pairs_collection.py - Creates and populates collections
      * query_qa-pairs.py - Queries collections with semantic search
      * list_chroma_collections.py - Lists available collections
"""

import yaml
import os
import sys
import asyncio
from langchain_ollama import OllamaEmbeddings
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

# Import the same embedding factory used during creation
from embeddings.base import EmbeddingServiceFactory

def load_config():
    """Load configuration files from project root"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Get the project root (2 levels up: scripts -> chroma -> project_root)
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
    
    return config

async def test_chroma_query(test_query: str, collection_name: str = None, use_local: bool = False, db_path: str = "./chroma_db"):
    config = load_config()

    # Get the same embedding provider that was used during creation
    embedding_provider = config['embedding']['provider']
    
    # Print environment variables being used
    print("\nConfiguration Variables:")
    print(f"Embedding Provider: {embedding_provider}")
    
    # Initialize client based on mode
    if use_local:
        # Create a local directory for persistence if it doesn't exist
        local_db_path = Path(db_path).resolve()
        if not os.path.exists(local_db_path):
            print(f"Error: Local database path {local_db_path} does not exist.")
            print("Please create it first using create_qa_pairs_collection.py with the --local option.")
            return
        
        client = chromadb.PersistentClient(path=str(local_db_path))
        print(f"Using local filesystem persistence at: {local_db_path}")
    else:
        # Get Chroma server details from configuration
        chroma_host = config['datasources']['chroma']['host']
        chroma_port = config['datasources']['chroma']['port']
        print(f"CHROMA_HOST: {chroma_host}")
        print(f"CHROMA_PORT: {chroma_port}")
        print(f"Using Chroma server at: {chroma_host}:{chroma_port}")
        
        # Initialize client with HTTP connection
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    
    print(f"CHROMA_COLLECTION: {collection_name}\n")
    
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
        # Generate embedding for query
        print(f"\nGenerating embedding for query: '{test_query}'")
        query_embedding = await embedding_service.embed_query(test_query)
        
        # Get the collection - don't try to create it
        try:
            collection = client.get_collection(name=collection_name)
            print(f"Successfully connected to collection: {collection_name}")
        except Exception as e:
            print(f"Error accessing collection '{collection_name}': {str(e)}")
            print("Please make sure the collection exists. You can create it using create_qa_pairs_collection.py")
            return
            
        # Perform query using the same approach as in creation script
        print("\nExecuting query...")
        
        # Query using the same method as in the creation script
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )
        
        # Print results
        print(f"\nQuery: '{test_query}'")
        
        if results['metadatas'] and len(results['metadatas'][0]) > 0:
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0], 
                results['metadatas'][0],
                results['distances'][0]
            )):
                similarity = 1 - distance
                print(f"\nResult {i+1} (similarity: {similarity:.4f}):")
                if 'question' in metadata and 'answer' in metadata:
                    print(f"Question: {metadata['question']}")
                    print(f"Answer: {metadata['answer']}")
                else:
                    print(f"Document: {doc[:100]}...")  # Show first 100 chars of doc
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
    config = load_config()
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Query a Chroma collection using semantic search')
    parser.add_argument('query_args', nargs='+', help='Collection name (optional) followed by query text')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    args = parser.parse_args()
    
    # Check if first argument might be a collection name
    if len(args.query_args) > 1:
        collection_name = args.query_args[0]
        test_query = " ".join(args.query_args[1:])
    else:
        collection_name = None
        test_query = args.query_args[0]
    
    await test_chroma_query(
        test_query, 
        collection_name,
        use_local=args.local,
        db_path=args.db_path
    )

if __name__ == "__main__":
    asyncio.run(main())