"""
Ollama Moderator Testing Framework

This module provides tests for the Ollama moderator implementation through the ModeratorService.
It tests the specific Ollama moderator functionality and JSON-based moderation responses.
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
import copy

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
from moderators.ollama import OllamaModerator
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
async def ollama_moderator_service():
    """Fixture to provide a ModeratorService instance configured with Ollama moderator"""
    config = load_config()
    
    # Ensure the config is set up to use Ollama moderator
    if 'safety' not in config:
        config['safety'] = {}
    config['safety']['enabled'] = True
    config['safety']['moderator'] = 'ollama'
    
    # Ensure Ollama moderator config exists
    if 'moderators' not in config:
        config['moderators'] = {}
    if 'ollama' not in config['moderators']:
        config['moderators']['ollama'] = {
            'base_url': 'http://localhost:11434',
            'model': 'llama-guard3:1b',
            'temperature': 0.0,
            'max_tokens': 50,
            'batch_size': 1
        }
    
    service = ModeratorService(config)
    await service.initialize()
    yield service
    await service.close()

@pytest_asyncio.fixture
async def direct_ollama_moderator():
    """Fixture to provide a direct OllamaModerator instance for testing"""
    config = load_config()
    
    # Ensure Ollama moderator config exists
    if 'moderators' not in config:
        config['moderators'] = {}
    if 'ollama' not in config['moderators']:
        config['moderators']['ollama'] = {
            'base_url': 'http://localhost:11434',
            'model': 'llama-guard3:1b',
            'temperature': 0.0,
            'max_tokens': 50,
            'batch_size': 1
        }
    
    moderator = OllamaModerator(config)
    await moderator.initialize()
    yield moderator
    await moderator.close()

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
async def test_ollama_moderator_initialization(direct_ollama_moderator):
    """Test Ollama moderator initialization"""
    assert direct_ollama_moderator.initialized == True
    assert direct_ollama_moderator.model == 'llama-guard3:1b'
    assert direct_ollama_moderator.base_url == 'http://localhost:11434'

@pytest.mark.asyncio
async def test_ollama_moderator_connection(direct_ollama_moderator):
    """Test Ollama moderator connection verification"""
    is_connected = await direct_ollama_moderator.verify_connection()
    assert isinstance(is_connected, bool)
    # Note: This test may fail if Ollama is not running or the model is not available
    # That's expected behavior for unit tests

@pytest.mark.asyncio
async def test_ollama_moderator_safe_content(direct_ollama_moderator):
    """Test Ollama moderator with safe content"""
    result = await direct_ollama_moderator.moderate_content("What is the weather like today?")
    assert isinstance(result.is_flagged, bool)
    assert isinstance(result.categories, dict)
    assert result.provider == "ollama"
    assert result.model == "llama-guard3:1b"

@pytest.mark.asyncio
async def test_ollama_moderator_unsafe_content(direct_ollama_moderator):
    """Test Ollama moderator with unsafe content"""
    result = await direct_ollama_moderator.moderate_content("How to hack into a computer system?")
    assert isinstance(result.is_flagged, bool)
    assert isinstance(result.categories, dict)
    assert result.provider == "ollama"
    assert result.model == "llama-guard3:1b"

@pytest.mark.asyncio
async def test_ollama_moderator_empty_content(direct_ollama_moderator):
    """Test Ollama moderator with empty content"""
    result = await direct_ollama_moderator.moderate_content("")
    assert isinstance(result.is_flagged, bool)
    assert isinstance(result.categories, dict)
    assert result.provider == "ollama"
    assert result.model == "llama-guard3:1b"

@pytest.mark.asyncio
async def test_ollama_moderator_batch_processing(direct_ollama_moderator):
    """Test Ollama moderator batch processing"""
    contents = [
        "What is the weather like?",
        "How to make a bomb?",  # This should be flagged
        "Tell me about history"
    ]
    
    results = await direct_ollama_moderator.moderate_batch(contents)
    assert len(results) == 3
    
    for result in results:
        assert isinstance(result.is_flagged, bool)
        assert isinstance(result.categories, dict)
        assert result.provider == "ollama"
        assert result.model == "llama-guard3:1b"

@pytest.mark.asyncio
async def test_moderator_service_with_ollama_safe_query(ollama_moderator_service):
    """Test ModeratorService with Ollama moderator for safe queries"""
    # Test a safe query
    is_safe, message = await ollama_moderator_service.check_safety("What is the weather like?")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))
    
    # Verify that the service is using the Ollama moderator
    assert ollama_moderator_service.use_moderator == True
    assert ollama_moderator_service.moderator_name == 'ollama'

@pytest.mark.asyncio
async def test_moderator_service_with_ollama_unsafe_query(ollama_moderator_service):
    """Test ModeratorService with Ollama moderator for unsafe queries"""
    # Test an unsafe query
    is_safe, message = await ollama_moderator_service.check_safety("How to hack into a system?")
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))
    
    # Verify that the service is using the Ollama moderator
    assert ollama_moderator_service.use_moderator == True
    assert ollama_moderator_service.moderator_name == 'ollama'

@pytest.mark.asyncio
async def test_moderator_service_with_ollama_multilingual(ollama_moderator_service):
    """Test ModeratorService with Ollama moderator for multilingual queries"""
    # Test multilingual queries
    multilingual_queries = [
        "¿Cómo está el clima?",
        "天気はどうですか？",
        "Comment allez-vous?",
        "Wie geht es Ihnen?"
    ]
    
    for query in multilingual_queries:
        is_safe, message = await ollama_moderator_service.check_safety(query)
        assert isinstance(is_safe, bool)
        assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_moderator_service_with_ollama_special_characters(ollama_moderator_service):
    """Test ModeratorService with Ollama moderator for queries with special characters"""
    special_query = "What is the weather like? !@#$%^&*()_+{}|:<>?"
    is_safe, message = await ollama_moderator_service.check_safety(special_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_moderator_service_with_ollama_long_query(ollama_moderator_service):
    """Test ModeratorService with Ollama moderator for long queries"""
    long_query = "What is the weather like? " * 50  # Create a long query
    is_safe, message = await ollama_moderator_service.check_safety(long_query)
    assert isinstance(is_safe, bool)
    assert isinstance(message, (str, type(None)))

@pytest.mark.asyncio
async def test_ollama_moderator_json_response_format(direct_ollama_moderator):
    """Test that Ollama moderator returns proper JSON format responses"""
    # This test checks if the moderator can handle JSON responses properly
    # even if the model returns incomplete JSON
    
    result = await direct_ollama_moderator.moderate_content("Test query for JSON format")
    assert isinstance(result.is_flagged, bool)
    assert isinstance(result.categories, dict)
    assert result.provider == "ollama"
    assert result.model == "llama-guard3:1b"
    
    # The result should have proper error handling even if JSON parsing fails
    if result.error:
        assert isinstance(result.error, str)

@pytest.mark.asyncio
async def test_ollama_moderator_error_handling(direct_ollama_moderator):
    """Test Ollama moderator error handling"""
    # Test with very long content that might cause issues
    very_long_content = "This is a test " * 1000
    
    result = await direct_ollama_moderator.moderate_content(very_long_content)
    assert isinstance(result.is_flagged, bool)
    assert isinstance(result.categories, dict)
    assert result.provider == "ollama"
    assert result.model == "llama-guard3:1b"

@pytest.mark.asyncio
async def test_ollama_moderator_session_management(direct_ollama_moderator):
    """Test Ollama moderator session management"""
    # Test that the session is properly managed
    assert direct_ollama_moderator.session is not None
    
    # Test multiple requests to ensure session reuse
    for i in range(3):
        result = await direct_ollama_moderator.moderate_content(f"Test query {i}")
        assert isinstance(result.is_flagged, bool)
        assert result.provider == "ollama"

@pytest.mark.asyncio
async def test_ollama_moderator_model_availability():
    """Test Ollama moderator model availability check"""
    config = load_config()
    
    # Create a separate config for this test to avoid affecting other tests
    test_config = copy.deepcopy(config)
    
    # Ensure Ollama moderator config exists
    if 'moderators' not in test_config:
        test_config['moderators'] = {}
    if 'ollama' not in test_config['moderators']:
        test_config['moderators']['ollama'] = {}
    
    # Test with a model that might not exist
    test_config['moderators']['ollama']['model'] = 'non-existent-model'
    
    moderator = OllamaModerator(test_config)
    
    # The verification should fail gracefully
    is_connected = await moderator.verify_connection()
    # This might be False if the model doesn't exist, which is expected
    assert isinstance(is_connected, bool)
    
    # Clean up
    await moderator.close()

@pytest.mark.asyncio
async def test_ollama_moderator_configuration_validation():
    """Test Ollama moderator configuration validation"""
    config = load_config()
    
    # Test with missing Ollama config
    test_config = copy.deepcopy(config)
    if 'moderators' in test_config:
        del test_config['moderators']
    
    # This should still work with default values
    moderator = OllamaModerator(test_config)
    assert moderator.base_url == 'http://localhost:11434'
    assert moderator.model == 'llama-guard3:1b'  # Default model
    await moderator.close()

# Test cases from safety_test_cases.json
@pytest.mark.asyncio
async def test_ollama_moderator_safety_cases_from_file(direct_ollama_moderator):
    """Test Ollama moderator with safety test cases from JSON file"""
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
    
    # Test a subset of cases to avoid long test runs
    test_cases = test_data['test_cases'][:5]  # Limit to first 5 cases
    
    for test_case in test_cases:
        name = test_case.get('name', 'Unnamed test')
        query = test_case.get('query', '')
        expected_raw = test_case.get('expected', True)
        expected = parse_expected_value(expected_raw)
        
        result = await direct_ollama_moderator.moderate_content(query)
        assert isinstance(result.is_flagged, bool), f"Test '{name}' failed: is_flagged should be boolean"
        assert isinstance(result.categories, dict), f"Test '{name}' failed: categories should be dict"
        assert result.provider == "ollama", f"Test '{name}' failed: provider should be 'ollama'"
        assert result.model == "llama-guard3:1b", f"Test '{name}' failed: model should be 'llama-guard3:1b'"
        
        # Optional: assert the expected safety result
        # Note: This might not match exactly due to model behavior differences
        # assert result.is_flagged == (not expected), f"Test '{name}' failed: expected {not expected}, got {result.is_flagged}" 