"""
Chroma Collection Deletion Tool
==============================

This script deletes a specified collection from a Chroma vector database,
supporting both remote server and local filesystem modes.

Usage:
    python delete_chroma_collection.py <collection_name> [--local] [--db-path PATH]

Arguments:
    collection_name      Name of the Chroma collection to delete
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"

Examples:
    # Delete collection from remote Chroma server (defined in config.yaml)
    python delete_chroma_collection.py city_faq
    
    # Delete collection from local filesystem database
    python delete_chroma_collection.py city_faq --local
    
    # Delete collection from a specific local database path
    python delete_chroma_collection.py city_faq --local --db-path /path/to/my/chroma_db

Process:
    1. Connects to the Chroma server or local filesystem database
    2. Checks if the specified collection exists
    3. Deletes the collection if it exists
    4. Provides confirmation of the deletion

Notes:
    - For remote mode, the script uses server connection details from config.yaml
    - For local mode, it connects to a PersistentClient at the specified path
    - This script is part of a suite of Chroma utilities that all support both modes:
      * create_qa_pairs_collection.py - Creates and populates collections
      * query_qa-pairs.py - Queries collections with semantic search
      * list_chroma_collections.py - Lists available collections
      * delete_chroma_collection.py - Deletes collections
"""

import sys
import yaml
import chromadb
import argparse
import os
from pathlib import Path

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

def delete_chroma_collection(collection_name: str, use_local: bool = False, db_path: str = "./chroma_db"):
    """
    Delete a collection from the Chroma database.
    
    Args:
        collection_name (str): Name of the collection to delete
        use_local (bool): Whether to use local filesystem instead of remote server
        db_path (str): Path to the local Chroma database (used only if use_local is True)
    """
    config = load_config()

    # Initialize client based on mode
    if use_local:
        # Create a client for the local database
        local_db_path = Path(db_path).resolve()
        if not os.path.exists(local_db_path):
            print(f"Error: Local database path {local_db_path} does not exist.")
            print("Please create it first using create_qa_pairs_collection.py with the --local option.")
            return
        
        client = chromadb.PersistentClient(path=str(local_db_path))
        print(f"Connected to local database at: {local_db_path}")
    else:
        # Get Chroma server details from configuration
        chroma_host = config['datasources']['chroma']['host']
        chroma_port = config['datasources']['chroma']['port']
        print(f"Connecting to Chroma server at: {chroma_host}:{chroma_port}")

        # Initialize client with HTTP connection
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))

    # Check if the collection exists
    try:
        collections = client.list_collections()
        collection_exists = False
        
        # In newer versions, list_collections() returns collection objects with 'name' attributes
        for collection in collections:
            if hasattr(collection, 'name') and collection.name == collection_name:
                collection_exists = True
                break
        
        if not collection_exists:
            print(f"Collection '{collection_name}' does not exist.")
            return
            
        print(f"Found collection '{collection_name}', deleting...")
        client.delete_collection(name=collection_name)
        print(f"Successfully deleted collection: {collection_name}")
        
    except Exception as e:
        print(f"Error when working with collections: {str(e)}")
        
        try:    
            print("Attempting direct deletion...")
            client.delete_collection(name=collection_name)
            print(f"Successfully deleted collection: {collection_name}")
        except Exception as inner_e:
            if "does not exist" in str(inner_e):
                print(f"Collection '{collection_name}' does not exist.")
            else:
                print(f"Failed to delete collection: {str(inner_e)}")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Delete a collection from Chroma database')
    parser.add_argument('collection_name', help='Name of the Chroma collection to delete')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    args = parser.parse_args()

    delete_chroma_collection(args.collection_name, use_local=args.local, db_path=args.db_path)