"""
Prompt Guardrail Testing Framework

This script provides a framework for testing the prompt guardrail system that determines
whether queries are safe to process. It can run both individual queries and batch tests
from a JSON file containing predefined test cases.

Usage:
    python3 test_prompt_guardrails.py [options]

Options:
    --test-file TEXT    Path to JSON file containing test cases (default: test_cases.json)
    --single-query TEXT Run a single query test

Example:
    # Run all test cases from default test file
    python3 test_prompt_guardrails.py --test-file test_cases.json

    # Test a single query
    python3 test_prompt_guardrails.py --single-query "Your test query here"

Test Case JSON Format:
    {
        "test_cases": [
            {
                "name": "test_name",
                "query": "your test query here",
                "expected": "SAFE: true/false",
                "description": "Description of what this test is checking"
            }
        ]
    }
"""

import requests
import yaml
import json
import sys
import argparse
from datetime import datetime

def load_config():
    """
    Load configuration from the server's config.yaml file.
    
    Returns:
        dict: Configuration dictionary containing Ollama settings and guardrail prompt.
    
    Raises:
        FileNotFoundError: If config.yaml is not found
        yaml.YAMLError: If config.yaml is not valid YAML
    """
    with open('../server/config.yaml', 'r') as file:
        return yaml.safe_load(file)

def run_single_test(query, ollama_config, guardrail_prompt):
    """
    Run a single query through the guardrail system using Ollama.
    
    Args:
        query (str): The query to test
        ollama_config (dict): Ollama configuration settings
        guardrail_prompt (str): The guardrail prompt to use for evaluation
    
    Returns:
        str: The guardrail response ("SAFE: true" or "SAFE: false")
    
    Raises:
        requests.RequestException: If the Ollama API request fails
    """
    payload = {
        "model": ollama_config["model"],
        "prompt": f"{guardrail_prompt}\n\nQuery: {query}\n\nRespond with ONLY 'SAFE: true' or 'SAFE: false':",
        "temperature": 0.0,  # Set to 0 for deterministic response
        "top_p": 1.0,
        "top_k": 1,
        "repeat_penalty": ollama_config["repeat_penalty"],
        "num_predict": 20,  # Limit response length
        "stream": False
    }

    try:
        response = requests.post(f"{ollama_config['base_url']}/api/generate", json=payload)
        response_data = response.json()
        return response_data.get("response", "").strip()
    except Exception as e:
        return f"ERROR: {str(e)}"

def run_test_cases(test_file):
    """
    Run all test cases from a JSON file and generate a test report.
    
    Args:
        test_file (str): Path to the JSON file containing test cases
    
    The function will:
    1. Load the configuration and test cases
    2. Run each test case through the guardrail system
    3. Compare results with expected outcomes
    4. Generate a detailed test report with pass/fail statistics
    """
    config = load_config()
    ollama_config = config['ollama']
    guardrail_prompt = config['system']['guardrail_prompt']

    with open(test_file, 'r') as f:
        test_data = json.load(f)

    print(f"\n=== Starting Guardrail Tests at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    total_tests = len(test_data['test_cases'])
    passed_tests = 0
    failed_tests = 0

    for test_case in test_data['test_cases']:
        print(f"\nTest: {test_case['name']}")
        print(f"Description: {test_case['description']}")
        print(f"Query: {test_case['query']}")
        print(f"Expected: {test_case['expected']}")
        
        result = run_single_test(test_case['query'], ollama_config, guardrail_prompt)
        print(f"Actual: {result}")
        
        if result == test_case['expected']:
            print("✅ PASSED")
            passed_tests += 1
        else:
            print("❌ FAILED")
            failed_tests += 1
            print(f"Expected: {test_case['expected']}")
            print(f"Got: {result}")
        
        print("-" * 80)

    print(f"\n=== Test Summary ===")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.2f}%")

def main():
    """
    Main entry point for the script.
    
    Parses command line arguments and runs either a single query test
    or a batch of test cases from a JSON file.
    """
    parser = argparse.ArgumentParser(description='Test prompt guardrails with various test cases')
    parser.add_argument('--test-file', default='test_cases.json',
                      help='Path to JSON file containing test cases')
    parser.add_argument('--single-query', help='Run a single query test')
    
    args = parser.parse_args()
    
    if args.single_query:
        config = load_config()
        result = run_single_test(args.single_query, config['ollama'], config['system']['guardrail_prompt'])
        print(f"\nQuery: {args.single_query}")
        print(f"Result: {result}")
    else:
        run_test_cases(args.test_file)

if __name__ == "__main__":
    main()