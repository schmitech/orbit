#!/usr/bin/env python3
"""
Test script to check the actual data stored in Chroma collection
"""
import json
import yaml
import sys
import asyncio
import chromadb
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[2] / "server"
sys.path.append(str(server_path))

# Load environment variables
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Import after adding to path
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

async def test_chroma_data(collection_name: str = None, use_local: bool = False, db_path: str = "./chroma_db"):
    config = load_config()
    
    # Use default collection name if not provided
    if not collection_name:
        collection_name = "city_qa_pairs"
    
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
        print(f"Connecting to Chroma at {chroma_host}:{chroma_port}")
        
        # Connect to Chroma
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    
    print(f"Collection: {collection_name}")
    
    try:
        # Get the collection
        collection = client.get_collection(name=collection_name)
        print(f"Successfully connected to collection: {collection_name}")
        
        # Get collection count
        count = collection.count()
        print(f"Collection contains {count} items")
        
        # Get a few sample items to check the data
        print("\n" + "="*50)
        print("SAMPLE DATA FROM COLLECTION:")
        print("="*50)
        
        # Get all items (limit to first 10 for testing)
        results = collection.get(
            limit=10,
            include=["documents", "metadatas"]
        )
        
        for i, (doc, metadata) in enumerate(zip(results['documents'], results['metadatas'])):
            print(f"\nItem {i+1}:")
            print(f"Document: {doc}")
            print(f"Metadata keys: {list(metadata.keys())}")
            
            if 'question' in metadata and 'answer' in metadata:
                print(f"Question: {metadata['question']}")
                print(f"Answer: {metadata['answer']}")
                
                # Check for the specific police report entry
                if "police report" in metadata['question'].lower():
                    print(f"🔍 FOUND POLICE REPORT ENTRY:")
                    print(f"   Question: {metadata['question']}")
                    print(f"   Answer: {metadata['answer']}")
                    print(f"   Answer length: {len(metadata['answer'])}")
                    print(f"   Answer bytes: {metadata['answer'].encode('utf-8')}")
            
            print("-" * 30)
        
        # Now test a specific query
        print("\n" + "="*50)
        print("TESTING SPECIFIC QUERY:")
        print("="*50)
        
        # Initialize embedding service
        embedding_provider = config['embedding']['provider']
        embedding_service = EmbeddingServiceFactory.create_embedding_service(config, embedding_provider)
        await embedding_service.initialize()
        
        # Test query for police reports
        test_query = "How much does it cost to get a copy of a police report?"
        query_embedding = await embedding_service.embed_query(test_query)
        
        # Query the collection
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )
        
        print(f"Query: {test_query}")
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
                print(f"Answer length: {len(metadata['answer'])}")
                print(f"Answer bytes: {metadata['answer'].encode('utf-8')}")
            else:
                print(f"Document: {doc}")
                print(f"Metadata: {metadata}")
        
        await embedding_service.close()
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

async def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Test script to check data in Chroma collection')
    parser.add_argument('collection_name', nargs='?', default=None, help='Name of the Chroma collection to test')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    args = parser.parse_args()
    
    await test_chroma_data(
        collection_name=args.collection_name,
        use_local=args.local,
        db_path=args.db_path
    )

if __name__ == "__main__":
    asyncio.run(main()) 