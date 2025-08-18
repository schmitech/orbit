"""
Pinecone Index Deletion Tool
============================

This script deletes a specified index from Pinecone vector database.

Usage:
    python delete_pinecone_index.py <index_name>

Arguments:
    index_name           Name of the Pinecone index to delete

Examples:
    # Delete index from Pinecone cloud
    python delete_pinecone_index.py city-faq

Process:
    1. Connects to the Pinecone service
    2. Checks if the specified index exists
    3. Deletes the index if it exists
    4. Provides confirmation of the deletion

Notes:
    - Requires DATASOURCE_PINECONE_API_KEY environment variable to be set
    - This script is part of a suite of Pinecone utilities:
      * create_pinecone_index.py - Creates and populates indexes
      * query_pinecone_index.py - Queries indexes with semantic search
      * list_pinecone_indexes.py - Lists available indexes
      * delete_pinecone_index.py - Deletes indexes
"""

import sys
import os
import argparse
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

def delete_pinecone_index(index_name: str):
    """
    Delete an index from the Pinecone database.
    
    Args:
        index_name (str): Name of the index to delete
    """
    print(f"Connecting to Pinecone service...")

    try:
        # Initialize Pinecone client
        pc = get_pinecone_client()
        
        # List existing indexes
        existing_indexes = pc.list_indexes()
        index_exists = False
        
        # Check if index exists
        for idx in existing_indexes:
            if idx.name == index_name:
                index_exists = True
                # Get index details before deletion
                index_info = pc.describe_index(index_name)
                vector_count = index_info.total_vector_count if hasattr(index_info, 'total_vector_count') else 'Unknown'
                print(f"Found index '{index_name}' with {vector_count} vectors")
                break
        
        if not index_exists:
            print(f"Index '{index_name}' does not exist.")
            return
        
        print("Deleting index...")
        
        # Delete the index
        pc.delete_index(index_name)
        print(f"Successfully deleted index: {index_name}")
                
    except Exception as e:
        print(f"Error connecting to Pinecone service: {str(e)}")
        print("Please check your API key and ensure you have network connectivity.")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Delete an index from Pinecone database')
    parser.add_argument('index_name', help='Name of the Pinecone index to delete')
    args = parser.parse_args()

    delete_pinecone_index(args.index_name)