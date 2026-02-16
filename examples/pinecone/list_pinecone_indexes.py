"""
Pinecone Index Listing Tool
===========================

This script lists all indexes in a Pinecone vector database, showing index names
and basic information about each index.

Usage:
    python list_pinecone_indexes.py

Examples:
    # List indexes from Pinecone cloud
    python list_pinecone_indexes.py

Notes:
    - Requires DATASOURCE_PINECONE_API_KEY environment variable to be set
    - This script is part of a suite of Pinecone utilities:
      * create_pinecone_index.py - Creates and populates indexes
      * query_pinecone_index.py - Queries indexes with semantic search
      * list_pinecone_indexes.py - Lists available indexes
      * delete_pinecone_index.py - Deletes indexes
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone

def get_pinecone_client():
    """Initialize and return Pinecone client"""
    # Load environment variables from main project directory
    project_env_path = Path(__file__).resolve().parents[2] / ".env"
    if project_env_path.exists():
        load_dotenv(project_env_path, override=True)
        print(f"Loading environment variables from: {project_env_path}")
    else:
        print(f"Warning: .env file not found at {project_env_path}")
    
    api_key = os.getenv('DATASOURCE_PINECONE_API_KEY')
    if not api_key:
        raise ValueError("DATASOURCE_PINECONE_API_KEY environment variable not set")
    
    pc = Pinecone(api_key=api_key)
    return pc

def list_indexes():
    print("Connecting to Pinecone service...")
    
    try:
        # Create Pinecone client
        pc = get_pinecone_client()
        
        # Get list of all indexes
        indexes = pc.list_indexes()
        
        # Print index information
        print("\nAvailable indexes:")
        if not indexes:
            print("No indexes found.")
        else:
            for index_info in indexes:
                try:
                    # Get detailed index info
                    index_name = index_info.name
                    detailed_info = pc.describe_index(index_name)
                    
                    print(f"- {index_name}")
                    
                    # Print dimensions if available
                    if hasattr(detailed_info, 'dimension'):
                        print(f"  Dimensions: {detailed_info.dimension}")
                    
                    # Print metric if available
                    if hasattr(detailed_info, 'metric'):
                        print(f"  Metric: {detailed_info.metric}")
                    
                    # Print vector count if available
                    if hasattr(detailed_info, 'total_vector_count'):
                        print(f"  Vectors: {detailed_info.total_vector_count}")
                    
                    # Print status if available
                    if hasattr(detailed_info, 'status'):
                        status = detailed_info.status
                        if isinstance(status, dict) and 'ready' in status:
                            print(f"  Ready: {status['ready']}")
                    
                    # Print spec information
                    if hasattr(detailed_info, 'spec'):
                        spec = detailed_info.spec
                        if hasattr(spec, 'serverless'):
                            serverless = spec.serverless
                            if hasattr(serverless, 'cloud') and hasattr(serverless, 'region'):
                                print(f"  Type: Serverless ({serverless.cloud}/{serverless.region})")
                        elif hasattr(spec, 'pod'):
                            print("  Type: Pod-based")
                    
                    print()
                except Exception as e:
                    print(f"- {index_name} (Error getting details: {str(e)})")
                    
    except Exception as e:
        print(f"Error connecting to Pinecone service: {str(e)}")
        print("Please check your API key and ensure you have network connectivity.")

if __name__ == "__main__":
    list_indexes()