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
    collection_name: str,
    model: str,
    batch_size: int = 50
):
    print(f"Function received ollama_base_url: {ollama_base_url}")
    
    # Initialize Chroma client with HTTP connection
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    print(f"Connected to Chroma server at {chroma_host}:{chroma_port}")
    
    # Create or get collection
    if not collection_name:
        raise ValueError("CHROMA_COLLECTION is not set in the configuration file.")
    
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
    parser.add_argument('json_file_path', help='Path to the JSON file containing Q&A pairs')
    args = parser.parse_args()
    
    # Updated configuration with Chroma server details
    CONFIG = {
        "ollama_base_url": config['ollama']['base_url'],
        "json_file_path": args.json_file_path,
        "batch_size": 50,
        "chroma_host": config['chroma']['host'],
        "chroma_port": config['chroma']['port'],
        "collection_name": config['chroma']['collection'],
        "model": config['ollama']['embed_model']
    }
    
    # Run ingestion with Chroma
    ingest_to_chroma(**CONFIG)