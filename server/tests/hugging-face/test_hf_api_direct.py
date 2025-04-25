#!/usr/bin/env python3
"""
Test the Hugging Face API directly using HTTP requests.
This bypasses the hugging_py_face library to check the API connection directly.
"""

import argparse
import json
import os
import sys
import requests

def mask_api_key(api_key):
    """Return a masked version of the API key."""
    if len(api_key) <= 4:
        return "****"
    return "****" + api_key[-4:]

def test_api_key_direct(api_key, model="gpt2"):
    """Test the Hugging Face API key using direct HTTP requests."""
    api_url = f"https://api-inference.huggingface.co/models/{model}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": "Hello, this is a test.",
        "parameters": {
            "max_new_tokens": 5,
            "temperature": 0.7,
            "return_full_text": False
        }
    }
    
    print(f"Testing Hugging Face API key: {mask_api_key(api_key)} (length: {len(api_key)})")
    print(f"Model: {model}")
    print(f"API URL: {api_url}")
    print("Sending request...")
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        status_code = response.status_code
        
        print(f"Response status code: {status_code}")
        
        if status_code == 200:
            result = response.json()
            print("✅ API key is working properly!")
            print(f"Response: {json.dumps(result, indent=2)}")
            return True
        elif status_code == 403:
            print("❌ Authentication error (403 Forbidden)")
            print("Your API key might be invalid or expired.")
            print("Get a new token at: https://huggingface.co/settings/tokens")
            return False
        elif status_code == 401:
            print("❌ Unauthorized (401)")
            print("Your API key is missing or improperly formatted.")
            return False
        else:
            print(f"❌ Request failed with status code: {status_code}")
            print(f"Response text: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_no_auth(model="gpt2"):
    """Test if the API works without authentication."""
    api_url = f"https://api-inference.huggingface.co/models/{model}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": "Hello, this is a test.",
        "parameters": {
            "max_new_tokens": 5,
            "temperature": 0.7,
            "return_full_text": False
        }
    }
    
    print(f"\nTesting without authentication")
    print(f"Model: {model}")
    print(f"API URL: {api_url}")
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        status_code = response.status_code
        
        print(f"Response status code: {status_code}")
        
        if status_code == 200:
            result = response.json()
            print("✅ Model works without authentication!")
            print(f"Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"❌ Authentication required for this model")
            print(f"Response text: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test Hugging Face API directly")
    parser.add_argument("--api-key", help="Hugging Face API key")
    parser.add_argument("--model", default="gpt2", help="Model to test (default: gpt2)")
    parser.add_argument("--test-no-auth", action="store_true", help="Also test without authentication")
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.api_key or os.environ.get("HUGGINGFACE_API_KEY")
    
    if not api_key:
        print("No API key provided. Use --api-key or set HUGGINGFACE_API_KEY environment variable.")
        if args.test_no_auth:
            print("Testing without authentication only...")
            test_no_auth(args.model)
        else:
            sys.exit(1)
    else:
        # Test with API key
        success = test_api_key_direct(api_key, args.model)
        
        # Test without authentication if requested
        if args.test_no_auth:
            test_no_auth(args.model)
            
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 