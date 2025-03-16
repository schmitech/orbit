import os
import sys
import yaml
from langchain_ollama import OllamaEmbeddings
import chromadb
from dotenv import load_dotenv

def load_config():
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

def test_chroma_ingestion(ollama_base_url: str, test_query: str):
    config = load_config()

    # Print environment variables being used
    print("\nConfiguration Variables:")
    print(f"OLLAMA_BASE_URL: {ollama_base_url}")
    print(f"OLLAMA_EMBED_MODEL: {config['ollama']['embed_model']}")
    print(f"CHROMA_COLLECTION: {config['chroma']['collection']}")
    print(f"CHROMA_HOST: {config['chroma']['host']}")
    print(f"CHROMA_PORT: {config['chroma']['port']}\n")

    print(f"Using Ollama server at: {ollama_base_url}")
    
    # Get Chroma server details from configuration
    chroma_host = config['chroma']['host']
    chroma_port = config['chroma']['port']
    print(f"Using Chroma server at: {chroma_host}:{chroma_port}")
    
    # Initialize client with HTTP connection instead of persistent storage
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    
    # Get the collection
    collection_name = config['chroma']['collection']
    if not collection_name:
        raise ValueError("CHROMA_COLLECTION environment variable is not set")
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
        n_results=3,
        include=['metadatas', 'documents', 'distances']
    )
    
    # Print results
    print("\nTest Query Results:")
    print(f"Query: '{test_query}'\n")
    
    if results['metadatas'] and results['metadatas'][0]:
        # Only show the closest match
        closest_match = results['metadatas'][0][0]
        print("Answer:")
        print(closest_match['answer'])
        print(f"\nConfidence: {1 - results['distances'][0][0]:.2%}")
    else:
        print("No results found")

if __name__ == "__main__":
    config = load_config()
    ollama_base_url = config['ollama']['base_url']
    if not ollama_base_url:
        raise ValueError("OLLAMA_BASE_URL environment variable is not set")
    
    # Get query from command line argument, or use default
    test_query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What are the parking rules?"
    
    test_chroma_ingestion(ollama_base_url, test_query)