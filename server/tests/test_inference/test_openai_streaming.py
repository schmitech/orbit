#!/usr/bin/env python3
"""
Test script to diagnose OpenAI streaming performance.
"""
import asyncio
import time
import os
import sys
import httpx
import pytest
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"Warning: .env file not found at {env_path}")

@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    return api_key


@pytest.mark.asyncio
async def test_default_client(openai_api_key):
    """Test with default OpenAI client."""
    print("\n=== Testing with DEFAULT OpenAI client ===")
    client = AsyncOpenAI(api_key=openai_api_key)

    start = time.time()
    first_chunk_time = None

    stream = await client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say hello"}],
        stream=True,
        max_completion_tokens=50
    )

    async for chunk in stream:
        if first_chunk_time is None:
            first_chunk_time = time.time()
            print(f"Time to first chunk: {first_chunk_time - start:.2f}s")
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

    print(f"\nTotal time: {time.time() - start:.2f}s\n")
    await client.close()

@pytest.mark.asyncio
async def test_custom_client(openai_api_key):
    """Test with custom httpx client."""
    print("\n=== Testing with CUSTOM httpx client ===")

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0,
            read=None,
            write=10.0,
            pool=2.0
        ),
        limits=httpx.Limits(
            max_keepalive_connections=10,
            max_connections=50,
            keepalive_expiry=5.0
        ),
        http2=False,
        follow_redirects=True
    )

    client = AsyncOpenAI(
        api_key=openai_api_key,
        http_client=http_client
    )

    start = time.time()
    first_chunk_time = None

    stream = await client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say hello"}],
        stream=True,
        max_completion_tokens=50
    )

    async for chunk in stream:
        if first_chunk_time is None:
            first_chunk_time = time.time()
            print(f"Time to first chunk: {first_chunk_time - start:.2f}s")
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

    print(f"\nTotal time: {time.time() - start:.2f}s\n")
    await client.close()

@pytest.mark.asyncio
async def test_minimal_client(openai_api_key):
    """Test with minimal httpx settings."""
    print("\n=== Testing with MINIMAL httpx client (no timeouts) ===")

    http_client = httpx.AsyncClient(
        timeout=None,  # No timeouts at all
        http2=False
    )

    client = AsyncOpenAI(
        api_key=openai_api_key,
        http_client=http_client
    )

    start = time.time()
    first_chunk_time = None

    stream = await client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say hello"}],
        stream=True,
        max_completion_tokens=50
    )

    async for chunk in stream:
        if first_chunk_time is None:
            first_chunk_time = time.time()
            print(f"Time to first chunk: {first_chunk_time - start:.2f}s")
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

    print(f"\nTotal time: {time.time() - start:.2f}s\n")
    await client.close()

