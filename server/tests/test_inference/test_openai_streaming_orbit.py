#!/usr/bin/env python3
"""
Test OpenAI streaming through ORBIT's infrastructure to diagnose buffering.
"""
import asyncio
import time
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

# Load environment
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)

async def test_orbit_streaming():
    """Test streaming through ORBIT's OpenAI service"""
    print("\n=== Testing OpenAI streaming through ORBIT infrastructure ===\n")

    # Import ORBIT components
    from ai_services.implementations.inference.openai_inference_service import OpenAIInferenceService

    # Create config
    config = {
        'openai': {
            'enabled': True,
            'api_key': os.environ.get('OPENAI_API_KEY'),
            'model': 'gpt-5',
            'temperature': 0.1,
            'max_tokens': 50,
            'stream': True
        }
    }

    # Initialize service
    service = OpenAIInferenceService(config)
    await service.initialize()

    # Test streaming
    print("Starting streaming test...")
    start_time = time.time()
    first_chunk_time = None
    chunk_count = 0

    try:
        async for chunk in service.generate_stream("Say hello", messages=[{"role": "user", "content": "Say hello"}]):
            if first_chunk_time is None:
                first_chunk_time = time.time()
                ttft = first_chunk_time - start_time
                print(f"\n⏱️  Time to first chunk: {ttft:.3f}s")
                print(f"\nStreaming response: ", end="", flush=True)

            print(chunk, end="", flush=True)
            chunk_count += 1

        total_time = time.time() - start_time
        streaming_time = total_time - (first_chunk_time - start_time if first_chunk_time else 0)

        print(f"\n\n✅ Streaming completed")
        print(f"   Total time: {total_time:.3f}s")
        print(f"   Time to first chunk: {(first_chunk_time - start_time) if first_chunk_time else 0:.3f}s")
        print(f"   Streaming time: {streaming_time:.3f}s")
        print(f"   Total chunks: {chunk_count}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_orbit_streaming())
