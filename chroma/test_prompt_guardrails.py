import requests
import yaml
import json
import sys

# Get query from command line argument
if len(sys.argv) < 2:
    print("Usage: python test_prompt_guardrails.py 'your query here'")
    sys.exit(1)

query = sys.argv[1]

# Load config
with open('../server/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Extract Ollama config and guardrail prompt
ollama_config = config['ollama']
guardrail_prompt = config['system']['guardrail_prompt']

# Debug logging
print("\n=== Configuration ===")
print("Ollama config:", json.dumps(ollama_config, indent=2))
print("\n=== Guardrail Prompt ===")
print(guardrail_prompt)
print("\n=== Query ===")
print(query)

# Create request payload with the parameters
payload = {
    "model": ollama_config["model"],
    "prompt": f"{guardrail_prompt}\n\nQuery: {query}\n\nRespond with ONLY 'SAFE: true' or 'SAFE: false':",
    "temperature": 0.0,  # Set to 0 for deterministic response
    "top_p": 1.0,
    "top_k": 1,
    "repeat_penalty": ollama_config["repeat_penalty"],
    "num_predict": 20,  # Limit response length
    "stream": False
}

# Debug logging for final prompt
print("\n=== Final Prompt to Ollama ===")
print(payload["prompt"])

try:
    # Make request to Ollama
    response = requests.post(f"{ollama_config['base_url']}/api/generate", json=payload)
    response_data = response.json()
    
    # Print response
    print("\n=== Response ===")
    print("Response:", response_data.get("response", "No response received").strip())
    
    # Check if the response matches the expected format
    resp = response_data.get("response", "").strip()
    if resp not in ["SAFE: true", "SAFE: false"]:
        print("\nWarning: Response does not match expected format. Should be exactly 'SAFE: true' or 'SAFE: false'.")
        
except Exception as e:
    print(f"\n=== Error ===")
    print(f"Error: {str(e)}")