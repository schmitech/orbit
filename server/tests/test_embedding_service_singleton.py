"""
Test for embedding service singleton functionality.

This test verifies that the EmbeddingServiceFactory properly reuses
instances instead of creating new ones for the same configuration.
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from embeddings.base import EmbeddingServiceFactory


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    return {
        'embedding': {
            'provider': 'ollama'
        },
        'embeddings': {
            'ollama': {
                'host': 'localhost',
                'port': 11434,
                'model': 'bge-m3'
            }
        }
    }


def test_embedding_service_singleton_same_config(mock_config):
    """Test that the same configuration returns the same instance."""
    
    # Clear any existing cache
    EmbeddingServiceFactory.clear_cache()
    
    with patch('embeddings.ollama.OllamaEmbeddingService') as mock_ollama:
        # Create a mock instance
        mock_instance = Mock()
        mock_ollama.return_value = mock_instance
        
        # Create first service
        service1 = EmbeddingServiceFactory.create_embedding_service(mock_config)
        
        # Create second service with same config
        service2 = EmbeddingServiceFactory.create_embedding_service(mock_config)
        
        # Should be the same instance
        assert service1 is service2
        
        # OllamaEmbeddingService should only be called once
        assert mock_ollama.call_count == 1


def test_embedding_service_singleton_different_configs():
    """Test that different configurations create different instances."""
    
    # Clear any existing cache
    EmbeddingServiceFactory.clear_cache()
    
    config1 = {
        'embedding': {'provider': 'ollama'},
        'embeddings': {
            'ollama': {
                'host': 'localhost',
                'port': 11434,
                'model': 'bge-m3'
            }
        }
    }
    
    config2 = {
        'embedding': {'provider': 'ollama'},
        'embeddings': {
            'ollama': {
                'host': 'localhost',
                'port': 11434,
                'model': 'different-model'  # Different model
            }
        }
    }
    
    with patch('embeddings.ollama.OllamaEmbeddingService') as mock_ollama:
        # Create mock instances
        mock_instance1 = Mock()
        mock_instance2 = Mock()
        mock_ollama.side_effect = [mock_instance1, mock_instance2]
        
        # Create services with different configs
        service1 = EmbeddingServiceFactory.create_embedding_service(config1)
        service2 = EmbeddingServiceFactory.create_embedding_service(config2)
        
        # Should be different instances
        assert service1 is not service2
        assert service1 is mock_instance1
        assert service2 is mock_instance2
        
        # OllamaEmbeddingService should be called twice
        assert mock_ollama.call_count == 2


def test_embedding_service_cache_key_generation():
    """Test that cache keys are generated correctly."""
    
    config = {
        'embeddings': {
            'ollama': {
                'host': 'localhost',
                'model': 'bge-m3'
            }
        }
    }
    
    cache_key = EmbeddingServiceFactory._create_cache_key('ollama', config)
    expected_key = 'ollama:localhost:bge-m3'
    
    assert cache_key == expected_key


def test_embedding_service_clear_cache():
    """Test that cache clearing works properly."""
    
    # Clear any existing cache
    EmbeddingServiceFactory.clear_cache()
    
    config = {
        'embedding': {'provider': 'ollama'},
        'embeddings': {
            'ollama': {
                'host': 'localhost',
                'model': 'bge-m3'
            }
        }
    }
    
    with patch('embeddings.ollama.OllamaEmbeddingService') as mock_ollama:
        mock_instance = Mock()
        mock_ollama.return_value = mock_instance
        
        # Create a service
        service1 = EmbeddingServiceFactory.create_embedding_service(config)
        
        # Verify it's cached
        cached_instances = EmbeddingServiceFactory.get_cached_instances()
        assert len(cached_instances) == 1
        
        # Clear cache
        EmbeddingServiceFactory.clear_cache()
        
        # Verify cache is empty
        cached_instances = EmbeddingServiceFactory.get_cached_instances()
        assert len(cached_instances) == 0
        
        # Create another service - should create new instance
        service2 = EmbeddingServiceFactory.create_embedding_service(config)
        
        # Should be different instance now (new creation)
        assert mock_ollama.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])