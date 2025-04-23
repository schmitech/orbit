import chromadb
import yaml

def load_config():
    with open('../config/config.yaml', 'r') as file:
        return yaml.safe_load(file)

# Load configuration
config = load_config()

# Create client using config values
chroma_host = config['chroma']['host']
chroma_port = config['chroma']['port']
client = chromadb.HttpClient(host=chroma_host, port=chroma_port)

# Get list of all collections
collections = client.list_collections()

# Print collection names
print("Available collections:")
for collection_name in collections:
    print(f"- {collection_name}")