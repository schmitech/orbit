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

# Get query from command line or use default
query = sys.argv[1] if len(sys.argv) > 1 else "What is the cost of the Beginner English fee for service course?"

# Load config
with open('../../config/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Extract Ollama config
ollama_config = config['ollama']
print("Loaded configuration:", json.dumps(ollama_config, indent=2))

# Create request payload with the parameters
payload = {
    "model": ollama_config["model"],
    "prompt": query,
    "temperature": ollama_config["temperature"],
    "top_p": ollama_config["top_p"],
    "top_k": ollama_config["top_k"],
    "repeat_penalty": ollama_config["repeat_penalty"],
    "num_predict": ollama_config["num_predict"],
    "stream": False
}

try:
    # Make request to Ollama
    response = requests.post(f"{ollama_config['base_url']}/api/generate", json=payload)
    response_data = response.json()
    
    # Print response
    print("\nResponse:", response_data["response"])
except requests.exceptions.RequestException as e:
    print("\nError connecting to Ollama service:", str(e))
except json.JSONDecodeError as e:
    print("\nError parsing response:", str(e))
    print("Raw response:", response.text)
except Exception as e:
    print("\nUnexpected error:", str(e))