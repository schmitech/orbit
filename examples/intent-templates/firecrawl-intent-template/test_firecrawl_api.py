#!/usr/bin/env python3
"""
Firecrawl API Test Script
Tests Firecrawl API using the official Python SDK
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any

# Load .env file from project root (two levels up)
try:
    from dotenv import load_dotenv
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    env_path = project_root / '.env'

    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded .env from: {env_path}")
    else:
        print(f"⚠️  .env file not found at: {env_path}")
        print("Will check environment variables...")
except ImportError:
    print("⚠️  python-dotenv not installed, checking environment variables only")

print("")

# Check if firecrawl is installed
try:
    from firecrawl import Firecrawl  # Correct class name
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False
    print("⚠️  firecrawl-py not installed")
    print("Install with: pip install firecrawl-py")
    print("")

# Color codes
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def print_colored(message: str, color: str = NC):
    """Print colored message."""
    print(f"{color}{message}{NC}")


def test_firecrawl_api():
    """Test Firecrawl API with multiple URLs."""

    print("=" * 60)
    print("Firecrawl API Test (Python SDK)")
    print("=" * 60)
    print("")

    # Check API key
    api_key = os.getenv('FIRECRAWL_API_KEY')
    if not api_key:
        print_colored("❌ FIRECRAWL_API_KEY not set", RED)
        print("")
        print("Add to .env file in project root:")
        print("  FIRECRAWL_API_KEY=your-api-key-here")
        print("")
        print("Or set environment variable:")
        print("  export FIRECRAWL_API_KEY='your-api-key-here'")
        sys.exit(1)

    print_colored("✓ API key found", GREEN)
    print("")

    if not FIRECRAWL_AVAILABLE:
        print_colored("❌ firecrawl-py package not available", RED)
        print("Install with: pip install firecrawl-py")
        sys.exit(1)

    # Initialize Firecrawl client
    try:
        app = Firecrawl(api_key=api_key)  # Correct class name
        print_colored("✓ Firecrawl client initialized", GREEN)
        print("")
    except Exception as e:
        print_colored(f"❌ Failed to initialize Firecrawl client: {e}", RED)
        sys.exit(1)

    # Test URLs
    test_cases = [
        {
            "name": "Example.com (smallest test)",
            "url": "https://example.com",
            "expected_content": "Example Domain"
        },
        {
            "name": "Python.org homepage",
            "url": "https://www.python.org/",
            "expected_content": "Python"
        },
        {
            "name": "HTTPBin HTML",
            "url": "https://httpbin.org/html",
            "expected_content": "Herman Melville"
        }
    ]

    results = []

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print(f"URL: {test['url']}")
        print("")

        try:
            # Scrape URL using the correct method name
            result = app.scrape(
                url=test['url'],
                formats=['markdown']
            )

            # Check result - Firecrawl returns a Document object (Pydantic model)
            if result:
                # Access as object attributes (not dictionary)
                markdown_content = getattr(result, 'markdown', None)

                if markdown_content:
                    print_colored(f"✓ Test {i} PASSED", GREEN)
                    print(f"Content length: {len(markdown_content)} characters")

                    # Show preview
                    lines = markdown_content.split('\n')
                    preview = '\n'.join(lines[:5])
                    print(f"\nContent preview:")
                    print("-" * 40)
                    print(preview)
                    print("-" * 40)
                    print("")

                    # Verify expected content
                    if test['expected_content'] in markdown_content:
                        print_colored(f"  ✓ Found expected content: '{test['expected_content']}'", GREEN)
                    else:
                        print_colored(f"  ⚠ Expected content '{test['expected_content']}' not found", YELLOW)

                    # Show metadata if available
                    if hasattr(result, 'metadata') and result.metadata:
                        metadata = result.metadata
                        if hasattr(metadata, 'title') and metadata.title:
                            print(f"  Title: {metadata.title}")
                        if hasattr(metadata, 'url') and metadata.url:
                            print(f"  URL: {metadata.url}")

                    results.append({
                        "test": test['name'],
                        "status": "PASSED",
                        "length": len(markdown_content)
                    })
                else:
                    print_colored(f"✗ Test {i} FAILED: No markdown content found", RED)
                    print(f"Response type: {type(result)}")
                    available_attrs = [a for a in dir(result) if not a.startswith('_')]
                    print(f"Available attributes: {available_attrs[:10]}")
                    results.append({
                        "test": test['name'],
                        "status": "FAILED",
                        "error": "No markdown content"
                    })
            else:
                print_colored(f"✗ Test {i} FAILED: No response received", RED)
                results.append({
                    "test": test['name'],
                    "status": "FAILED",
                    "error": "No response received"
                })

        except Exception as e:
            print_colored(f"✗ Test {i} FAILED with exception", RED)
            print(f"Error: {str(e)}")
            print("")
            results.append({
                "test": test['name'],
                "status": "FAILED",
                "error": str(e)
            })

        print("")

    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for r in results if r['status'] == 'PASSED')
    failed = sum(1 for r in results if r['status'] == 'FAILED')

    print(f"\nTotal: {len(results)} tests")
    print_colored(f"Passed: {passed}", GREEN if passed > 0 else NC)
    print_colored(f"Failed: {failed}", RED if failed > 0 else NC)
    print("")

    if failed == 0:
        print_colored("🎉 All tests passed! Firecrawl is working correctly.", GREEN)
        print("")
        print("Next steps:")
        print("1. Configure ORBIT with test templates")
        print("2. Follow steps in test_firecrawl_setup.md")
        print("3. Test with: orbit-chat")
        return 0
    else:
        print_colored("⚠️  Some tests failed. Check errors above.", YELLOW)
        print("")
        print("Troubleshooting:")
        print("1. Verify API key is valid")
        print("2. Check network connectivity")
        print("3. Try increasing timeout")
        print("4. Check Firecrawl account credits/status")
        return 1


if __name__ == "__main__":
    sys.exit(test_firecrawl_api())
