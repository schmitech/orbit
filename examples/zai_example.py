#!/usr/bin/env python3
"""
Z.AI inference service example.

This example demonstrates how to use the Z.AI inference service
with the Orbit unified AI services architecture.
"""

import asyncio
import os
import sys
from typing import Dict, Any

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from ai_services.implementations.zai_inference_service import ZaiInferenceService
from ai_services.registry import register_all_services


async def main():
    """Main example function."""
    print("Z.AI Inference Service Example")
    print("=" * 40)
    
    # Register all services
    register_all_services()
    
    # Configuration for Z.AI service
    config = {
        "inference": {
            "zai": {
                "api_key": os.getenv("ZAI_API_KEY", "your-api-key-here"),
                "model": "glm-4.6",
                "temperature": 0.1,
                "top_p": 0.8,
                "max_tokens": 2000,
                "stream": True,
                "timeout": {
                    "connect": 10000,
                    "total": 120000
                },
                "retry": {
                    "enabled": True,
                    "max_retries": 3,
                    "initial_wait_ms": 1000,
                    "max_wait_ms": 30000,
                    "exponential_base": 2
                }
            }
        }
    }
    
    # Check if API key is provided
    if config["inference"]["zai"]["api_key"] == "your-api-key-here":
        print("Error: Please set the ZAI_API_KEY environment variable")
        print("Example: export ZAI_API_KEY=your-actual-api-key")
        return
    
    try:
        # Create the Z.AI inference service
        print("Creating Z.AI inference service...")
        service = ZaiInferenceService(config)
        
        # Initialize the service
        print("Initializing service...")
        if not await service.initialize():
            print("Failed to initialize Z.AI service")
            return
        
        print("✓ Service initialized successfully")
        print(f"Model: {service.model}")
        print(f"Temperature: {service.temperature}")
        print(f"Max tokens: {service.max_tokens}")
        print()
        
        # Example 1: Simple text generation
        print("Example 1: Simple text generation")
        print("-" * 30)
        prompt = "Hello! Please introduce yourself and tell me what you can do."
        print(f"Prompt: {prompt}")
        print("Response:")
        
        response = await service.generate(prompt)
        print(response)
        print()
        
        # Example 2: Conversation with messages format
        print("Example 2: Conversation with messages format")
        print("-" * 30)
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant that specializes in Python programming."},
            {"role": "user", "content": "Can you help me write a simple Python function to calculate the factorial of a number?"}
        ]
        
        print("Messages:")
        for msg in messages:
            print(f"  {msg['role']}: {msg['content']}")
        print("Response:")
        
        response = await service.generate("", messages=messages)
        print(response)
        print()
        
        # Example 3: Streaming response
        print("Example 3: Streaming response")
        print("-" * 30)
        prompt = "Write a short story about a robot learning to paint."
        print(f"Prompt: {prompt}")
        print("Streaming response:")
        
        async for chunk in service.generate_stream(prompt):
            print(chunk, end='', flush=True)
        print()
        print()
        
        # Example 4: Parameter customization
        print("Example 4: Custom parameters")
        print("-" * 30)
        prompt = "Explain quantum computing in simple terms."
        print(f"Prompt: {prompt}")
        print("Response (with custom temperature=0.7):")
        
        response = await service.generate(
            prompt,
            temperature=0.7,
            max_tokens=500
        )
        print(response)
        print()
        
        # Close the service
        await service.close()
        print("✓ Service closed successfully")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        print("\nMake sure you have:")
        print("1. Set the ZAI_API_KEY environment variable")
        print("2. Installed the zai-sdk package: pip install zai-sdk==0.0.4")
        print("3. Have a valid Z.AI API key")


if __name__ == "__main__":
    asyncio.run(main())
