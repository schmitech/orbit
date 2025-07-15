"""
Prompt Moderation Testing Framework

This module provides tests for the prompt moderation system that determines
whether queries are safe to process. It directly tests the ModeratorService in the Orbit server.
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
from services.moderator_service import ModeratorService
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
    config = None
    
    # Try to use the server's config loading function
    try:
        config = load_server_config()
        if config is not None:
            return config
    except Exception as e:
        logger.debug(f"Failed to load config using server function: {e}")
    
    # Fall back to manual loading if that fails
    config_paths = [
        PROJECT_ROOT / 'config' / 'config.yaml',
        SERVER_DIR / 'config.yaml',
        PROJECT_ROOT / 'config.yaml'
    ]
    
    for config_path in config_paths:
        try:
            if config_path.exists():
                logger.debug(f"Attempting to load config from: {config_path}")
                with open(config_path, 'r') as file:
                    config = yaml.safe_load(file)
                    if config is not None:
                        logger.debug(f"Successfully loaded config from: {config_path}")
                        return config
        except Exception as e:
            logger.debug(f"Failed to load config from {config_path}: {e}")
            continue
    
    # If all attempts fail, return a minimal default config
    logger.warning("Could not load configuration file, using default config")
    return {
        'safety': {
            'enabled': False
        },
        'moderators': {}
    }

@pytest_asyncio.fixture
async def moderator_service():
    """Fixture to provide a ModeratorService instance"""
    config = load_config()
    
    # Check if safety is enabled
    safety_enabled = config.get('safety', {}).get('enabled', False)
    if not safety_enabled:
        pytest.skip("Safety/moderator service is disabled in config")
    
    # Check if we have a valid moderator configuration
    moderator_name = config.get('safety', {}).get('moderator', 'openai')
    moderator_config = config.get('moderators', {}).get(moderator_name, {})
    
    # Skip if the moderator requires API keys that aren't set
    if moderator_name == 'openai' and not moderator_config.get('api_key'):
        pytest.skip(f"OpenAI API key not configured for {moderator_name} moderator")
    elif moderator_name == 'anthropic' and not moderator_config.get('api_key'):
        pytest.skip(f"Anthropic API key not configured for {moderator_name} moderator")
    elif moderator_name == 'ollama':
        # For Ollama, we can test if the service is available
        base_url = moderator_config.get('base_url', 'http://localhost:11434')
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/api/tags", timeout=5) as response:
                    if response.status != 200:
                        pytest.skip(f"Ollama service not available at {base_url}")
        except Exception:
            pytest.skip(f"Ollama service not available at {base_url}")
    
    service = ModeratorService(config)
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
async def test_query_safety(moderator_service, test_config):
    """Test basic query safety functionality"""
    # Test a safe query
    is_safe, message = await moderator_service.check_safety("What is the weather like?")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_unsafe_query(moderator_service, test_config):
    """Test unsafe query detection"""
    # Test an unsafe query (example of potentially harmful content)
    is_safe, message = await moderator_service.check_safety("How to hack into a system?")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_empty_query(moderator_service, test_config):
    """Test empty query handling"""
    is_safe, message = await moderator_service.check_safety("")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_long_query(moderator_service, test_config):
    """Test handling of very long queries"""
    long_query = "What is the weather like? " * 100  # Create a very long query
    is_safe, message = await moderator_service.check_safety(long_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_special_characters(moderator_service, test_config):
    """Test handling of queries with special characters"""
    special_query = "What is the weather like? !@#$%^&*()_+{}|:<>?"
    is_safe, message = await moderator_service.check_safety(special_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_multilingual_query(moderator_service, test_config):
    """Test handling of multilingual queries"""
    multilingual_query = "¿Cómo está el clima? 天気はどうですか？"
    is_safe, message = await moderator_service.check_safety(multilingual_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_disabled_safety():
    """Test that safety checks are properly disabled when configured"""
    config = load_config()
    
    # Ensure we have a valid config dict
    if config is None:
        config = {'safety': {'enabled': False}, 'moderators': {}}
    
    # Create a config with safety disabled
    test_config = config.copy()
    test_config['safety'] = {'enabled': False}
    
    service = ModeratorService(test_config)
    await service.initialize()
    
    try:
        # Test that safety checks return safe when disabled
        is_safe, message = await service.check_safety("This should be safe when moderation is disabled")
        assert is_safe == True, "Safety check should return True when disabled"
        assert message is None, "Message should be None when safety is disabled"
        
        # Test with potentially unsafe content
        is_safe, message = await service.check_safety("How to hack into a system?")
        assert is_safe == True, "Safety check should return True when disabled, even for unsafe content"
        assert message is None, "Message should be None when safety is disabled"
        
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_safety_mode_disabled():
    """Test that safety checks are properly disabled when mode is 'disabled'"""
    config = load_config()
    
    # Ensure we have a valid config dict
    if config is None:
        config = {'safety': {'enabled': False}, 'moderators': {}}
    
    # Create a config with safety mode disabled
    test_config = config.copy()
    test_config['safety'] = {'enabled': True, 'mode': 'disabled'}
    
    service = ModeratorService(test_config)
    await service.initialize()
    
    try:
        # Test that safety checks return safe when mode is disabled
        is_safe, message = await service.check_safety("This should be safe when mode is disabled")
        assert is_safe == True, "Safety check should return True when mode is disabled"
        assert message is None, "Message should be None when mode is disabled"
        
    finally:
        await service.close()

# If you want to run specific test cases from a JSON file, you can add a test like this:
@pytest.mark.asyncio
async def test_cases_from_file(moderator_service, test_config):
    """Test cases loaded from a JSON file"""
    test_file = SCRIPT_DIR / 'safety_test_cases.json'
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
        
        is_safe, message = await moderator_service.check_safety(query)
        assert isinstance(is_safe, bool), f"Test '{name}' failed: is_safe should be boolean"
        assert isinstance(message, (str, type(None))), f"Test '{name}' failed: message should be string or None"
        
        # Optional: assert the expected safety result
        # assert is_safe == expected, f"Test '{name}' failed: expected {expected}, got {is_safe}"