#!/usr/bin/env python3
"""
Live test for Qdrant Cloud connection.

This script tests if Qdrant Cloud is properly configured and accessible.

NOTE: This test requires valid Qdrant Cloud credentials in .env file.
Run this test manually: python test_qdrant_cloud.py
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent.parent
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Configuration
QDRANT_URL = os.getenv("DATASOURCE_QDRANT_URL")
QDRANT_HOST = os.getenv("DATASOURCE_QDRANT_HOST")
QDRANT_PORT = os.getenv("DATASOURCE_QDRANT_PORT", "6333")
QDRANT_API_KEY = os.getenv("DATASOURCE_QDRANT_API_KEY")


def test_qdrant_connection():
    """Test the Qdrant connection (cloud or self-hosted)."""

    print("=" * 60)
    print("Qdrant Connection Test")
    print("=" * 60)

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("ERROR: qdrant-client not installed.")
        print("Install with: pip install qdrant-client")
        return False

    # Determine connection mode
    if QDRANT_URL:
        print(f"\nMode: Qdrant Cloud")
        print(f"URL: {QDRANT_URL}")
        print(f"API Key: {'*' * 10}..." if QDRANT_API_KEY else "Not set")

        try:
            client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
            )
        except Exception as e:
            print(f"\nERROR: Failed to create client: {e}")
            return False
    else:
        print(f"\nMode: Self-hosted")
        print(f"Host: {QDRANT_HOST or 'localhost'}")
        print(f"Port: {QDRANT_PORT}")

        try:
            port = int(QDRANT_PORT) if QDRANT_PORT else 6333
            client = QdrantClient(
                host=QDRANT_HOST or 'localhost',
                port=port,
                api_key=QDRANT_API_KEY if QDRANT_API_KEY else None,
            )
        except Exception as e:
            print(f"\nERROR: Failed to create client: {e}")
            return False

    # Test connection
    print("\n=== Testing connection ===")
    try:
        collections = client.get_collections()
        print(f"✓ Connected successfully!")
        print(f"\nExisting collections ({len(collections.collections)}):")
        for col in collections.collections:
            print(f"  - {col.name}")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

    # Test creating a collection
    test_collection = "orbit_test_collection"
    print(f"\n=== Testing collection operations ===")

    try:
        from qdrant_client.models import Distance, VectorParams

        # Create test collection
        print(f"Creating test collection: {test_collection}")
        client.recreate_collection(
            collection_name=test_collection,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        print(f"✓ Collection created")

        # Add a test vector
        print("Adding test vector...")
        from qdrant_client.models import PointStruct
        import random

        test_vector = [random.random() for _ in range(384)]
        client.upsert(
            collection_name=test_collection,
            points=[
                PointStruct(
                    id=1,
                    vector=test_vector,
                    payload={"test": "data", "source": "orbit_test"}
                )
            ]
        )
        print(f"✓ Vector added")

        # Search for similar vectors
        print("Searching for similar vectors...")
        results = client.query_points(
            collection_name=test_collection,
            query=test_vector,
            limit=1,
            with_payload=True
        )

        if hasattr(results, 'points'):
            results = results.points

        if results:
            print(f"✓ Search successful, found {len(results)} result(s)")
            print(f"  Score: {results[0].score}")
            print(f"  Payload: {results[0].payload}")
        else:
            print("✗ No results found")

        # Cleanup - delete test collection
        print(f"\nCleaning up test collection...")
        client.delete_collection(collection_name=test_collection)
        print(f"✓ Test collection deleted")

    except Exception as e:
        print(f"✗ Collection operations failed: {e}")
        import traceback
        traceback.print_exc()

        # Try to cleanup anyway
        try:
            client.delete_collection(collection_name=test_collection)
        except:
            pass
        return False

    print("\n" + "=" * 60)
    print("✓ All Qdrant tests passed!")
    print("=" * 60)
    return True


def main():
    """Run the Qdrant test."""

    # Check for required environment variables
    if not QDRANT_URL and not QDRANT_HOST:
        print("WARNING: Neither DATASOURCE_QDRANT_URL nor DATASOURCE_QDRANT_HOST is set.")
        print("Will attempt to connect to localhost:6333")

    success = test_qdrant_connection()

    if not success:
        print("\nTroubleshooting steps:")
        print("  1. For Qdrant Cloud:")
        print("     - Set DATASOURCE_QDRANT_URL (e.g., https://xxx.cloud.qdrant.io:6333)")
        print("     - Set DATASOURCE_QDRANT_API_KEY")
        print("  2. For self-hosted:")
        print("     - Ensure Qdrant is running on the specified host:port")
        print("     - Leave DATASOURCE_QDRANT_URL empty")
        print("  3. Check .env file for correct credentials")
        sys.exit(1)


if __name__ == "__main__":
    main()
