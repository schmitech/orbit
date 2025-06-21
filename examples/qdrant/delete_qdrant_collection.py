"""
Qdrant Collection Deletion Tool
===============================

This script deletes a specified collection from a Qdrant vector database.

Usage:
    python delete_qdrant_collection.py <collection_name>

Arguments:
    collection_name      Name of the Qdrant collection to delete

Examples:
    # Delete collection from Qdrant server (defined in config.yaml and .env)
    python delete_qdrant_collection.py city_faq

Process:
    1. Connects to the Qdrant server
    2. Checks if the specified collection exists
    3. Deletes the collection if it exists
    4. Provides confirmation of the deletion

Notes:
    - The script uses server connection details from config.yaml and .env file
    - This script is part of a suite of Qdrant utilities:
      * create_qa_pairs_collection_qdrant.py - Creates and populates collections
      * query_qa_pairs_qdrant.py - Queries collections with semantic search
      * list_qdrant_collections.py - Lists available collections
      * delete_qdrant_collection.py - Deletes collections
"""

import sys
import yaml
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient

def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

def resolve_env_placeholder(value):
    """Resolve environment variable placeholders like ${VAR_NAME}"""
    if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
        env_var = value[2:-1]  # Remove ${ and }
        return os.getenv(env_var, value)  # Return original if env var not found
    return value

def get_qdrant_config():
    """Get Qdrant configuration with proper fallbacks"""
    # Load environment variables from main project directory
    project_env_path = Path(__file__).resolve().parents[2] / ".env"
    if project_env_path.exists():
        load_dotenv(project_env_path, override=True)
        print(f"Loading environment variables from: {project_env_path}")
    else:
        print(f"Warning: .env file not found at {project_env_path}")
    
    # Load configuration
    config = load_config()
    
    # Get Qdrant config with fallbacks
    qdrant_config = config.get('datasources', {}).get('qdrant', {})
    
    # Resolve environment variable placeholders
    host = resolve_env_placeholder(qdrant_config.get('host', 'localhost'))
    port = resolve_env_placeholder(qdrant_config.get('port', 6333))
    
    # Debug output to show what values are being used
    print(f"Qdrant config from config.yaml: host={qdrant_config.get('host')}, port={qdrant_config.get('port')}")
    print(f"Resolved values: host={host}, port={port}")
    
    # Convert port to int if it's a string
    if isinstance(port, str):
        try:
            port = int(port)
        except ValueError:
            print(f"Warning: Invalid port value '{port}', using default port 6333")
            port = 6333
    
    return host, port

def delete_qdrant_collection(collection_name: str):
    """
    Delete a collection from the Qdrant database.
    
    Args:
        collection_name (str): Name of the collection to delete
    """
    # Get Qdrant connection details
    qdrant_host, qdrant_port = get_qdrant_config()
    
    print(f"Connecting to Qdrant server at: {qdrant_host}:{qdrant_port}")

    try:
        # Initialize Qdrant client
        client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            timeout=30
        )
        
        # Check if the collection exists
        try:
            collections_response = client.get_collections()
            collections = collections_response.collections
            collection_exists = any(col.name == collection_name for col in collections)
            
            if not collection_exists:
                print(f"Collection '{collection_name}' does not exist.")
                return
                
            # Get collection info before deletion
            collection_info = client.get_collection(collection_name)
            points_count = collection_info.points_count
            
            print(f"Found collection '{collection_name}' with {points_count} vectors")
            print("Deleting collection...")
            
            # Delete the collection
            client.delete_collection(collection_name)
            print(f"Successfully deleted collection: {collection_name}")
            
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                print(f"Collection '{collection_name}' does not exist.")
            else:
                print(f"Error when working with collection: {str(e)}")
                
    except Exception as e:
        print(f"Error connecting to Qdrant server: {str(e)}")
        print("Please check your connection details and ensure the Qdrant server is running.")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Delete a collection from Qdrant database')
    parser.add_argument('collection_name', help='Name of the Qdrant collection to delete')
    args = parser.parse_args()

    delete_qdrant_collection(args.collection_name)