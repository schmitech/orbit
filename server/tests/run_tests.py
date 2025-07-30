#!/usr/bin/env python
"""
Test runner script for all server tests
"""

import pytest
import os
import sys
import glob
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

# Log MongoDB configuration values
logger.info("MongoDB Configuration in run_tests.py:")
logger.info(f"Host: {os.getenv('INTERNAL_SERVICES_MONGODB_HOST')}")
logger.info(f"Port: {os.getenv('INTERNAL_SERVICES_MONGODB_PORT')}")
logger.info(f"Database: {os.getenv('INTERNAL_SERVICES_MONGODB_DATABASE')}")
logger.info(f"Username: {os.getenv('INTERNAL_SERVICES_MONGODB_USERNAME')}")
logger.info(f"Password: {'*' * len(os.getenv('INTERNAL_SERVICES_MONGODB_PASSWORD', '')) if os.getenv('INTERNAL_SERVICES_MONGODB_PASSWORD') else 'None'}")

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

def main():
    """Run all tests in the tests directory"""
    # Get the directory containing this script
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Find all test files (excluding __pycache__ and .pyc files)
    test_files = glob.glob(os.path.join(test_dir, "test_*.py"))
    
    # Filter out any non-test files and sort for consistent order
    test_files = [f for f in test_files if os.path.isfile(f)]
    test_files.sort()
    
    print(f"Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"  - {os.path.basename(test_file)}")
    
    # Run the tests with verbose output and stop on first failure
    # Combine all exclusions into a single -k expression
    pytest.main([
        str(SCRIPT_DIR),
        "-v",
        "--asyncio-mode=auto",
        "-k", "not test_ollama and not vllm",
        "--ignore=tests/vllm/"
    ])

if __name__ == "__main__":
    main()