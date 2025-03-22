"""
Ollama Service Check Script

This script tests the connection and functionality of the Ollama service by sending
a test query and verifying the response. It's useful for:
- Verifying Ollama is running and accessible
- Testing the model configuration
- Checking response format and content
- Debugging connection issues

Usage:
    python3 check_ollama.py

The script will:
1. Load the Ollama configuration from config.yaml
2. Send a test query to the Ollama service
3. Display the configuration and response

Example Output:
    Loaded configuration: {
        "base_url": "http://localhost:11434",
        "model": "gemma3:1b",
        ...
    }
    Response: [Ollama's response to the test query]
"""

import requests
import yaml
import json

# Load config
with open('../server/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Extract Ollama config
ollama_config = config['ollama']
print("Loaded configuration:", json.dumps(ollama_config, indent=2))

# Create request payload with the parameters
payload = {
    "model": ollama_config["model"],
    "prompt": "What is the cost of the Beginner English fee for service course?",
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