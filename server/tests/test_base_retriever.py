"""
Tests for the BaseRetriever class and factory
"""

import pytest
import asyncio
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock

# Add the server directory to path to fix import issues
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from retrievers.base_retriever import BaseRetriever, RetrieverFactory

# Sample minimal retriever implementation for testing
class TestRetriever(BaseRetriever):
    """Test implementation of BaseRetriever for testing"""
    
    def _get_datasource_name(self) -> str:
        return "test"
        
    async def set_collection(self, collection_name: str) -> None:
        self.collection = collection_name
        
    async def initialize(self) -> None:
        await super().initialize()
        self.initialized = True
        
    async def close(self) -> None:
        await super().close()
        self.closed = True
        
    async def get_relevant_context(self, 
                                  query: str, 
                                  api_key: Optional[str] = None,
                                  collection_name: Optional[str] = None,
                                  **kwargs) -> List[Dict[str, Any]]:
        # Call parent to handle collection resolution
        await super().get_relevant_context(query, api_key, collection_name, **kwargs)
        
        # Return test data
        return [
            {
                "question": "Test question?",
                "answer": "Test answer",
                "confidence": 0.95,
                "content": "Test content"
            }
        ]

# Register the test retriever
RetrieverFactory.register_retriever("test", TestRetriever)

# Sample config for testing
@pytest.fixture
def test_config():
    return {
        "datasources": {
            "test": {
                "confidence_threshold": 0.8,
                "relevance_threshold": 0.6,
                "max_results": 5,
                "return_results": 2,
                "collection": "test_collection"
            }
        },
        "general": {
            "verbose": False
        }
    }

# Create a mock API key service
@pytest.fixture
def mock_api_key_service():
    with patch("services.api_key_service.ApiKeyService") as mock:
        instance = MagicMock()
        mock.return_value = instance
        
        # Setup the validate_api_key method
        async def validate_api_key(api_key):
            if api_key == "valid_key":
                return True, "api_collection"
            return False, None
            
        instance.validate_api_key.side_effect = validate_api_key
        instance.initialize = MagicMock(return_value=asyncio.Future())
        instance.initialize.return_value.set_result(None)
        instance.close = MagicMock(return_value=asyncio.Future())
        instance.close.return_value.set_result(None)
        
        yield instance

# Test the factory
@pytest.mark.asyncio
async def test_factory_creates_retriever(test_config):
    """Test that the factory creates the right retriever"""
    retriever = RetrieverFactory.create_retriever("test", test_config)
    
    assert isinstance(retriever, TestRetriever)
    assert retriever.config == test_config
    assert retriever.confidence_threshold == 0.8
    assert retriever.relevance_threshold == 0.6
    assert retriever.max_results == 5
    assert retriever.return_results == 2
    assert retriever.collection == "test_collection"

# Test retriever initialization
@pytest.mark.asyncio
async def test_retriever_initialization(test_config, mock_api_key_service):
    """Test retriever initialization"""
    retriever = TestRetriever(config=test_config)
    
    await retriever.initialize()
    assert retriever.initialized
    assert mock_api_key_service.initialize.called
    
    await retriever.close()
    assert retriever.closed
    assert mock_api_key_service.close.called

# Test collection resolution
@pytest.mark.asyncio
async def test_collection_resolution(test_config, mock_api_key_service):
    """Test that the retriever resolves collections correctly"""
    retriever = TestRetriever(config=test_config)
    await retriever.initialize()
    
    # Collection from API key
    collection = await retriever._resolve_collection(api_key="valid_key")
    assert collection == "api_collection"
    assert mock_api_key_service.validate_api_key.called_with("valid_key")
    
    # Collection from parameter
    collection = await retriever._resolve_collection(collection_name="param_collection")
    assert collection == "param_collection"
    
    # Default collection
    collection = await retriever._resolve_collection()
    assert collection == "test_collection"

# Test direct answers
@pytest.mark.asyncio
async def test_direct_answer(test_config):
    """Test that direct answers are extracted correctly"""
    retriever = TestRetriever(config=test_config)
    
    # No context
    assert retriever.get_direct_answer([]) is None
    
    # Context with sufficient confidence
    context = [{
        "question": "Test question?",
        "answer": "Test answer",
        "confidence": 0.9  # Above the threshold of 0.8
    }]
    answer = retriever.get_direct_answer(context)
    assert answer == "Question: Test question?\nAnswer: Test answer"
    
    # Context with insufficient confidence
    context = [{
        "question": "Test question?",
        "answer": "Test answer",
        "confidence": 0.7  # Below the threshold of 0.8
    }]
    assert retriever.get_direct_answer(context) is None

# Test get_relevant_context
@pytest.mark.asyncio
async def test_get_relevant_context(test_config, mock_api_key_service):
    """Test retrieving relevant context"""
    retriever = TestRetriever(config=test_config)
    await retriever.initialize()
    
    # Test with valid API key
    context = await retriever.get_relevant_context("test query", api_key="valid_key")
    assert context[0]["question"] == "Test question?"
    assert context[0]["confidence"] == 0.95
    
    # Test with explicit collection name
    context = await retriever.get_relevant_context("test query", collection_name="explicit_collection")
    assert context[0]["question"] == "Test question?"
    assert retriever.collection == "explicit_collection" 