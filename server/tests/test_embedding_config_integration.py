"""
Test for embedding service configuration integration.

This test verifies that the singleton correctly uses the global embedding
provider specified in the config and switches when the config changes.
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from embeddings.base import EmbeddingServiceFactory


def test_embedding_service_uses_global_config():
    """Test that embedding service uses the global embedding provider from config."""
    
    # Clear any existing cache
    EmbeddingServiceFactory.clear_cache()
    
    # Config with global embedding provider set to OpenAI
    config_openai = {
        'embedding': {
            'provider': 'openai'
        },
        'embeddings': {
            'openai': {
                'api_key': 'test-key',
                'model': 'text-embedding-3-large'
            }
        }
    }
    
    with patch('embeddings.openai.OpenAIEmbeddingService') as mock_openai:
        mock_instance = Mock()
        mock_openai.return_value = mock_instance
        
        # Create service without specifying provider (should use global config)
        service = EmbeddingServiceFactory.create_embedding_service(config_openai)
        
        # Should have created OpenAI service based on global config
        assert mock_openai.called
        assert service is mock_instance


def test_embedding_service_switches_providers():
    """Test that changing the global config switches embedding providers."""
    
    # Clear any existing cache
    EmbeddingServiceFactory.clear_cache()
    
    # Config with Ollama as global provider
    config_ollama = {
        'embedding': {
            'provider': 'ollama'
        },
        'embeddings': {
            'ollama': {
                'base_url': 'http://localhost:11434',
                'model': 'bge-m3'
            }
        }
    }
    
    # Config with OpenAI as global provider  
    config_openai = {
        'embedding': {
            'provider': 'openai'
        },
        'embeddings': {
            'openai': {
                'api_key': 'test-key',
                'model': 'text-embedding-3-large'
            }
        }
    }
    
    with patch('embeddings.ollama.OllamaEmbeddingService') as mock_ollama, \
         patch('embeddings.openai.OpenAIEmbeddingService') as mock_openai:
        
        mock_ollama_instance = Mock()
        mock_openai_instance = Mock()
        mock_ollama.return_value = mock_ollama_instance
        mock_openai.return_value = mock_openai_instance
        
        # Create service with Ollama config
        service1 = EmbeddingServiceFactory.create_embedding_service(config_ollama)
        
        # Create service with OpenAI config
        service2 = EmbeddingServiceFactory.create_embedding_service(config_openai)
        
        # Should have created both services
        assert mock_ollama.called
        assert mock_openai.called
        assert service1 is mock_ollama_instance
        assert service2 is mock_openai_instance


def test_embedding_service_defaults_to_ollama():
    """Test that embedding service defaults to ollama when no provider is specified."""
    
    # Clear any existing cache
    EmbeddingServiceFactory.clear_cache()
    
    # Config without global embedding provider
    config_no_provider = {
        'embeddings': {
            'ollama': {
                'base_url': 'http://localhost:11434',
                'model': 'bge-m3'
            }
        }
    }
    
    with patch('embeddings.ollama.OllamaEmbeddingService') as mock_ollama:
        mock_instance = Mock()
        mock_ollama.return_value = mock_instance
        
        # Create service without global provider (should default to ollama)
        service = EmbeddingServiceFactory.create_embedding_service(config_no_provider)
        
        # Should have created Ollama service as default
        assert mock_ollama.called
        assert service is mock_instance


def test_embedding_service_cache_key_includes_provider():
    """Test that cache keys properly differentiate between providers."""
    
    config_ollama = {
        'embeddings': {
            'ollama': {
                'host': 'localhost',
                'model': 'bge-m3'
            }
        }
    }
    
    config_openai = {
        'embeddings': {
            'openai': {
                'host': 'api.openai.com', 
                'model': 'text-embedding-3-large'
            }
        }
    }
    
    # Test cache keys for different providers
    ollama_key = EmbeddingServiceFactory._create_cache_key('ollama', config_ollama)
    openai_key = EmbeddingServiceFactory._create_cache_key('openai', config_openai)
    
    # Keys should be different
    assert ollama_key != openai_key
    assert 'ollama' in ollama_key
    assert 'openai' in openai_key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])