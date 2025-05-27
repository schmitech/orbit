#!/usr/bin/env python3
"""
Test script for the logger service
"""

import os
import asyncio
import sys
import pytest
import pytest_asyncio

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config_manager import load_config
from services.logger_service import LoggerService


@pytest_asyncio.fixture
async def logger_service():
    """Fixture to create and initialize a logger service for testing."""
    config = load_config()
    config['general']['verbose'] = 'true'  # Enable verbose mode for testing
    
    service = LoggerService(config)
    await service.initialize_elasticsearch()
    
    try:
        yield service
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_log_conversation(logger_service):
    """Test logging a conversation."""
    test_query = "What is the capital of France?"
    test_response = "The capital of France is Paris."
    test_ip = "192.168.1.100"
    
    await logger_service.log_conversation(
        query=test_query,
        response=test_response,
        ip=test_ip,
        backend="ollama-test",
        blocked=False
    )


@pytest.mark.asyncio
async def test_log_localhost(logger_service):
    """Test logging with localhost IP."""
    localhost_ip = "127.0.0.1"
    await logger_service.log_conversation(
        query="Local test query",
        response="Local test response",
        ip=localhost_ip,
        backend="ollama-test",
        blocked=False
    )


@pytest.mark.asyncio
async def test_log_blocked(logger_service):
    """Test logging a blocked query."""
    await logger_service.log_conversation(
        query="This is a blocked query",
        response="I cannot assist with that request",
        ip="203.0.113.1",  # Example external IP
        backend="ollama-test",
        blocked=True
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])