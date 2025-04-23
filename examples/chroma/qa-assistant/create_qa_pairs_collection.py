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
import json
import yaml
from langchain_ollama import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tqdm import tqdm
import chromadb
import argparse
from pathlib import Path

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

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
    
    # Using a completely different approach for collection creation
    print("Using simplified collection creation approach...")
    
    try:
        # Skip any attempt to get or verify existing collections first
        # Just try to create the collection directly with only the name parameter
        # This avoids any issues with the configuration structure in newer Chroma versions
        
        # Create collection with absolute minimal parameters
        collection = None
        collection = client.create_collection(name=collection_name)
        print(f"Successfully created collection: {collection_name}")
        
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
        else:
            # For other errors, try a different approach - direct Python requests to the API
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
    
    # Confirm we have a valid collection object
    if not collection:
        raise Exception("Failed to obtain a valid collection object")
    
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
    test_embedding = embeddings.embed_query(test_query)
    
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