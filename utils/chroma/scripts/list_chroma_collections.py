import chromadb
import yaml
from pathlib import Path
def load_config():
    CONFIG_PATH = Path(__file__).resolve().parents[3] / "server" / "config.yaml"
    return yaml.safe_load(CONFIG_PATH.read_text())

# Load configuration
config = load_config()

# Create client using config values
chroma_host = config['datasources']['chroma']['host']
chroma_port = config['datasources']['chroma']['port']
client = chromadb.HttpClient(host=chroma_host, port=chroma_port)

# Get list of all collections
collections = client.list_collections()

# Print collection names
print("Available collections:")
for collection_name in collections:
    print(f"- {collection_name}")