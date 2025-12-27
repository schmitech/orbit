"""
Qdrant Collection Deletion Tool
===============================

This script deletes a specified collection from a Qdrant vector database.

Usage:
    python delete_qdrant_collection.py <collection_name> [--cloud]

Arguments:
    collection_name      Name of the Qdrant collection to delete
    --cloud              Use Qdrant Cloud instead of self-hosted Qdrant

Examples:
    # Delete collection from self-hosted Qdrant server (uses DATASOURCE_QDRANT_HOST/PORT from .env)
    python delete_qdrant_collection.py city_faq

    # Delete collection from Qdrant Cloud (uses DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY from .env)
    python delete_qdrant_collection.py city_faq --cloud

Process:
    1. Connects to the Qdrant server
    2. Checks if the specified collection exists
    3. Deletes the collection if it exists
    4. Provides confirmation of the deletion

Environment Variables:
    For self-hosted Qdrant (default):
        DATASOURCE_QDRANT_HOST - Qdrant server host (default: localhost)
        DATASOURCE_QDRANT_PORT - Qdrant server port (default: 6333)
    
    For Qdrant Cloud (--cloud flag):
        DATASOURCE_QDRANT_URL  - Qdrant Cloud URL (required)
        DATASOURCE_QDRANT_API_KEY - Qdrant Cloud API key (required)

Notes:
    - The script uses server connection details from config.yaml and .env file
    - This script is part of a suite of Qdrant utilities:
      * create_qdrant_collection.py - Creates and populates collections
      * query_qdrant_collection.py - Queries collections with semantic search
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
    """Load configuration files from project root"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Get the project root (2 levels up: scripts -> qdrant -> project_root)
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

def resolve_env_placeholder(value):
    """Resolve environment variable placeholders like ${VAR_NAME} or ${VAR_NAME:-default}"""
    if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
        inner = value[2:-1]  # Remove ${ and }
        # Handle ${VAR:-default} syntax
        if ':-' in inner:
            env_var, default = inner.split(':-', 1)
            return os.getenv(env_var, default)
        else:
            return os.getenv(inner, '')  # Return empty string if env var not found
    return value

def get_qdrant_config(use_cloud: bool = False):
    """Get Qdrant configuration with proper fallbacks
    
    Args:
        use_cloud: If True, use cloud configuration (URL + API key), 
                   otherwise use self-hosted (host + port)
    
    Returns:
        For cloud mode: tuple(url, api_key, None, None)
        For self-hosted: tuple(None, None, host, port)
    """
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
    
    if use_cloud:
        # Cloud mode: use URL and API key
        url = resolve_env_placeholder(qdrant_config.get('url', ''))
        api_key = resolve_env_placeholder(qdrant_config.get('api_key', ''))
        
        # Also check direct environment variables as fallback
        if not url:
            url = os.getenv('DATASOURCE_QDRANT_URL', '')
        if not api_key:
            api_key = os.getenv('DATASOURCE_QDRANT_API_KEY', '')
        
        if not url:
            raise ValueError("DATASOURCE_QDRANT_URL is required for cloud mode. "
                           "Please set it in your .env file.")
        if not api_key:
            raise ValueError("DATASOURCE_QDRANT_API_KEY is required for cloud mode. "
                           "Please set it in your .env file.")
        
        print(f"Qdrant Cloud config: url={url[:50]}...")
        return url, api_key, None, None
    else:
        # Self-hosted mode: use host and port
        host = resolve_env_placeholder(qdrant_config.get('host', 'localhost'))
        port = resolve_env_placeholder(qdrant_config.get('port', 6333))
        
        # Also check direct environment variables as fallback
        if not host or host == 'localhost':
            env_host = os.getenv('DATASOURCE_QDRANT_HOST')
            if env_host:
                host = env_host
        
        env_port = os.getenv('DATASOURCE_QDRANT_PORT')
        if env_port:
            port = env_port
        
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
        
        return None, None, host, port

def delete_qdrant_collection(collection_name: str, use_cloud: bool = False):
    """
    Delete a collection from the Qdrant database.
    
    Args:
        collection_name (str): Name of the collection to delete
        use_cloud (bool): If True, use Qdrant Cloud instead of self-hosted
    """
    # Get Qdrant connection details
    qdrant_url, qdrant_api_key, qdrant_host, qdrant_port = get_qdrant_config(use_cloud=use_cloud)

    try:
        # Initialize Qdrant client based on cloud or self-hosted mode
        if qdrant_url and qdrant_api_key:
            # Cloud mode: use URL and API key
            client = QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=30
            )
            print(f"Connected to Qdrant Cloud at {qdrant_url[:50]}...")
        else:
            # Self-hosted mode: use host and port
            print(f"Connecting to Qdrant server at: {qdrant_host}:{qdrant_port}")
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
    parser.add_argument('--cloud', action='store_true', 
                        help='Use Qdrant Cloud (requires DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY in .env)')
    args = parser.parse_args()

    delete_qdrant_collection(args.collection_name, use_cloud=args.cloud)