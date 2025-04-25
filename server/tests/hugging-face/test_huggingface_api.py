#!/usr/bin/env python3
"""
Simple script to test Hugging Face API connectivity.
This script verifies if your API key works with Hugging Face's inference API.
"""

import os
import sys
import argparse
from hugging_py_face import NLP
from hugging_py_face.exceptions import APICallException

def test_api_key(api_key, model="gpt2", verbose=False):
    """Test if the provided API key works with Hugging Face."""
    print(f"Testing Hugging Face API key (last 4 chars: {'*' * 16 + api_key[-4:] if len(api_key) >= 4 else 'N/A'})")
    print(f"API key length: {len(api_key)} characters")
    
    try:
        # Initialize the NLP client
        print("Initializing NLP client...")
        client = NLP(api_token=api_key)
        
        # Test text generation
        print(f"Testing text generation with model: {model}")
        response = client.text_generation(
            text="Hello, this is a test.",
            parameters={
                "max_new_tokens": 5,
                "temperature": 0.7,
                "top_p": 0.9,
                "return_full_text": False
            },
            model=model
        )
        
        # Print the response
        if verbose:
            print(f"Full response: {response}")
        
        # Extract the generated text
        if isinstance(response, dict) and "generated_text" in response:
            generated_text = response["generated_text"]
        elif isinstance(response, list) and len(response) > 0 and "generated_text" in response[0]:
            generated_text = response[0]["generated_text"]
        else:
            generated_text = str(response)
        
        print(f"Generated text: {generated_text}")
        print("✅ API key is working properly!")
        return True
        
    except APICallException as e:
        print(f"❌ API call failed: {str(e)}")
        if "403" in str(e):
            print("Authentication error. Your API key might be invalid or expired.")
            print("Get a new token at: https://huggingface.co/settings/tokens")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test Hugging Face API connectivity")
    parser.add_argument("--api-key", help="Hugging Face API key")
    parser.add_argument("--model", default="gpt2", help="Model to test (default: gpt2)")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.api_key or os.environ.get("HUGGINGFACE_API_KEY")
    
    if not api_key:
        print("No API key provided. Use --api-key or set HUGGINGFACE_API_KEY environment variable.")
        sys.exit(1)
    
    success = test_api_key(api_key, args.model, args.verbose)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 