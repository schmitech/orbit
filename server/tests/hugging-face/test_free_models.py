#!/usr/bin/env python3
"""
Script to test which Hugging Face models work without an API key.
This is useful for finding fallback models for the application.
"""

import sys
from hugging_py_face import NLP
from hugging_py_face.exceptions import APICallException

# List of models to test
TEST_MODELS = [
    "gpt2",
    "gpt2-medium",
    "distilgpt2",
    "facebook/opt-125m",
    "EleutherAI/gpt-neo-125m",
    "bigscience/bloom-560m",
    "bert-base-uncased",
    "distilbert-base-uncased",
    "google/t5-small",
    "google/flan-t5-small",
    "roberta-base",
]

def test_model_without_key(model):
    """Test if a model can be used without an API key."""
    print(f"Testing model: {model}")
    
    try:
        # Initialize the NLP client with empty API token
        client = NLP(api_token="")
        
        # Test text generation
        response = client.text_generation(
            text="Hello, this is a test.",
            parameters={
                "max_new_tokens": 5,
                "temperature": 0.7,
                "return_full_text": False
            },
            model=model
        )
        
        # Extract the generated text
        if isinstance(response, dict) and "generated_text" in response:
            generated_text = response["generated_text"]
        elif isinstance(response, list) and len(response) > 0 and "generated_text" in response[0]:
            generated_text = response[0]["generated_text"]
        else:
            generated_text = str(response)
        
        print(f"  ✅ Success! Generated text: {generated_text}")
        return True
        
    except APICallException as e:
        error_msg = str(e)
        if "403" in error_msg:
            print(f"  ❌ Authentication required: {error_msg}")
        else:
            print(f"  ❌ API call failed: {error_msg}")
        return False
        
    except Exception as e:
        print(f"  ❌ Unexpected error: {str(e)}")
        return False

def main():
    """Main function to test multiple models."""
    print("Testing which Hugging Face models work without an API key...\n")
    
    working_models = []
    failed_models = []
    
    for model in TEST_MODELS:
        success = test_model_without_key(model)
        if success:
            working_models.append(model)
        else:
            failed_models.append(model)
        print()  # Add line break between model tests
    
    # Print summary
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    print(f"\n✅ Working models ({len(working_models)}):")
    for model in working_models:
        print(f"  - {model}")
    
    print(f"\n❌ Models requiring authentication ({len(failed_models)}):")
    for model in failed_models:
        print(f"  - {model}")
    
    print("\nYou can use any of the working models as fallback options in your application.")

if __name__ == "__main__":
    main() 