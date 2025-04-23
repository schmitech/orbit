#!/usr/bin/env python3
"""
Test script to verify that grocery data was successfully loaded into a unified Chroma collection.
This script queries the collection and displays sample results for each store and across all stores.

Note: You must run the scrapers first to populate the database:
- python grocery_specials.py "Metro Market" ./weekly-specials/metromarket.json
- python grocery_specials.py "SunnySide Foods" ./weekly-specials/sunnyside.json

This script assumes the remote Chroma server is configured in config.yaml
"""

import os
import sys
import json
import yaml
from langchain_ollama import OllamaEmbeddings
import chromadb
from typing import List, Dict, Any, Optional

class GroceryDataStorage:
    """
    Storage class for grocery data using Chroma DB.
    Updated to work with newer Chroma API versions.
    """
    
    def __init__(self, collection_name="grocery-deals", config_path="../config/config.yaml"):
        """
        Initialize the storage with configuration.
        
        Args:
            collection_name: Name of the collection to use
            config_path: Path to the configuration file
        """
        self.collection_name = collection_name
        
        # Load configuration
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        
        # Chroma configuration
        self.chroma_host = config['chroma']['host']
        self.chroma_port = config['chroma']['port']
        
        # Ollama configuration
        self.ollama_base_url = config['ollama']['base_url']
        self.model = config['ollama']['embed_model']
        
        # Initialize Ollama embeddings
        self.embeddings = OllamaEmbeddings(
            model=self.model,
            base_url=self.ollama_base_url,
            client_kwargs={"timeout": 30.0}
        )
        
        # Connect to Chroma
        self.client = chromadb.HttpClient(host=self.chroma_host, port=int(self.chroma_port))
        
        # Get collection
        self._get_collection()
    
    def _get_collection(self):
        """
        Get the collection, using updated approach for newer Chroma API.
        """
        try:
            # Get existing collections
            collections = self.client.list_collections()
            collection_exists = False
            
            # Check if our collection exists
            for coll in collections:
                if hasattr(coll, 'name') and coll.name == self.collection_name:
                    collection_exists = True
                    break
            
            if collection_exists:
                self.collection = self.client.get_collection(name=self.collection_name)
            else:
                raise ValueError(f"Collection '{self.collection_name}' does not exist. Please create it first.")
                
        except Exception as e:
            raise Exception(f"Error accessing collection: {str(e)}")
    
    def get_all_stores(self) -> List[str]:
        """
        Get all stores in the database.
        
        Returns:
            List of store names
        """
        try:
            # Query to get all unique store names
            results = self.collection.get(
                include=["metadatas"],
                limit=10000  # Adjust as needed
            )
            
            if not results or not results["metadatas"]:
                return []
            
            # Extract unique store names
            stores = set()
            for metadata in results["metadatas"]:
                if metadata and "store" in metadata:
                    stores.add(metadata["store"])
            
            return sorted(list(stores))
        
        except Exception as e:
            print(f"Error getting stores: {str(e)}")
            return []
    
    def _clean_metadata_lists(self, metadatas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean metadata lists to ensure all values are valid types.
        
        Args:
            metadatas: List of metadata dictionaries
            
        Returns:
            Cleaned metadata list
        """
        cleaned = []
        for metadata in metadatas:
            if metadata:
                # Ensure no None values which newer Chroma API doesn't accept
                cleaned_metadata = {}
                for key, value in metadata.items():
                    if value is None:
                        cleaned_metadata[key] = ""
                    else:
                        cleaned_metadata[key] = value
                cleaned.append(cleaned_metadata)
            else:
                cleaned.append({})
        return cleaned
    
    def query_store(self, store_name: str, query: str, limit: int = 5, similarity_threshold: float = 0.3) -> Dict[str, Any]:
        """
        Query products from a specific store.
        
        Args:
            store_name: Name of the store to query
            query: Search query
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score for results to be included
            
        Returns:
            Query results
        """
        embedding = self.embeddings.embed_query(query)
        
        # Request more results than needed since we'll filter by similarity threshold
        max_results = limit * 3  # Request more to account for filtering
        
        # Using where filter with appropriate handling for store name
        results = self.collection.query(
            query_embeddings=[embedding],
            where={"store": store_name},
            n_results=max_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # Filter results by similarity threshold
        if results and "distances" in results and results["distances"] and results["distances"][0]:
            # Create lists to store filtered results
            filtered_docs = []
            filtered_metas = []
            filtered_distances = []
            
            # Process each result and only keep those above threshold
            for i, distance in enumerate(results["distances"][0]):
                similarity = 1 - distance
                if similarity >= similarity_threshold:
                    if "documents" in results and results["documents"] and results["documents"][0]:
                        filtered_docs.append(results["documents"][0][i])
                    if "metadatas" in results and results["metadatas"] and results["metadatas"][0]:
                        filtered_metas.append(results["metadatas"][0][i])
                    filtered_distances.append(distance)
            
            # Update results with filtered data (up to the requested limit)
            max_to_include = min(limit, len(filtered_docs))
            if "documents" in results and results["documents"]:
                results["documents"] = [filtered_docs[:max_to_include]]
            if "metadatas" in results and results["metadatas"]:
                results["metadatas"] = [filtered_metas[:max_to_include]]
            if "distances" in results:
                results["distances"] = [filtered_distances[:max_to_include]]
        
        # Make sure None values are handled for newer Chroma API
        if results and "metadatas" in results and results["metadatas"]:
            results["metadatas"] = [self._clean_metadata_lists(results["metadatas"][0])]
        
        return results
    
    def query_all_stores(self, query: str, limit: int = 5, similarity_threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Query products across all stores.
        
        Args:
            query: Search query
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1) for results to be included
            
        Returns:
            List of product dictionaries with store information
        """
        embedding = self.embeddings.embed_query(query)
        
        # Request more results than needed since we'll filter by similarity threshold
        max_results = limit * 3  # Request more to account for filtering
        
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=max_results,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results or "metadatas" not in results or not results["metadatas"] or not results["metadatas"][0]:
            return []
        
        # Process results into a more convenient format
        processed_results = []
        for i, (metadata, distance) in enumerate(zip(
            results["metadatas"][0],
            results["distances"][0] if "distances" in results and results["distances"] else [0] * len(results["metadatas"][0])
        )):
            # Calculate similarity score (1 - distance)
            similarity = 1 - distance
            
            # Skip results below the similarity threshold
            if similarity < similarity_threshold:
                continue
                
            # Clean metadata to handle None values
            cleaned_metadata = {}
            for key, value in metadata.items():
                if value is None:
                    cleaned_metadata[key] = ""
                else:
                    cleaned_metadata[key] = value
            
            # Create result dict
            result = cleaned_metadata.copy()
            
            # Add similarity score
            result["similarity"] = similarity
            
            processed_results.append(result)
        
        # Sort by similarity and limit to requested number
        processed_results.sort(key=lambda x: x["similarity"], reverse=True)
        return processed_results[:limit]

def test_store_query(storage, store_name, query="fresh", num_results=3):
    """
    Test querying products from a specific store.
    
    Args:
        storage: GroceryDataStorage instance
        store_name: Name of the store to query
        query: Search query to use
        num_results: Number of results to display
    
    Returns:
        bool: True if the query returns results, False otherwise
    """
    print(f"\n{'='*50}")
    print(f"Testing query for store: {store_name}")
    print(f"{'='*50}")
    
    try:
        # Use a lower similarity threshold for store-specific queries to show results
        # but still filter out completely unrelated items
        results = storage.query_store(store_name, query, num_results, similarity_threshold=0.1)
        
        if not results or 'documents' not in results or not results["documents"] or not results["documents"][0]:
            print(f"No relevant results found for '{query}' in {store_name}.")
            return False
        
        print(f"Found {len(results['documents'][0])} results for '{query}' in {store_name}:")
        
        for i, (doc, metadata, distance) in enumerate(zip(
            results["documents"][0], 
            results["metadatas"][0],
            results["distances"][0] if "distances" in results and results["distances"] else [0] * len(results["metadatas"][0])
        )):
            similarity = 1 - distance
            print(f"\n{i+1}. {metadata.get('name', 'Unknown')} - {metadata.get('price', 'N/A')} ({store_name})")
            print(f"   Similarity: {similarity:.4f}")
            if "description" in metadata and metadata["description"]:
                print(f"   {metadata['description']}")
            print(f"   Category: {metadata.get('category', 'N/A')}")
            # Use safer access for fields that might not exist
            if "unit" in metadata and metadata["unit"]:
                print(f"   Unit: {metadata['unit']}")
            if "unit_price" in metadata and metadata["unit_price"]:
                if isinstance(metadata["unit_price"], (int, float)):
                    print(f"   Unit Price: ${metadata['unit_price']:.2f}")
                else:
                    print(f"   Unit Price: {metadata['unit_price']}")
            # For grocery deals, use department instead of category if available
            if "department" in metadata and metadata["department"]:
                print(f"   Department: {metadata['department']}")
        
        return True
    
    except Exception as e:
        print(f"Error querying {store_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function to test the Chroma collection."""
    print("=" * 70)
    print("GROCERY DEALS DATABASE TEST (SINGLE COLLECTION)")
    print("=" * 70)
    print("Testing connection to remote Chroma server...")
    print("This script tests if data has been successfully loaded into the unified Chroma collection.")
    print("If no data is found, please run the scrapers first:")
    print("  python grocery_specials.py \"Metro Market\" ./weekly-specials/metromarket.json")
    print("  python grocery_specials.py \"SunnySide Foods\" ./weekly-specials/sunnyside.json")
    print("=" * 70)
    
    # Get query from command line arguments
    if len(sys.argv) > 1:
        query = sys.argv[1]
    else:
        # Prompt user for a query if not provided as an argument
        query = input("Enter search query (or press Enter for default 'fresh'): ").strip() or "fresh"
    
    # Use standard config path
    config_path = "../config/config.yaml"
    
    print(f"Using search query: '{query}'")

    
    try:
        # Initialize storage with the config path
        print(f"Initializing storage with config from: {config_path}")
        storage = GroceryDataStorage(config_path=config_path)
        
        # Print connection information
        print(f"Connected to Chroma server at: {storage.chroma_host}:{storage.chroma_port}")
        print(f"Using Ollama embedding model: {storage.model}")
        print(f"Using collection: {storage.collection_name}")
        print(f"Using search query: '{query}'")
        
        # Get list of all stores in the database
        stores = storage.get_all_stores()
        print(f"\nFound {len(stores)} stores in the database: {', '.join(stores)}")
        
        if not stores:
            print("\nNo stores found in the database. Please run the scrapers first to populate the database.")
            print("  python grocery_specials.py \"Metro Market\" ./weekly-specials/metromarket.json")
            print("  python grocery_specials.py \"SunnySide Foods\" ./weekly-specials/sunnyside.json")
            return
        
        # Test store-specific queries
        successful_stores = []
        for store in stores:
            if test_store_query(storage, store, query=query):
                successful_stores.append(store)
        
        # Summary
        print("\n" + "="*50)
        print("Test Summary")
        print("="*50)
        print(f"Successfully tested {len(successful_stores)} out of {len(stores)} stores.")
        if successful_stores:
            print("Successful stores:")
            for store in successful_stores:
                print(f"- {store}")
        else:
            print("\nNo store queries were successful.")
            print("Please make sure you've run the scrapers to populate the database:")
            print("  python grocery_specials.py \"Metro Market\" ./weekly-specials/metromarket.json")
            print("  python grocery_specials.py \"SunnySide Foods\" ./weekly-specials/sunnyside.json")
        
        # Test a cross-store query
        if len(successful_stores) > 0:
            print("\n" + "="*50)
            print("Testing Cross-Store Query")
            print("="*50)
            
            try:
                print(f"Searching for '{query}' across all stores...")
                results = storage.query_all_stores(query, 5)
                
                if results:
                    print(f"\nFound {len(results)} results for '{query}' across all stores:")
                    for i, item in enumerate(results):
                        print(f"\n{i+1}. {item.get('name', 'Unknown')} - {item.get('price', 'N/A')} ({item.get('store', 'Unknown')})")
                        if "similarity" in item:
                            print(f"   Similarity: {item['similarity']}")
                        if "description" in item and item["description"]:
                            print(f"   {item['description']}")
                        # Use safer access for fields that might not exist
                        print(f"   Category: {item.get('category', 'N/A')}")
                        if "unit" in item and item["unit"]:
                            print(f"   Unit: {item['unit']}")
                        if "unit_price" in item and item["unit_price"]:
                            if isinstance(item["unit_price"], (int, float)):
                                print(f"   Unit Price: ${item['unit_price']:.2f}")
                            else:
                                print(f"   Unit Price: {item['unit_price']}")
                        # For grocery deals, use department instead of category if available
                        if "department" in item and item["department"]:
                            print(f"   Department: {item['department']}")
                else:
                    print(f"No results found for '{query}' across all stores.")
            except Exception as e:
                print(f"Error in cross-store query: {e}")
                import traceback
                traceback.print_exc()
    
    except Exception as e:
        print(f"Error initializing storage: {e}")
        import traceback
        traceback.print_exc()
        print("\nPlease check your configuration file and ensure the Chroma and Ollama servers are running.")

if __name__ == "__main__":
    main()