"""
Qdrant Collection Listing Tool
==============================

This script lists all collections in a Qdrant vector database, showing collection names
and basic information about each collection.

Usage:
    python list_qdrant_collections.py [--cloud]

Arguments:
    --cloud              Use Qdrant Cloud instead of self-hosted Qdrant

Examples:
    # List collections from self-hosted Qdrant server (uses DATASOURCE_QDRANT_HOST/PORT from .env)
    python list_qdrant_collections.py

    # List collections from Qdrant Cloud (uses DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY from .env)
    python list_qdrant_collections.py --cloud

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

import yaml
import os
import re
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

def list_collections(use_cloud: bool = False):
    # Get Qdrant connection details
    qdrant_url, qdrant_api_key, qdrant_host, qdrant_port = get_qdrant_config(use_cloud=use_cloud)
    
    try:
        # Create Qdrant client based on cloud or self-hosted mode
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
    # Set up argument parser
    parser = argparse.ArgumentParser(description='List collections in Qdrant database')
    parser.add_argument('--cloud', action='store_true', 
                        help='Use Qdrant Cloud (requires DATASOURCE_QDRANT_URL and DATASOURCE_QDRANT_API_KEY in .env)')
    args = parser.parse_args()
    
    list_collections(use_cloud=args.cloud)