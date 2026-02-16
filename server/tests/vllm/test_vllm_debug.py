#!/usr/bin/env python
"""Debug script for vLLM provider"""

import asyncio
import aiohttp
import json
import logging
from inference.pipeline.providers.vllm_provider import VLLMProvider

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_direct_api():
    """Test direct API call (mimicking the curl command)"""
    print("\n=== Testing Direct API Call ===")
    
    url = "http://3.96.55.208:8000/v1/chat/completions"
    payload = {
        "model": "Qwen/Qwen2.5-1.5B-Instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "temperature": 0.7,
        "max_tokens": 100
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as response:
                print(f"Status: {response.status}")
                data = await response.json()
                print(f"Response: {json.dumps(data, indent=2)}")
                return data
        except Exception as e:
            print(f"Error: {e}")
            return None

async def test_provider():
    """Test the VLLMProvider"""
    print("\n=== Testing VLLMProvider ===")
    
    config = {
        "inference": {
            "vllm": {
                "host": "3.96.55.208",
                "port": 8000,
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "temperature": 0.7,
                "max_tokens": 100,
                "stream": False
            }
        },
        "general": {
        }
    }
    
    provider = VLLMProvider(config)
    
    try:
        # Test validation
        print("Validating config...")
        is_valid = await provider.validate_config()
        print(f"Config valid: {is_valid}")
        
        # Initialize
        print("Initializing provider...")
        await provider.initialize()
        
        # Test with simple prompt
        prompt = "You are a helpful assistant.\n\nUser: Hello, how are you?\n\nAssistant:"
        print(f"Testing generation with prompt: {prompt}")
        response = await provider.generate(prompt)
        print(f"Provider response: {response}")
        
        # Test with messages format
        messages_prompt = """You are a helpful assistant.

User: Hello, how are you?
Assistant:"""
        print(f"\nTesting with formatted prompt: {messages_prompt}")
        response2 = await provider.generate(messages_prompt)
        print(f"Provider response 2: {response2}")
        
        # Close provider
        await provider.close()
        
    except Exception as e:
        logger.exception(f"Provider test failed: {e}")

async def main():
    """Run all tests"""
    # Test direct API
    await test_direct_api()
    
    # Test provider
    await test_provider()

if __name__ == "__main__":
    asyncio.run(main())