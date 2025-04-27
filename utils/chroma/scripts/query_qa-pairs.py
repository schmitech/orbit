"""
Chroma Collection Query Tool
===========================

This script queries a Chroma vector database collection using semantic search.
It takes a query string, generates an embedding using Ollama, and retrieves the most relevant Q&A pairs.

Usage:
    python query-chroma-collection.py [collection_name] "your query text"

Arguments:
    collection_name: (Optional) Name of the Chroma collection to query
                     If not provided, uses the collection specified in config.yaml
    query: The search query text (in quotes if it contains spaces)

Example:
    python query-chroma-collection.py "What are the parking rules?"
    python query-chroma-collection.py my_collection "What are the parking rules?"

Requirements:
    - config.yaml file with Ollama and Chroma configuration
    - Running Ollama server with the specified embedding model
    - Running Chroma server with an existing collection
"""

import yaml
from langchain_ollama import OllamaEmbeddings
import chromadb
import argparse
from pathlib import Path

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "server" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

def test_chroma_ingestion(ollama_base_url: str, test_query: str, collection_name: str = None):
    config = load_config()

    # Print environment variables being used
    print("\nConfiguration Variables:")
    print(f"OLLAMA_BASE_URL: {ollama_base_url}")
    print(f"EMBED_MODEL: {config['embeddings']['ollama']['model']}")
    print(f"CHROMA_HOST: {config['datasources']['chroma']['host']}")
    print(f"CHROMA_PORT: {config['datasources']['chroma']['port']}")
    
    print(f"CHROMA_COLLECTION: {collection_name}\n")
    print(f"Using Ollama server at: {ollama_base_url}")
    
    # Get Chroma server details from configuration
    chroma_host = config['datasources']['chroma']['host']
    chroma_port = config['datasources']['chroma']['port']
    print(f"Using Chroma server at: {chroma_host}:{chroma_port}")
    
    # Initialize client with HTTP connection - exactly as in create-chroma-collection.py
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    
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
            print("Please make sure the collection exists. You can create it using create-chroma-collection.py")
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
            
            # Use the API query method with embeddings
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
    args = parser.parse_args()
    
    # Check if first argument might be a collection name
    if len(args.query_args) > 1:
        collection_name = args.query_args[0]
        test_query = " ".join(args.query_args[1:])
    else:
        collection_name = None
        test_query = args.query_args[0]
    
    test_chroma_ingestion(ollama_base_url, test_query, collection_name)