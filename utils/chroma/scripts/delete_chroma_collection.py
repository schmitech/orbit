"""
Chroma Collection Deletion Tool
==============================

This script deletes a specified collection from a Chroma vector database.
It provides a simple way to remove collections that are no longer needed.

Usage:
    python delete_chroma_collection.py <collection_name>

Arguments:
    collection_name: Name of the Chroma collection to delete

Example:
    python delete_chroma_collection.py my_qa_collection

Requirements:
    - config.yaml file with Chroma configuration
    - Running Chroma server

Configuration (config.yaml):
    chroma:
      host: Hostname of the Chroma server
      port: Port of the Chroma server

Process:
    1. Connects to the Chroma server using configuration from config.yaml
    2. Checks if the specified collection exists
    3. Deletes the collection if it exists
    4. Provides confirmation of the deletion
"""

import sys
import yaml
import chromadb
import argparse

def load_config():
    """
    Load configuration from config.yaml file.
    
    Returns:
        dict: Configuration parameters
    """
    with open('../config/config.yaml', 'r') as file:
        return yaml.safe_load(file)

def delete_chroma_collection(collection_name: str):
    """
    Delete a collection from the Chroma database.
    
    Args:
        collection_name (str): Name of the collection to delete
    """
    config = load_config()

    # Get Chroma server details from configuration
    chroma_host = config['datasources']['chroma']['host']
    chroma_port = config['datasources']['chroma']['port']
    print(f"Connecting to Chroma server at: {chroma_host}:{chroma_port}")

    # Initialize client with HTTP connection
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))

    # Check if the collection exists using the new API approach
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
    args = parser.parse_args()

    delete_chroma_collection(args.collection_name)