"""
Qdrant Collection Listing Tool
==============================

This script lists all collections in a Qdrant vector database, showing collection names
and basic information about each collection.

Usage:
    python list_qdrant_collections.py

Examples:
    # List collections from Qdrant server (defined in config.yaml and .env)
    python list_qdrant_collections.py

Notes:
    - The script uses server connection details from config.yaml and .env file
    - This script is part of a suite of Qdrant utilities:
      * create_qa_pairs_collection_qdrant.py - Creates and populates collections
      * query_qa_pairs_qdrant.py - Queries collections with semantic search
      * list_qdrant_collections.py - Lists available collections
      * delete_qdrant_collection.py - Deletes collections
"""

import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "server" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

def list_collections():
    # Load configuration
    config = load_config()
    
    # Load environment variables
    server_env_path = Path(__file__).resolve().parents[3] / "server" / ".env"
    if server_env_path.exists():
        load_dotenv(server_env_path)
    
    # Get Qdrant connection details
    qdrant_host = os.getenv('QDRANT_HOST', config['datasources']['qdrant']['host'])
    qdrant_port = int(os.getenv('QDRANT_PORT', config['datasources']['qdrant']['port']))
    
    print(f"Connecting to Qdrant server at: {qdrant_host}:{qdrant_port}")
    
    try:
        # Create Qdrant client
        client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            timeout=30
        )
        
        # Get list of all collections
        collections_response = client.get_collections()
        collections = collections_response.collections
        
        # Print collection information
        print("\nAvailable collections:")
        if not collections:
            print("No collections found.")
        else:
            for collection in collections:
                try:
                    # Get detailed collection info
                    collection_info = client.get_collection(collection.name)
                    vectors_count = collection_info.points_count
                    vector_size = collection_info.config.params.vectors.size
                    distance = collection_info.config.params.vectors.distance
                    
                    print(f"- {collection.name}")
                    print(f"  Vectors: {vectors_count}")
                    print(f"  Dimensions: {vector_size}")
                    print(f"  Distance: {distance}")
                    print()
                except Exception as e:
                    print(f"- {collection.name} (Error getting details: {str(e)})")
                    
    except Exception as e:
        print(f"Error connecting to Qdrant server: {str(e)}")
        print("Please check your connection details and ensure the Qdrant server is running.")

if __name__ == "__main__":
    list_collections()