#!/usr/bin/env python3
"""
Minimal script to test Hugging Face API directly without any libraries.
"""

import os
import sys
import requests
import json

# Get API token from environment
api_token = os.environ.get("HUGGINGFACE_API_KEY")
if not api_token:
    print("Please set HUGGINGFACE_API_KEY environment variable")
    sys.exit(1)

print(f"API token length: {len(api_token)}")
print(f"Last 4 characters: {api_token[-4:]}")

# Test normal Hugging Face API
print("\n1. Testing Hugging Face API directly")
api_url = "https://api-inference.huggingface.co/models/gpt2"
headers = {
    "Authorization": f"Bearer {api_token}",
    "Content-Type": "application/json"
}
payload = {
    "inputs": "Hello, this is a test."
}

try:
    response = requests.post(api_url, headers=headers, json=payload)
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        print("Success!")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Exception: {e}")

# Test Hugging Face Hub API (what the NLP class might be using)
print("\n2. Testing Hugging Face Hub API")
hub_url = "https://huggingface.co/api/models/gpt2"
try:
    response = requests.get(hub_url, headers=headers)
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        print("Success!")
        # Don't print full response as it's large
        print("Hub API returned model information successfully")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Exception: {e}")

# Test with token in query parameter instead
print("\n3. Testing with token in query parameter")
hub_url_with_token = f"https://huggingface.co/api/models/gpt2?auth_token={api_token}"
try:
    response = requests.get(hub_url_with_token)
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        print("Success!")
        print("Token works as query parameter")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Exception: {e}")

# Check if token is well-formed
print("\n4. Checking token format")
if api_token.startswith("hf_"):
    print("✅ Token has correct prefix (hf_)")
else:
    print("❌ Token doesn't have the expected prefix (hf_)")
    print("Token should start with 'hf_'")

if len(api_token) >= 30:
    print("✅ Token has sufficient length")
else:
    print("❌ Token seems too short for a Hugging Face token")

print("\nDebug recommendations:")
print("1. Verify your token at: https://huggingface.co/settings/tokens")
print("2. Generate a fresh token if needed")
print("3. Make sure there are no extra spaces or newlines in your token")
print("4. Check token permissions (should have 'read' at minimum)") 