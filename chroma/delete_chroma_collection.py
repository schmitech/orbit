import sys
import yaml
import chromadb

def load_config():
    with open('../config.yaml', 'r') as file:
        return yaml.safe_load(file)

def delete_chroma_collection(collection_name: str):
    config = load_config()

    # Get Chroma server details from configuration
    chroma_host = config['chroma']['host']
    chroma_port = config['chroma']['port']
    print(f"Connecting to Chroma server at: {chroma_host}:{chroma_port}")

    # Initialize client with HTTP connection
    client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))

    # Check if the collection exists
    existing_collections = client.list_collections()
    if collection_name not in existing_collections:
        print(f"Collection '{collection_name}' does not exist.")
        return

    # Delete the collection
    client.delete_collection(collection_name)
    print(f"Deleted collection: {collection_name}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python delete_chroma_collection.py <collection_name>")
        sys.exit(1)

    collection_name = sys.argv[1]
    delete_chroma_collection(collection_name) 