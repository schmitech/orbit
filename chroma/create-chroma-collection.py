"""
Chroma Collection Creator
=========================

This script creates a vector database collection in Chroma from a JSON file containing Q&A pairs.
It processes the Q&A pairs, generates embeddings using Ollama, and stores them in a Chroma collection.

Usage:
    python create-chroma-collection.py <collection_name> <json_file_path>

Arguments:
    collection_name: Name of the Chroma collection to create
    json_file_path: Path to the JSON file containing Q&A pairs

Example:
    python create-chroma-collection.py my_qa_collection data/qa_pairs.json

Requirements:
    - config.yaml file with Ollama and Chroma configuration
    - Running Ollama server with the specified embedding model
    - Running Chroma server
    - JSON file with Q&A pairs in the format: [{"question": "...", "answer": "..."}, ...]

Configuration (config.yaml):
    ollama:
      base_url: URL of the Ollama server (e.g., http://localhost:11434)
      embed_model: Name of the embedding model to use (e.g., mxbai-embed-large)
    chroma:
      host: Hostname of the Chroma server
      port: Port of the Chroma server

Process:
    1. Loads Q&A pairs from the JSON file
    2. Splits longer Q&A pairs into smaller chunks
    3. Generates embeddings for each chunk using Ollama
    4. Stores the embeddings and metadata in a Chroma collection
    5. Processes in batches to handle large datasets efficiently
"""

import os
import json
import yaml
from langchain_ollama import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tqdm import tqdm
import chromadb
import argparse

def load_config():
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

def ingest_to_chroma(
    json_file_path: str,
    ollama_base_url: str,
    chroma_host: str,
    chroma_port: str,
    model: str,
    collection_name: str,
    batch_size: int = 50
):
    print(f"Function received ollama_base_url: {ollama_base_url}")
    
    # Initialize Chroma client with HTTP connection
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    print(f"Connected to Chroma server at {chroma_host}:{chroma_port}")
    
    # Create or get collection
    if not collection_name:
        raise ValueError("Collection name cannot be empty.")
    
    # Delete existing collection if it exists
    existing_collections = client.list_collections()
    if collection_name in existing_collections:
        client.delete_collection(collection_name)
        print(f"Deleted existing collection: {collection_name}")
    
    # Create new collection
    collection = client.create_collection(name=collection_name)
    print(f"Created new collection: {collection_name}")
    
    # Print the embedding model being used
    print(f"Using embedding model: {model}")
    
    # Initialize Ollama embeddings
    if not model:
        raise ValueError("OLLAMA_EMBED_MODEL is not set in the configuration file.")
    
    embeddings = OllamaEmbeddings(
        model=model,
        base_url=ollama_base_url,
        client_kwargs={"timeout": 30.0}
    )
    
    # Verify Ollama connection
    try:
        # Test embedding with a simple string
        test_embedding = embeddings.embed_query("test connection")
        print("Successfully connected to Ollama server")
        print(f"Embedding dimensions: {len(test_embedding)}")  # Should print 1024 for mxbai-embed-large
    except Exception as e:
        print(f"Failed to connect to Ollama server at {ollama_base_url}")
        print(f"Error: {str(e)}")
        return
    
    # Load Q&A pairs
    with open(json_file_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"Loaded {len(qa_pairs)} Q&A pairs")
    
    # Text splitter for longer texts
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )
    
    # Process in batches
    for i in tqdm(range(0, len(qa_pairs), batch_size), desc="Processing Q&A pairs"):
        batch = qa_pairs[i:i + batch_size]
        
        batch_ids = []
        batch_embeddings = []
        batch_metadatas = []
        
        for idx, qa in enumerate(batch):
            combined_text = f"Question: {qa['question']}\nAnswer: {qa['answer']}"
            chunks = text_splitter.split_text(combined_text)
            
            for chunk_idx, chunk in enumerate(chunks):
                try:
                    embedding = embeddings.embed_query(chunk)
                    doc_id = f"qa_{i + idx}_{chunk_idx}"
                    
                    batch_ids.append(doc_id)
                    batch_embeddings.append(embedding)
                    batch_metadatas.append({
                        "text": chunk,
                        "question": qa["question"],
                        "answer": qa["answer"],
                        "chunk_index": str(chunk_idx),
                        "source": collection_name
                    })
                    
                except Exception as e:
                    print(f"Error processing Q&A pair {i + idx}: {str(e)}")
                    continue

        # Add batch to collection
        if batch_ids:
            try:
                collection.upsert(
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas
                )
                print(f"Uploaded batch of {len(batch_ids)} vectors")
            except Exception as e:
                print(f"Error uploading batch: {str(e)}")

    # Print stats
    print("\nIngestion complete!")
    print(f"Total vectors in collection: {collection.count()}")

if __name__ == "__main__":
    config = load_config()  # Load the config

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Ingest Q&A pairs into Chroma database')
    parser.add_argument('collection_name', help='Name of the Chroma collection to create')
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs')
    args = parser.parse_args()
    
    # Updated configuration with Chroma server details
    CONFIG = {
        "ollama_base_url": config['ollama']['base_url'],
        "json_file_path": args.json_file_path,
        "batch_size": 50,
        "chroma_host": config['chroma']['host'],
        "chroma_port": config['chroma']['port'],
        "collection_name": args.collection_name,  # Use the command-line argument
        "model": config['ollama']['embed_model']
    }
    
    # Run ingestion with Chroma
    ingest_to_chroma(**CONFIG)