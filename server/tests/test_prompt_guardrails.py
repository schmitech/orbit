"""
Prompt Guardrail Testing Framework

This script provides a framework for testing the prompt guardrail system that determines
whether queries are safe to process. It directly tests the GuardrailService in the Orbit server.

Usage:
    python3 test_prompt_guardrails.py [options]

Options:
    --test-file TEXT       Path to JSON file containing test cases (default: test_cases.json)
    --single-query TEXT    Run a single query test
    --delay FLOAT          Delay in seconds between test calls (default: 0.5)

Example:
    # Run all test cases from default test file
    python3 test_prompt_guardrails.py --test-file test_cases.json

    # Test a single query
    python3 test_prompt_guardrails.py --single-query "Your test query here"
    
    # Run tests with a 2-second delay between calls
    python3 test_prompt_guardrails.py --test-file test_cases.json --delay 2.0

Test Case JSON Format:
    {
        "test_cases": [
            {
                "name": "test_name",
                "query": "your test query here",
                "expected": true/false,   # Expected safety result (true = safe, false = unsafe)
                "description": "Description of what this test is checking"
            }
        ]
    }
"""

import asyncio
import json
import argparse
from datetime import datetime
import sys
import os
import yaml
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

# Load environment variables from .env file in the parent directory
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(server_dir, '.env')
if os.path.exists(env_path):
    print(f"Loading environment variables from {env_path}")
    load_dotenv(env_path)
else:
    print(f"No .env file found at {env_path}")

# Add the parent directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the necessary modules from the server
from services.guardrail_service import GuardrailService
from moderators.base import ModeratorFactory
from config.config_manager import load_config as load_server_config

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    """
    Load configuration from the server's config.yaml file.
    
    Returns:
        dict: Configuration dictionary
    """
    # Try to use the server's config loading function
    try:
        return load_server_config()
    except:
        # Fall back to manual loading if that fails
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(server_dir, 'config.yaml')
        
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

async def test_query(query: str, guardrail_service: GuardrailService) -> Tuple[bool, Optional[str]]:
    """
    Test a query with the GuardrailService.
    
    Args:
        query: The query to test
        guardrail_service: Initialized GuardrailService instance
        
    Returns:
        Tuple of (is_safe, message)
    """
    return await guardrail_service.check_safety(query)

async def run_single_test(query: str, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Run a single query test using the GuardrailService.
    
    Args:
        query: The query to test
        config: Server configuration
        
    Returns:
        Tuple of (is_safe, message)
    """
    # Create guardrail service
    guardrail_service = GuardrailService(config)
    
    try:
        # Initialize the service
        await guardrail_service.initialize()
        
        # Test the query
        is_safe, message = await test_query(query, guardrail_service)
        
        return is_safe, message
    finally:
        # Clean up resources
        if guardrail_service:
            await guardrail_service.close()

def parse_expected_value(expected):
    """
    Parse the expected value which might be a boolean or a string "SAFE: true"/"SAFE: false".
    
    Args:
        expected: The expected value from the test case
        
    Returns:
        bool: True if safe, False if unsafe
    """
    if isinstance(expected, bool):
        return expected
    elif isinstance(expected, str) and expected.startswith("SAFE:"):
        return "true" in expected.lower()
    else:
        # Default to safe if unknown format
        return True

async def run_test_cases(test_file: str, config: Dict[str, Any], delay: float = 0.5):
    """
    Run all test cases from a JSON file.
    
    Args:
        test_file: Path to the JSON test file
        config: Server configuration
        delay: Delay in seconds between test calls to avoid rate limits
    """
    try:
        with open(test_file, 'r') as f:
            test_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Test file not found: {test_file}")
        return
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in test file: {test_file}")
        return
    
    if 'test_cases' not in test_data:
        print(f"❌ No test_cases found in {test_file}")
        return
    
    # Create guardrail service
    guardrail_service = GuardrailService(config)
    
    try:
        # Initialize the service
        await guardrail_service.initialize()
        
        print(f"\n=== Starting Guardrail Tests at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        
        # Get safety configuration for display
        safety_config = config.get('safety', {})
        moderator = safety_config.get('moderator', 'None')
        mode = safety_config.get('mode', 'strict')
        
        print(f"Using moderator: {moderator}")
        print(f"Safety mode: {mode}")
        print(f"Rate limiting: {delay} seconds between API calls")
        
        total_tests = len(test_data['test_cases'])
        passed_tests = 0
        failed_tests = 0

        for i, test_case in enumerate(test_data['test_cases']):
            name = test_case.get('name', 'Unnamed test')
            query = test_case.get('query', '')
            expected_raw = test_case.get('expected', True)  # Default to expecting safe
            expected = parse_expected_value(expected_raw)
            description = test_case.get('description', 'No description')
            
            # Show test progress
            print(f"\nTest {i+1}/{total_tests}: {name}")
            print(f"Description: {description}")
            print(f"Query: {query}")
            print(f"Expected: {'safe' if expected else 'unsafe'}")
            
            # Run the test
            is_safe, message = await test_query(query, guardrail_service)
            
            print(f"Result: {'safe' if is_safe else 'unsafe'}")
            if message:
                print(f"Message: {message}")
            
            # Check if the result matches expectations
            if is_safe == expected:
                print("✅ PASSED")
                passed_tests += 1
            else:
                print("❌ FAILED")
                failed_tests += 1
            
            print("-" * 80)
            
            # Add delay between tests to avoid rate limiting, if not the last test
            if i < total_tests - 1:
                print(f"Waiting {delay} seconds before next test...")
                await asyncio.sleep(delay)

        print(f"\n=== Test Summary ===")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.2f}%")
    
    finally:
        # Clean up resources
        if guardrail_service:
            await guardrail_service.close()

async def main_async():
    """
    Async main function that parses arguments and runs tests.
    """
    parser = argparse.ArgumentParser(description='Test prompt guardrails with various test cases')
    parser.add_argument('--test-file', default='test_cases.json',
                      help='Path to JSON file containing test cases')
    parser.add_argument('--single-query', help='Run a single query test')
    parser.add_argument('--delay', type=float, default=0.5,
                      help='Delay in seconds between test calls (default: 0.5)')
    
    args = parser.parse_args()
    
    # Load the configuration
    config = load_config()
    
    if args.single_query:
        # Run a single test
        is_safe, message = await run_single_test(args.single_query, config)
        
        print(f"\nQuery: {args.single_query}")
        print(f"Result: {'safe' if is_safe else 'unsafe'}")
        if message:
            print(f"Message: {message}")
    else:
        # Run all tests from the test file
        await run_test_cases(args.test_file, config, args.delay)

def main():
    """
    Main entry point that runs the async main function.
    """
    asyncio.run(main_async())

if __name__ == "__main__":
    main()