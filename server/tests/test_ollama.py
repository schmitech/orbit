"""
Ollama Service Check Script

This script tests the connection and functionality of the Ollama service by sending
a test query and verifying the response. It's useful for:
- Verifying Ollama is running and accessible
- Testing the model configuration
- Checking response format and content
- Debugging connection issues

Usage:
    python3 check_ollama.py [query]

    If no query is provided, it will use a default test query.

Example:
    python3 check_ollama.py "What is the cost of the Beginner English fee for service course?"
"""

import requests
import yaml
import json
import sys
import os

# Get query from command line or use default
query = sys.argv[1] if len(sys.argv) > 1 else "What is the cost of the Beginner English fee for service course?"

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Get the absolute path to the backend directory (parent of server)
backend_dir = os.path.dirname(server_dir)

# Add server directory to Python path
sys.path.append(server_dir)

# Load config using os.path.join for cross-platform compatibility
config_path = os.path.join(backend_dir, 'server', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

# Extract Ollama config from inference section
ollama_config = config.get('inference', {}).get('ollama', {})
if not ollama_config:
    # Fallback to root level for backward compatibility
    ollama_config = config.get('ollama', {})

print("Loaded configuration:", json.dumps(ollama_config, indent=2))

# Create request payload with the parameters
payload = {
    "model": ollama_config["model"],
    "prompt": query,
    "temperature": ollama_config.get("temperature", 0.1),
    "top_p": ollama_config.get("top_p", 0.8),
    "top_k": ollama_config.get("top_k", 20),
    "repeat_penalty": ollama_config.get("repeat_penalty", 1.1),
    "num_predict": ollama_config.get("num_predict", 1024),
    "stream": False  # Force non-streaming for testing
}

try:
    # Make request to Ollama
    print(f"\nSending request to {ollama_config['base_url']}/api/generate")
    print(f"Using model: {ollama_config['model']}")
    print(f"Query: {query}")
    
    response = requests.post(
        f"{ollama_config['base_url']}/api/generate",
        json=payload,
        timeout=30  # Add timeout
    )
    
    # Check if the request was successful
    if response.status_code != 200:
        print(f"\nError: Server returned status code {response.status_code}")
        print("Response:", response.text)
        sys.exit(1)
    
    # Try to parse the response
    try:
        response_data = response.json()
        if "response" in response_data:
            print("\nResponse:", response_data["response"])
        else:
            print("\nUnexpected response format:")
            print(json.dumps(response_data, indent=2))
    except json.JSONDecodeError as e:
        print("\nError parsing JSON response:")
        print("Raw response:", response.text)
        print("Error details:", str(e))
        sys.exit(1)

except requests.exceptions.RequestException as e:
    print("\nError connecting to Ollama service:")
    print("Error type:", type(e).__name__)
    print("Error details:", str(e))
    if isinstance(e, requests.exceptions.ConnectionError):
        print("\nPlease check if Ollama is running and accessible at:", ollama_config['base_url'])
    sys.exit(1)
except Exception as e:
    print("\nUnexpected error:")
    print("Error type:", type(e).__name__)
    print("Error details:", str(e))
    sys.exit(1)