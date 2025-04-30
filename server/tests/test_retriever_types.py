"""
Tests for the specialized retriever base classes (VectorDBRetriever and SQLRetriever)
"""

import pytest
import asyncio
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock, AsyncMock
import string

# Add the server directory to path to fix import issues
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from retrievers.base_retriever import VectorDBRetriever, SQLRetriever, RetrieverFactory

# Sample implementations for testing
class TestVectorRetriever(VectorDBRetriever):
    """Test implementation of VectorDBRetriever for testing"""
    
    def _get_datasource_name(self) -> str:
        return "test_vector"
        
    async def set_collection(self, collection_name: str) -> None:
        self.collection = collection_name
        
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
                "question": "Test vector question?",
                "answer": "Test vector answer",
                "confidence": 0.95,
                "content": "Test vector content"
            }
        ]

class TestSQLRetriever(SQLRetriever):
    """Test implementation of SQLRetriever for testing"""
    
    def _get_datasource_name(self) -> str:
        return "test_sql"
        
    async def set_collection(self, collection_name: str) -> None:
        self.collection = collection_name
        
    def _tokenize_text(self, text: str) -> List[str]:
        # Simple tokenization for testing
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        return [token for token in text.split() if len(token) > 1]
        
    def _calculate_similarity(self, query: str, text: str) -> float:
        # Simple similarity for testing
        query_tokens = set(self._tokenize_text(query))
        text_tokens = set(self._tokenize_text(text))
        
        if not query_tokens or not text_tokens:
            return 0.0
            
        # Jaccard similarity
        intersection = len(query_tokens.intersection(text_tokens))
        union = len(query_tokens.union(text_tokens))
        return intersection / union if union > 0 else 0.0
        
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
                "question": "Test SQL question?",
                "answer": "Test SQL answer",
                "confidence": 0.85,
                "content": "Test SQL content"
            }
        ]

# Register test retrievers
RetrieverFactory.register_retriever("test_vector", TestVectorRetriever)
RetrieverFactory.register_retriever("test_sql", TestSQLRetriever)

# Sample config for testing
@pytest.fixture
def test_config():
    return {
        "datasources": {
            "test_vector": {
                "confidence_threshold": 0.8,
                "relevance_threshold": 0.6,
                "max_results": 5,
                "return_results": 2,
                "collection": "test_vector_collection"
            },
            "test_sql": {
                "confidence_threshold": 0.75,
                "relevance_threshold": 0.5,
                "max_results": 10,
                "return_results": 3,
                "collection": "test_sql_collection"
            }
        },
        "general": {
            "verbose": False
        },
        "embedding": {
            "enabled": True,
            "provider": "test_provider"
        }
    }

# Create mocks
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

@pytest.fixture
def mock_embedding_service():
    with patch("embeddings.base.EmbeddingServiceFactory") as mock_factory:
        service = AsyncMock()
        mock_factory.create_embedding_service.return_value = service
        
        # Setup embed_query method
        async def embed_query(text):
            return [0.1, 0.2, 0.3, 0.4, 0.5]
            
        service.embed_query.side_effect = embed_query
        service.initialize = AsyncMock()
        service.close = AsyncMock()
        
        yield service

# Test VectorDBRetriever
@pytest.mark.asyncio
async def test_vector_retriever_with_embeddings(test_config, mock_api_key_service, mock_embedding_service):
    """Test vector retriever with embeddings"""
    retriever = TestVectorRetriever(config=test_config)
    
    # Initialize and verify embeddings are set up
    await retriever.initialize()
    assert retriever.embeddings is not None
    assert mock_embedding_service.initialize.called
    
    # Test embed_query functionality
    embedding = await retriever.embed_query("test query")
    assert embedding == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert mock_embedding_service.embed_query.called_with("test query")
    
    # Test retrieval
    results = await retriever.get_relevant_context("test query")
    assert len(results) == 1
    assert results[0]["question"] == "Test vector question?"
    
    # Test cleanup
    await retriever.close()
    assert mock_embedding_service.close.called

# Test SQLRetriever
@pytest.mark.asyncio
async def test_sql_retriever(test_config, mock_api_key_service):
    """Test SQL retriever functionality"""
    retriever = TestSQLRetriever(config=test_config)
    
    # Initialize
    await retriever.initialize()
    
    # Test tokenization
    tokens = retriever._tokenize_text("This is a test query with punctuation!")
    assert "this" in tokens
    assert "test" in tokens
    assert "query" in tokens
    assert "punctuation" in tokens
    
    # Test similarity calculation
    similarity = retriever._calculate_similarity("test query", "this is a test and a query")
    assert similarity > 0.0  # Should find some similarity
    assert similarity <= 1.0  # Should be normalized
    
    # Test retrieval
    results = await retriever.get_relevant_context("test sql query")
    assert len(results) == 1
    assert results[0]["question"] == "Test SQL question?"
    
    # Test cleanup
    await retriever.close()

# Test factory creates correct type
@pytest.mark.asyncio
async def test_factory_creates_correct_type(test_config):
    """Test that the factory creates retrievers of the correct type"""
    vector_retriever = RetrieverFactory.create_retriever("test_vector", test_config)
    sql_retriever = RetrieverFactory.create_retriever("test_sql", test_config)
    
    assert isinstance(vector_retriever, VectorDBRetriever)
    assert isinstance(sql_retriever, SQLRetriever)
    
    # Test specific config
    assert vector_retriever.relevance_threshold == 0.6
    assert sql_retriever.relevance_threshold == 0.5 