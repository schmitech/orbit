"""
Chroma Collection Listing Tool
=============================

This script lists all collections in a Chroma vector database, supporting both
remote server and local filesystem modes.

Usage:
    python list_chroma_collections.py [--local] [--db-path PATH]

Arguments:
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"

Examples:
    # List collections from remote Chroma server (defined in config.yaml)
    python list_chroma_collections.py
    
    # List collections from local filesystem database
    python list_chroma_collections.py --local
    
    # List collections from a specific local database path
    python list_chroma_collections.py --local --db-path /path/to/my/chroma_db

Notes:
    - For remote mode, the script uses server connection details from config.yaml
    - For local mode, it connects to a PersistentClient at the specified path
    - This script is part of a suite of Chroma utilities that all support both modes:
      * create_qa_pairs_collection.py - Creates and populates collections
      * query_qa-pairs.py - Queries collections with semantic search
      * list_chroma_collections.py - Lists available collections
"""

import chromadb
import yaml
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

def list_collections(use_local=False, db_path="./chroma_db"):
    # Load configuration
    config = load_config()
    
    # Create client based on mode
    if use_local:
        # Create a client for the local database
        local_db_path = Path(db_path).resolve()
        if not os.path.exists(local_db_path):
            print(f"Error: Local database path {local_db_path} does not exist.")
            print("Please create it first using create_qa_pairs_collection.py with the --local option.")
            return
        
        client = chromadb.PersistentClient(path=str(local_db_path))
        print(f"Listing collections from local database at: {local_db_path}")
    else:
        # Create client using config values for remote server
        chroma_host = config['datasources']['chroma']['host']
        chroma_port = config['datasources']['chroma']['port']
        client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        print(f"Listing collections from Chroma server at: {chroma_host}:{chroma_port}")

    # Get list of all collections
    collections = client.list_collections()

    # Print collection names
    print("\nAvailable collections:")
    if not collections:
        print("No collections found.")
    else:
        for collection in collections:
            print(f"- {collection.name}")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='List all collections in a Chroma database')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    args = parser.parse_args()
    
    # List collections based on mode
    list_collections(use_local=args.local, db_path=args.db_path)