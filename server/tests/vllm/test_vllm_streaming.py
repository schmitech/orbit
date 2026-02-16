#!/usr/bin/env python
"""Test vLLM provider with streaming"""

import asyncio
import sys
import os

# Add server directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from inference.pipeline.providers.vllm_provider import VLLMProvider

async def test_streaming():
    """Test vLLM provider with streaming enabled"""
    print("\n=== Testing vLLM Provider with Streaming ===")
    
    config = {
        "inference": {
            "vllm": {
                "host": "3.96.55.208",
                "port": 8000,
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "temperature": 0.7,
                "max_tokens": 100,
                "stream": True  # Force streaming
            }
        },
        "general": {
        }
    }
    
    provider = VLLMProvider(config)
    
    try:
        # Initialize
        await provider.initialize()
        
        # Test streaming generation
        prompt = "You are a helpful assistant.\n\nUser: Hello, how are you?\n\nAssistant:"
        print(f"Prompt: {prompt}")
        print("\nStreaming response:")
        print("-" * 40)
        
        full_response = []
        async for chunk in provider.generate_stream(prompt):
            print(chunk, end='', flush=True)
            full_response.append(chunk)
        
        print("\n" + "-" * 40)
        print(f"\nFull response: {''.join(full_response)}")
        
        # Close provider
        await provider.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def test_non_streaming():
    """Test vLLM provider with streaming disabled"""
    print("\n=== Testing vLLM Provider without Streaming ===")
    
    config = {
        "inference": {
            "vllm": {
                "host": "3.96.55.208",
                "port": 8000,
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "temperature": 0.7,
                "max_tokens": 100,
                "stream": False  # Force non-streaming
            }
        },
        "general": {
        }
    }
    
    provider = VLLMProvider(config)
    
    try:
        # Initialize
        await provider.initialize()
        
        # Test non-streaming generation
        prompt = "You are a helpful assistant.\n\nUser: Hello, how are you?\n\nAssistant:"
        print(f"Prompt: {prompt}")
        print("\nNon-streaming response:")
        print("-" * 40)
        
        response = await provider.generate(prompt)
        print(response)
        
        print("-" * 40)
        
        # Close provider
        await provider.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run all tests"""
    await test_non_streaming()
    await test_streaming()

if __name__ == "__main__":
    asyncio.run(main())