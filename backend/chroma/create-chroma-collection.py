"""
Enhanced Chroma Collection Creator for RAG
=========================================

This script creates an optimized vector database collection in Chroma from a JSON file containing Q&A pairs.
It processes questions, generates embeddings, and stores them with associated answers as metadata.

Usage:
    python improved-chroma-collection.py <collection_name> <json_file_path>

Key improvements:
    1. Embeds only questions for focused semantic search
    2. Stores complete answers as metadata for retrieval
    3. Optimizes metadata structure for retrieval
    4. Includes content and metadata indexing for hybrid search
"""

import os
import json
import yaml
from langchain_ollama import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tqdm import tqdm
import chromadb
import argparse
import uuid

def load_config():
    with open('../config/config.yaml', 'r') as file:
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
    if collection_name in [c.name for c in existing_collections]:
        client.delete_collection(collection_name)
        print(f"Deleted existing collection: {collection_name}")
    
    # Create new collection
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}  # Use cosine similarity for better matching
    )
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
        test_embedding = embeddings.embed_query("test connection")
        print("Successfully connected to Ollama server")
        print(f"Embedding dimensions: {len(test_embedding)}")
    except Exception as e:
        print(f"Failed to connect to Ollama server at {ollama_base_url}")
        print(f"Error: {str(e)}")
        return
    
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
        
        for item in batch:
            try:
                # Generate embedding from the question only
                embedding = embeddings.embed_query(item["content"])
                
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
    test_query = "How do I pay my property taxes?"
    test_embedding = embeddings.embed_query(test_query)
    
    results = collection.query(
        query_embeddings=[test_embedding],
        n_results=3,
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
        "collection_name": args.collection_name,
        "model": config['ollama']['embed_model']
    }
    
    # Run ingestion with Chroma
    ingest_to_chroma(**CONFIG)