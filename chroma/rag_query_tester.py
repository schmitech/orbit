"""
RAG Query Tester
===============

This script tests the retrieval quality of your Chroma RAG system with a set of test queries.
It compares how well your system retrieves relevant answers for different types of questions.

Usage:
    python query-testing.py <collection_name>

This will run a series of test queries against your collection and report metrics.
"""

import yaml
import argparse
import chromadb
from langchain_ollama import OllamaEmbeddings

def load_config():
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

def test_queries(collection_name, chroma_host, chroma_port, ollama_base_url, model):
    # Initialize Chroma client
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    print(f"Connected to Chroma server at {chroma_host}:{chroma_port}")
    
    # Get collection
    collection = client.get_collection(name=collection_name)
    print(f"Using collection: {collection_name}")
    
    # Initialize Ollama embeddings
    embeddings = OllamaEmbeddings(
        model=model,
        base_url=ollama_base_url,
        client_kwargs={"timeout": 30.0}
    )
    
    # Test queries
    test_queries = [
        # Direct matches (similar to questions in dataset)
        "Where can I pay my taxes?",
        "What are the hours for Revenue Services?",
        "How much is the fee for name changes?",
        
        # Paraphrased queries
        "I need to know when property tax is due",
        "How can I change my address with the tax office?",
        "What happens if I'm late paying my property taxes?",
        
        # Complex queries
        "I need to view my property assessment and pay my taxes",
        "What fees do I need to pay for a name change and refund?",
        "Can I dispute my tax assessment and what's the process?"
    ]
    
    print("\nRunning test queries...\n")
    
    for query in test_queries:
        print(f"Query: {query}")
        
        # Generate embedding
        query_embedding = embeddings.embed_query(query)
        
        # Get results
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=2,
            include=["documents", "metadatas", "distances"]
        )
        
        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0], 
            results['metadatas'][0],
            results['distances'][0]
        )):
            similarity = 1 - distance
            print(f"  Result {i+1} (similarity: {similarity:.4f}):")
            print(f"  Q: {metadata['question']}")
            print(f"  A: {metadata['answer']}")
        print("-" * 80)

if __name__ == "__main__":
    config = load_config()
    
    parser = argparse.ArgumentParser(description='Test RAG queries')
    parser.add_argument('collection_name', help='Name of the Chroma collection to query')
    args = parser.parse_args()
    
    test_queries(
        collection_name=args.collection_name,
        chroma_host=config['chroma']['host'],
        chroma_port=config['chroma']['port'],
        ollama_base_url=config['ollama']['base_url'],
        model=config['ollama']['embed_model']
    )