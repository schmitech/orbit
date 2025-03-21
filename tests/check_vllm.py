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