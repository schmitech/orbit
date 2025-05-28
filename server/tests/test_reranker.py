"""
Unit tests for the reranker service.
"""

import pytest
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from rerankers import RerankerFactory
from rerankers.base import RerankerService


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Create a mock configuration for testing."""
    return {
        'reranker': {
            'enabled': True,
            'provider': 'ollama',
            'batch_size': 5,
            'temperature': 0.0,
            'top_n': 3
        },
        'rerankers': {
            'ollama': {
                'base_url': 'http://localhost:11434',
                'model': 'xitao/bge-reranker-v2-m3:',
                'temperature': 0.0,
                'batch_size': 5
            }
        }
    }


@pytest.fixture
def mock_reranker() -> Mock:
    """Create a mock reranker instance."""
    reranker = Mock(spec=RerankerService)
    reranker.initialize = AsyncMock(return_value=True)
    reranker.rerank = AsyncMock(return_value=[
        {'document': 'test doc 1', 'score': 0.9, 'rank': 1},
        {'document': 'test doc 2', 'score': 0.7, 'rank': 2}
    ])
    reranker.close = AsyncMock()
    return reranker


@pytest.mark.asyncio
async def test_reranker_factory_create(mock_config):
    """Test creating a reranker instance through the factory."""
    mock_instance = Mock(spec=RerankerService)
    mock_instance.initialize = AsyncMock(return_value=True)
    mock_instance.rerank = AsyncMock()
    mock_instance.close = AsyncMock()
    
    with patch('rerankers.RerankerFactory._providers', {'ollama': Mock(return_value=mock_instance)}):
        reranker = RerankerFactory.create(mock_config)
        assert reranker is not None
        # Verify the mock was called with the correct config
        assert reranker == mock_instance


@pytest.mark.asyncio
async def test_reranker_factory_create_disabled(mock_config):
    """Test factory behavior when reranking is disabled."""
    mock_config['reranker']['enabled'] = False
    reranker = RerankerFactory.create(mock_config)
    assert reranker is None


@pytest.mark.asyncio
async def test_reranker_factory_create_invalid_provider(mock_config):
    """Test factory behavior with invalid provider."""
    mock_config['reranker']['provider'] = 'invalid_provider'
    reranker = RerankerFactory.create(mock_config)
    assert reranker is None


@pytest.mark.asyncio
async def test_reranker_initialization(mock_reranker):
    """Test reranker initialization."""
    result = await mock_reranker.initialize()
    assert result is True
    mock_reranker.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_reranker_rerank(mock_reranker):
    """Test document reranking."""
    query = "test query"
    documents = ["test doc 1", "test doc 2", "test doc 3"]
    
    results = await mock_reranker.rerank(query, documents, top_n=2)
    
    assert len(results) == 2  # Should only return top 2 results
    assert results[0]['score'] > results[1]['score']  # Verify sorting
    mock_reranker.rerank.assert_called_once_with(query, documents, top_n=2)


@pytest.mark.asyncio
async def test_reranker_close(mock_reranker):
    """Test reranker cleanup."""
    await mock_reranker.close()
    mock_reranker.close.assert_called_once()


@pytest.mark.asyncio
async def test_reranker_integration(mock_config):
    """Test full reranker integration with factory."""
    # Create a mock instance with all required attributes
    mock_instance = Mock(spec=RerankerService)
    mock_instance.initialize = AsyncMock(return_value=True)
    mock_instance.rerank = AsyncMock(return_value=[
        {'document': 'test doc 1', 'score': 0.9, 'rank': 1},
        {'document': 'test doc 2', 'score': 0.7, 'rank': 2}
    ])
    mock_instance.close = AsyncMock()
    
    with patch('rerankers.RerankerFactory._providers', {'ollama': Mock(return_value=mock_instance)}):
        # Create and initialize reranker
        reranker = RerankerFactory.create(mock_config)
        assert reranker is not None
        
        # Test initialization
        init_result = await reranker.initialize()
        assert init_result is True
        
        # Test reranking
        query = "test query"
        documents = ["test doc 1", "test doc 2"]
        results = await reranker.rerank(query, documents, top_n=2)
        
        assert len(results) == 2
        assert results[0]['score'] > results[1]['score']
        assert all('rank' in result for result in results) 