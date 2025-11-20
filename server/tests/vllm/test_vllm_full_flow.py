#!/usr/bin/env python
"""Test vLLM provider in full application flow"""

import asyncio
import json
import sys
import os
import logging

# Add server directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(level=logging.DEBUG)

from inference.pipeline_factory import PipelineFactory
from services.pipeline_chat_service import PipelineChatService

async def test_full_flow():
    """Test vLLM provider through the full application flow"""
    print("\n=== Testing vLLM Provider in Full Application Flow ===")
    
    config = {
        "general": {
            "inference_provider": "vllm"
        },
        "inference": {
            "vllm": {
                "host": "3.96.55.208",
                "port": 8000,
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "temperature": 0.7,
                "max_tokens": 100,
                "stream": True
            }
        },
        "language_detection": {
            "enabled": False
        },
        "safety": {
            "enabled": False
        }
    }
    
    # Create chat service (it creates its own pipeline factory internally)
    chat_service = PipelineChatService(
        config=config,
        logger_service=None,
        chat_history_service=None,
        llm_guard_service=None,
        moderator_service=None,
        retriever=None,
        reranker_service=None,
        prompt_service=None
    )
    
    # Initialize chat service
    await chat_service.initialize()
    
    # Test non-streaming
    print("\n--- Testing Non-Streaming ---")
    result = await chat_service.process_chat(
        message="Hello, how are you?",
        client_ip="127.0.0.1",
        adapter_name="default",
        session_id="test-session"
    )
    
    print(f"Non-streaming result: {json.dumps(result, indent=2)}")
    
    # Test streaming
    print("\n--- Testing Streaming ---")
    print("Streaming chunks:")
    chunks = []
    async for chunk in chat_service.process_chat_stream(
        message="Hello, how are you?",
        client_ip="127.0.0.1",
        adapter_name="default",
        session_id="test-session-2"
    ):
        print(f"  Chunk: {chunk}")
        chunks.append(chunk)
    
    print(f"\nTotal chunks received: {len(chunks)}")

if __name__ == "__main__":
    asyncio.run(test_full_flow())