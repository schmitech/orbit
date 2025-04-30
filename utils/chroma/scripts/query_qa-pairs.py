"""
Chroma Collection Query Tool
===========================

This script queries a Chroma vector database collection using semantic search.
It takes a query string, generates an embedding using Ollama, and retrieves the most relevant Q&A pairs.

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
    # Query remote Chroma server (basic usage)
    python query_qa-pairs.py "What are the parking rules?"
    
    # Query specific collection on remote server
    python query_qa-pairs.py city_faq "What are the parking rules?"
    
    # Query local filesystem database
    python query_qa-pairs.py city_faq "What are the parking rules?" --local
    
    # Query from a specific local database path
    python query_qa-pairs.py city_faq "What are the parking rules?" --local --db-path /path/to/my/chroma_db

Requirements:
    - config.yaml file with Ollama and Chroma configuration
    - Running Ollama server with the specified embedding model
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
from langchain_ollama import OllamaEmbeddings
import chromadb
import argparse
from pathlib import Path

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "server" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

def test_chroma_ingestion(ollama_base_url: str, test_query: str, collection_name: str = None, use_local: bool = False, db_path: str = "./chroma_db"):
    config = load_config()

    # Print environment variables being used
    print("\nConfiguration Variables:")
    print(f"OLLAMA_BASE_URL: {ollama_base_url}")
    print(f"EMBED_MODEL: {config['embeddings']['ollama']['model']}")
    
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
    print(f"Using Ollama server at: {ollama_base_url}")
    
    # Initialize the same embeddings model used in ingestion
    model = config['embeddings']['ollama']['model']
    if not model:
        raise ValueError("EMBED_MODEL environment variable is not set")
    
    embeddings = OllamaEmbeddings(
        model=model,
        base_url=ollama_base_url,
        client_kwargs={"timeout": 30.0}  # Match timeout from create script
    )
    
    print(f"Using embedding model: {model}")
    
    # Test connection to Ollama
    try:
        test_embedding = embeddings.embed_query("test connection")
        print("Successfully connected to Ollama server")
        print(f"Embedding dimensions: {len(test_embedding)}")
    except Exception as e:
        print(f"Failed to connect to Ollama server: {str(e)}")
        return
    
    try:
        # Generate embedding for query
        print(f"\nGenerating embedding for query: '{test_query}'")
        query_embedding = embeddings.embed_query(test_query)
        
        # Get the collection - don't try to create it
        try:
            collection = client.get_collection(name=collection_name)
            print(f"Successfully connected to collection: {collection_name}")
        except Exception as e:
            print(f"Error accessing collection '{collection_name}': {str(e)}")
            print("Please make sure the collection exists. You can create it using create_qa_pairs_collection.py")
            return
            
        # Perform query using a WHERE filter instead of embedding directly (avoids SeqID issue)
        print("\nExecuting query...")
        
        # First, perform embedding search by directly providing the embeddings
        # This ensures dimension compatibility
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )
        
        # Print results in the same format as the test query in create-chroma-collection.py
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
        
        # If the above approach fails, try an alternative approach using the collection's direct methods
        try:
            print("\nTrying alternative query approach...")
            # Generate embedding for query
            query_embedding = embeddings.embed_query(test_query)
            
            if not use_local:
                # Use the API query method with embeddings (only for remote server)
                results = client.raw_api.query(
                    collection_name=collection_name,
                    query_embeddings=[query_embedding],
                    n_results=3,
                    include=["documents", "metadatas", "distances"]
                )
                
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
            else:
                print("Alternative approach not available for local database")
                
        except Exception as e2:
            print(f"Alternative approach also failed: {str(e2)}")
            print("Recommendation: Recreate your collection with integer IDs instead of string IDs")
            traceback.print_exc()

if __name__ == "__main__":
    config = load_config()
    ollama_base_url = config['inference']['ollama']['base_url']
    if not ollama_base_url:
        raise ValueError("OLLAMA_BASE_URL environment variable is not set")
    
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
    
    test_chroma_ingestion(
        ollama_base_url, 
        test_query, 
        collection_name,
        use_local=args.local,
        db_path=args.db_path
    )