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

Configuration (config.yaml):
    ollama:
      base_url: URL of the Ollama server (e.g., http://localhost:11434)
      embed_model: Name of the embedding model to use (e.g., mxbai-embed-large)
    chroma:
      host: Hostname of the Chroma server
      port: Port of the Chroma server
      collection: Default collection name (used if not specified as argument)

Process:
    1. Connects to the Ollama server to generate embeddings
    2. Connects to the Chroma server to access the vector database
    3. Converts the query text into an embedding vector
    4. Searches the collection for semantically similar content
    5. Returns the most relevant answers with confidence scores
"""

import os
import sys
import yaml
from langchain_ollama import OllamaEmbeddings
import chromadb
import argparse
from dotenv import load_dotenv

def load_config():
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

def test_chroma_ingestion(ollama_base_url: str, test_query: str, collection_name: str = None):
    config = load_config()

    # Print environment variables being used
    print("\nConfiguration Variables:")
    print(f"OLLAMA_BASE_URL: {ollama_base_url}")
    print(f"OLLAMA_EMBED_MODEL: {config['ollama']['embed_model']}")
    print(f"CHROMA_HOST: {config['chroma']['host']}")
    print(f"CHROMA_PORT: {config['chroma']['port']}")
    
    # Use provided collection name or fall back to config
    if not collection_name:
        collection_name = config['chroma']['collection']
    print(f"CHROMA_COLLECTION: {collection_name}\n")

    print(f"Using Ollama server at: {ollama_base_url}")
    
    # Get Chroma server details from configuration
    chroma_host = config['chroma']['host']
    chroma_port = config['chroma']['port']
    print(f"Using Chroma server at: {chroma_host}:{chroma_port}")
    
    # Initialize client with HTTP connection instead of persistent storage
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    
    # Get the collection
    if not collection_name:
        raise ValueError("Collection name is not provided and not set in config.yaml")
    collection = client.get_collection(name=collection_name)
    
    # Initialize the same embeddings model used in ingestion
    model = config['ollama']['embed_model']
    if not model:
        raise ValueError("OLLAMA_EMBED_MODEL environment variable is not set")
    
    embeddings = OllamaEmbeddings(
        model=model,
        base_url=ollama_base_url
    )
    
    # Get total count
    total_records = collection.count()
    print(f"\nTotal records in collection: {total_records}")
    
    # Perform the query
    query_embedding = embeddings.embed_query(test_query)
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=5,  # Increased to get more results to find the best match
        include=['metadatas', 'documents', 'distances']
    )
    
    # Print results
    print("\nTest Query Results:")
    print(f"Query: '{test_query}'\n")
    
    if results['metadatas'] and results['metadatas'][0]:
        # Find the result with the highest confidence (lowest distance)
        best_idx = 0
        best_confidence = 0
        
        for idx, distance in enumerate(results['distances'][0]):
            confidence = 1 - distance  # Convert distance to confidence score
            if confidence > best_confidence:
                best_confidence = confidence
                best_idx = idx
        
        # Get the best match
        best_match = results['metadatas'][0][best_idx]
        print("Best Match Answer:")
        print(best_match['answer'])
        print(f"\nConfidence: {best_confidence:.2%}")
        
        # Print other matches for reference
        if len(results['metadatas'][0]) > 1:
            print("\nOther Matches:")
            for idx, (metadata, distance) in enumerate(zip(results['metadatas'][0], results['distances'][0])):
                if idx != best_idx:
                    confidence = 1 - distance
                    print(f"\nMatch {idx + 1}:")
                    print(metadata['answer'])
                    print(f"Confidence: {confidence:.2%}")
    else:
        print("No results found")

if __name__ == "__main__":
    config = load_config()
    ollama_base_url = config['ollama']['base_url']
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