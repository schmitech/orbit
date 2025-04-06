#!/usr/bin/env python3
"""
Test script for the logger service
"""

import os
import asyncio
import sys

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config_manager import load_config
from services import LoggerService


async def main():
    """
    Test the logger service
    """
    print("Testing logger service...")
    
    # Load configuration
    config = load_config()
    config['general']['verbose'] = 'true'  # Enable verbose mode for testing
    
    # Create logger service
    logger_service = LoggerService(config)
    
    # Initialize Elasticsearch (if configured)
    await logger_service.initialize_elasticsearch()
    
    # Test log entry
    test_query = "What is the capital of France?"
    test_response = "The capital of France is Paris."
    test_ip = "192.168.1.100"
    
    print(f"Logging test message with IP: {test_ip}")
    await logger_service.log_conversation(
        query=test_query,
        response=test_response,
        ip=test_ip,
        backend="ollama-test",
        blocked=False
    )
    
    # Test with localhost IP
    localhost_ip = "127.0.0.1"
    print(f"Logging test message with localhost IP: {localhost_ip}")
    await logger_service.log_conversation(
        query="Local test query",
        response="Local test response",
        ip=localhost_ip,
        backend="ollama-test",
        blocked=False
    )
    
    # Test with blocked query
    print("Logging test blocked query")
    await logger_service.log_conversation(
        query="This is a blocked query",
        response="I cannot assist with that request",
        ip="203.0.113.1",  # Example external IP
        backend="ollama-test",
        blocked=True
    )
    
    # Close connections
    await logger_service.close()
    
    print("Test completed. Check the logs directory for the log file.")
    print("If Elasticsearch is configured, check the index for logged data.")


if __name__ == "__main__":
    asyncio.run(main())