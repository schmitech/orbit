"""
vLLM Service Check Script

This script tests the connection and functionality of the vLLM service by sending
a test query and verifying the response. It's useful for:
- Verifying vLLM server is running and accessible
- Testing the model configuration
- Checking response format and content
- Debugging connection issues
- Validating API endpoint functionality

Usage:
    python3 check_vllm.py

The script will:
1. Load the vLLM configuration from config.yaml
2. Send a test query to the vLLM service
3. Display the configuration, request payload, and response
4. Handle various types of errors that might occur

Example Output:
    Loaded vLLM configuration: {
        "base_url": "http://15.156.8.133:5000",
        "model": "VLLMQwen2.5-14B",
        ...
    }
    
    Sending request to vLLM server...
    Payload: {
        "model": "VLLMQwen2.5-14B",
        "prompt": "What is the capital of Canada?",
        ...
    }
    
    Response status code: 200
    Response content: [vLLM's response to the test query]
"""

import requests
import yaml
import json

# Load config
with open('../server/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Extract vLLM config
vllm_config = config['vllm']
print("Loaded vLLM configuration:", json.dumps(vllm_config, indent=2))

# Create request payload for vLLM
payload = {
    'model': vllm_config['model'],
    'prompt': 'What is the capital of Canada?',
    'max_tokens': vllm_config['max_tokens'],
    'temperature': vllm_config['temperature'],
    'top_p': vllm_config['top_p'],
    'frequency_penalty': vllm_config['frequency_penalty'],
    'presence_penalty': vllm_config['presence_penalty']
}

print("\nSending request to vLLM server...")
print("Payload:", json.dumps(payload, indent=2))

try:
    # Make request to vLLM server
    response = requests.post(
        f"{vllm_config['base_url']}/v1/completions",
        json=payload,
        headers={'Content-Type': 'application/json'}
    )
    
    print("\nResponse status code:", response.status_code)
    print("Response headers:", response.headers)
    
    response_data = response.json()
    print("\nFull response:", json.dumps(response_data, indent=2))
    
    if 'choices' in response_data and len(response_data['choices']) > 0:
        print("\nResponse content:", response_data['choices'][0]['text'])
    else:
        print("\nNo choices in response. Response structure:", json.dumps(response_data, indent=2))

except requests.exceptions.RequestException as e:
    print("\nRequest error:", str(e))
except json.JSONDecodeError as e:
    print("\nJSON decode error:", str(e))
    print("Raw response:", response.text)
except Exception as e:
    print("\nUnexpected error:", str(e))