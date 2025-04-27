"""
Grocery Product Matcher for Price Comparison
============================================

This script creates or appends to an optimized vector database in Chroma for matching grocery products
across different stores. It processes product information, generates embeddings via Ollama, and upserts
vectors into a Chroma collection without overwriting existing data.

Usage:
    python create_grocery_deals_collection.py <collection_name> <file1> <store1> [<file2> <store2> ...]

Arguments:
    collection_name    Name of the Chroma collection to append to or create
    file1             Path to first store's JSON file containing product data
    store1            Name identifier for the first store
    file2, store2     Additional store files and their identifiers (optional)

Example:
    python create_grocery_deals_collection.py grocery_deals ./data/safeway.json safeway ./data/target.json target

Input JSON Format:
    [
        {
            "id": "123",
            "name": "Product Name",
            "brand": "Brand Name",
            "department": "Department",
            "size": "Size/Weight",
            "price": "10.99",
            "price_tag": "ea",
            "location": "Aisle A1",
            "extra_price": "2 for $20",
            "extra_price_tag": "sale",
            "multiple": 2,
            "validfrom": "2024-03-01",
            "validto": "2024-03-07"
        },
        ...
    ]

Requirements:
    - Running Ollama server (configured in /config/config.yaml)
    - Running Chroma server (configured in /config/config.yaml)
    - Input JSON files with product data

Key features:
    1. Reuses or creates a Chroma collection via get_or_create_collection()
    2. Generates embeddings client‑side and upserts to avoid duplicates
    3. Normalizes product descriptions for semantic matching
    4. Stores full metadata for filtering and retrieval
"""

import json
import yaml
import argparse
from typing import Dict, Any, List
from langchain_ollama import OllamaEmbeddings
from tqdm import tqdm
import chromadb
from pathlib import Path
import time


def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())


def process_product(product: Dict[str, Any], store_name: str) -> Dict[str, Any]:
    name = product["name"]
    department = product.get("department", "")
    brand = product.get("brand", "") or ""
    size = product.get("size", "") or ""
    embedding_text = f"{name} {brand} {size} {department}".strip()
    
    # Create metadata with no None values - replace with appropriate defaults
    metadata = {
        "id": str(product["id"]),
        "store": store_name,
        "name": name,
        "brand": brand,
        "department": department,
        "size": size,
        "price": str(product.get("price", "")),
        "price_tag": product.get("price_tag", ""),
        "location": product.get("location", "") or "",
        "extra_price": product.get("extra_price", "") or "",
        "extra_price_tag": product.get("extra_price_tag", "") or "",
        "multiple": product.get("multiple", 1) or 1,  # Default to 1 if None
        "validfrom": product.get("validfrom", "") or "",
        "validto": product.get("validto", "") or ""
    }
    
    # Ensure all metadata values are valid types (str, int, float, bool)
    for key, value in metadata.items():
        # Convert any remaining None values to empty strings
        if value is None:
            metadata[key] = ""
        # Ensure numbers are actual numbers, not strings that might be empty
        elif key == "multiple" and not isinstance(value, (int, float)):
            try:
                metadata[key] = int(value) if value else 1
            except (ValueError, TypeError):
                metadata[key] = 1
    
    return {
        "id": f"{store_name}_{product['id']}",
        "content": embedding_text,
        "metadata": metadata
    }


def load_store_data(file_path: str, store_name: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        products = json.load(f)
    print(f"Loaded {len(products)} products from {store_name}")
    return [process_product(prod, store_name) for prod in products]


def create_or_get_collection(client, collection_name, chroma_host, chroma_port):
    """
    Creates a new collection or gets an existing one using the updated API.
    Uses multiple approaches to handle different Chroma API versions.
    """
    collection = None
    
    # Print diagnostic information
    print(f"Attempting to create or get collection: '{collection_name}'")
    print(f"Using client type: {type(client).__name__}")
    
    # First check if collection exists - attempt 1
    print("Checking if collection exists - method 1...")
    try:
        collections = client.list_collections()
        print(f"Found {len(collections)} collections: {[c.name if hasattr(c, 'name') else str(c) for c in collections]}")
        
        collection_exists = False
        for coll in collections:
            if hasattr(coll, 'name') and coll.name == collection_name:
                collection_exists = True
                break
                
        if collection_exists:
            print(f"Collection '{collection_name}' already exists, using it...")
            collection = client.get_collection(name=collection_name)
            print(f"Successfully got collection reference")
            return collection
    except Exception as e:
        print(f"Error checking existing collections (method 1): {str(e)}")
    
    # Try direct get - attempt 2
    print("Trying direct get (method 2)...")
    try:
        collection = client.get_collection(name=collection_name)
        print(f"Successfully got collection via direct get")
        return collection
    except Exception as e:
        if "does not exist" in str(e):
            print(f"Collection '{collection_name}' confirmed to not exist yet.")
        else:
            print(f"Error directly getting collection: {str(e)}")
    
    # Try to create with minimal parameters - attempt 3
    print(f"Creating new collection (method 3)...")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Simplest possible call with just the name
            collection = client.create_collection(name=collection_name)
            print(f"Successfully created collection on attempt {attempt+1}")
            return collection
        except Exception as e:
            print(f"Creation attempt {attempt+1}/{max_retries} failed: {str(e)}")
            if "already exists" in str(e) or "already used" in str(e):
                print(f"Collection exists according to error, getting reference...")
                try:
                    collection = client.get_collection(name=collection_name)
                    print(f"Successfully got existing collection")
                    return collection
                except Exception as inner_e:
                    print(f"Error getting existing collection: {str(inner_e)}")
            
            # Wait before retry
            import time
            time.sleep(1)
    
    # Last resort - try with requests library - attempt 4
    print("Trying direct API call as last resort (method 4)...")
    try:
        import requests
        
        # Use the provided host and port variables instead of trying to extract from client
        host = chroma_host
        port = chroma_port
        
        url = f"http://{host}:{port}/api/v2/tenants/default_tenant/databases/default_database/collections"
        print(f"Making direct API call to: {url}")
        
        response = requests.post(url, json={"name": collection_name})
        print(f"API response: {response.status_code} - {response.text}")
        
        if response.status_code in (200, 201, 409):  # 409 = already exists
            # Try to get collection after creation
            collection = client.get_collection(name=collection_name)
            print(f"Collection created or accessed via direct API")
            return collection
        else:
            print(f"Direct API call failed with status {response.status_code}")
    except Exception as e:
        print(f"Direct API attempt failed: {str(e)}")
    
    # If we got here, all methods failed
    print("❌ All collection creation/access methods failed")
    print("Diagnostic information:")
    print(f"- Collection name: {collection_name}")
    print(f"- Client type: {type(client).__name__}")
    try:
        print(f"- Available collections: {[c.name if hasattr(c, 'name') else str(c) for c in client.list_collections()]}")
    except:
        print("- Could not list available collections")
        
    raise Exception(f"Cannot create or access collection '{collection_name}' after multiple attempts")


def ingest_to_chroma(
    store_data_list: List[tuple],
    ollama_base_url: str,
    chroma_host: str,
    chroma_port: str,
    model: str,
    collection_name: str,
    batch_size: int = 50
):
    print(f"Initializing Ollama embeddings at {ollama_base_url} with model {model}")
    embeddings = OllamaEmbeddings(
        model=model,
        base_url=ollama_base_url,
        client_kwargs={"timeout": 30.0}
    )
    # Test Ollama connection
    try:
        test_embedding = embeddings.embed_query("test connection")
        print("Successfully connected to Ollama server")
        print(f"Embedding dimensions: {len(test_embedding)}")
    except Exception as e:
        print(f"Failed to connect to Ollama server: {e}")
        return

    # Initialize Chroma client with HTTP connection
    try:
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
        print(f"Connected to Chroma server at {chroma_host}:{chroma_port}")
    except Exception as e:
        print(f"Error connecting to Chroma server: {str(e)}")
        return

    # Create or get collection using our helper function
    collection = create_or_get_collection(client, collection_name, chroma_host, chroma_port)
    if not collection:
        print("Failed to create or access collection")
        return
    
    print(f"Using collection: {collection_name}")

    # Aggregate items
    all_items = []
    for file_path, store_name in store_data_list:
        print(f"Processing data for {store_name}...")
        all_items.extend(load_store_data(file_path, store_name))

    print(f"Total products to index: {len(all_items)}")

    # Upsert in batches
    for i in tqdm(range(0, len(all_items), batch_size), desc="Upserting batches"):
        batch = all_items[i:i + batch_size]
        ids, embs, metas, docs = [], [], [], []
        for item in batch:
            try:
                emb = embeddings.embed_query(item["content"])
                ids.append(item["id"])
                embs.append(emb)
                
                # Process metadata to ensure it has no None values
                clean_metadata = {}
                for key, value in item["metadata"].items():
                    if value is None:
                        clean_metadata[key] = ""
                    else:
                        clean_metadata[key] = value
                
                metas.append(clean_metadata)
                docs.append(item["content"])
            except Exception as e:
                print(f"Error embedding {item['id']}: {e}")

        if ids:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Extra verification of metadata to avoid None values
                    for meta in metas:
                        for key in list(meta.keys()):
                            if meta[key] is None:
                                meta[key] = ""
                    
                    collection.upsert(
                        ids=ids,
                        embeddings=embs,
                        metadatas=metas,
                        documents=docs
                    )
                    print(f"Upserted {len(ids)} vectors to {collection_name}")
                    break
                except Exception as e:
                    print(f"Attempt {attempt+1}/{max_retries} - Error upserting batch: {str(e)}")
                    
                    if "None" in str(e) or "NoneType" in str(e):
                        print("Detected None values in metadata, cleaning up...")
                        # Clean any remaining None values at multiple levels
                        for i, meta in enumerate(metas):
                            for key, value in list(meta.items()):
                                if value is None:
                                    metas[i][key] = ""
                        continue
                        
                    if "_type" in str(e):
                        # Try without metadata if that's causing issues
                        try:
                            print("Trying upsert without metadata...")
                            collection.upsert(
                                ids=ids,
                                embeddings=embs,
                                documents=docs
                            )
                            print(f"Uploaded batch without metadata (fallback)")
                            break
                        except Exception as simple_e:
                            print(f"Simplified upsert also failed: {str(simple_e)}")
                    
                    if attempt == max_retries - 1:
                        print(f"Failed to upload batch after {max_retries} attempts")
                    else:
                        time.sleep(1)  # Wait before retry

    # Try to get collection count
    try:
        count = collection.count()
        print("\nIngestion complete!")
        print(f"Total vectors in collection: {count}")
    except Exception as e:
        print(f"\nIngestion process completed, but error getting count: {str(e)}")

    # Sample retrieval
    print("\nTesting retrieval with sample query...")
    test_query, n = "organic blueberries", 5
    
    try:
        test_emb = embeddings.embed_query(test_query)
        
        try:
            # Make sure we can access the collection
            count = collection.count()
            if count == 0:
                print("Collection is empty. Skipping test query.")
            else:
                results = collection.query(
                    query_embeddings=[test_emb],
                    n_results=min(n, count),  # Ensure we don't request more results than available
                    include=["documents", "metadatas", "distances"]
                )
                
                print(f"Top {min(n, count)} results for '{test_query}':")
                for idx, (doc, meta, dist) in enumerate(zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    print(f"\n{idx+1}. [{1 - dist:.4f}] {meta['store']} – {meta['name']} (${meta['price']})")
        except Exception as e:
            print(f"Error during test query: {str(e)}")
            print("This may be due to the collection not being properly initialized or empty.")
    except Exception as e:
        print(f"Error creating test embedding: {str(e)}")


def main():
    config = load_config()
    parser = argparse.ArgumentParser(
        description='Create or append grocery product matching database'
    )
    parser.add_argument('collection_name', help='Chroma collection to use')
    parser.add_argument(
        'store_files',
        nargs='+',
        help='Pairs: <json_file> <store_name>'
    )
    args = parser.parse_args()
    if len(args.store_files) % 2 != 0:
        raise ValueError("Provide JSON/file and store name pairs")
    store_data_list = [
        (args.store_files[i], args.store_files[i+1])
        for i in range(0, len(args.store_files), 2)
    ]
    conf = load_config()
    ingest_to_chroma(
        store_data_list,
        conf['ollama']['base_url'],
        conf['chroma']['host'],
        conf['chroma']['port'],
        conf['ollama']['embed_model'],
        args.collection_name
    )

if __name__ == "__main__":
    main()