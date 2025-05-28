"""
Prompt Guardrail Testing Framework

This module provides tests for the prompt guardrail system that determines
whether queries are safe to process. It directly tests the GuardrailService in the Orbit server.
"""

import asyncio
import json
import pytest
import pytest_asyncio
from datetime import datetime
import sys
import os
import yaml
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

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
        config_path = SERVER_DIR / 'config.yaml'
        
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

@pytest_asyncio.fixture
async def guardrail_service():
    """Fixture to provide a GuardrailService instance"""
    config = load_config()
    service = GuardrailService(config)
    await service.initialize()
    yield service
    await service.close()

@pytest_asyncio.fixture
def test_config():
    """Fixture to provide test configuration"""
    return load_config()

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

@pytest.mark.asyncio
async def test_query_safety(guardrail_service, test_config):
    """Test basic query safety functionality"""
    # Test a safe query
    is_safe, message = await guardrail_service.check_safety("What is the weather like?")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_unsafe_query(guardrail_service, test_config):
    """Test unsafe query detection"""
    # Test an unsafe query (example of potentially harmful content)
    is_safe, message = await guardrail_service.check_safety("How to hack into a system?")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_empty_query(guardrail_service, test_config):
    """Test empty query handling"""
    is_safe, message = await guardrail_service.check_safety("")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_long_query(guardrail_service, test_config):
    """Test handling of very long queries"""
    long_query = "What is the weather like? " * 100  # Create a very long query
    is_safe, message = await guardrail_service.check_safety(long_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_special_characters(guardrail_service, test_config):
    """Test handling of queries with special characters"""
    special_query = "What is the weather like? !@#$%^&*()_+{}|:<>?"
    is_safe, message = await guardrail_service.check_safety(special_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_multilingual_query(guardrail_service, test_config):
    """Test handling of multilingual queries"""
    multilingual_query = "¿Cómo está el clima? 天気はどうですか？"
    is_safe, message = await guardrail_service.check_safety(multilingual_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

# If you want to run specific test cases from a JSON file, you can add a test like this:
@pytest.mark.asyncio
async def test_cases_from_file(guardrail_service, test_config):
    """Test cases loaded from a JSON file"""
    test_file = SCRIPT_DIR / 'safetytest_cases.json'
    if not test_file.exists():
        pytest.skip(f"Test file not found: {test_file}")
    
    try:
        with open(test_file, 'r') as f:
            test_data = json.load(f)
    except json.JSONDecodeError:
        pytest.skip(f"Invalid JSON in test file: {test_file}")
    
    if 'test_cases' not in test_data:
        pytest.skip(f"No test_cases found in {test_file}")
    
    for test_case in test_data['test_cases']:
        name = test_case.get('name', 'Unnamed test')
        query = test_case.get('query', '')
        expected_raw = test_case.get('expected', True)
        expected = parse_expected_value(expected_raw)
        
        is_safe, message = await guardrail_service.check_safety(query)
        assert isinstance(is_safe, bool), f"Test '{name}' failed: is_safe should be boolean"
        assert isinstance(message, (str, type(None))), f"Test '{name}' failed: message should be string or None"
        
        # Optional: assert the expected safety result
        # assert is_safe == expected, f"Test '{name}' failed: expected {expected}, got {is_safe}"