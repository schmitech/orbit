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

# Make request to Ollama
response = requests.post(f"{ollama_config['base_url']}/api/generate", json=payload)

# Print response
print("Response:", response.json()["response"])