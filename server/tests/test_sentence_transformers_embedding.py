"""
Sentence Transformers Embedding Service Test Suite

This module contains tests for the Sentence Transformers embedding service functionality:
- Configuration loading and validation
- Local model embedding generation
- Remote API embedding (mocked)
- Batch processing
- Device detection
- Dimensions validation
- Error handling
- Normalization
"""

import pytest
import yaml
import os
import sys
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Get the absolute path to the project root directory (parent of server)
project_root = os.path.dirname(server_dir)

# Add server directory to Python path
sys.path.append(server_dir)


@pytest.fixture
def config() -> Dict[str, Any]:
    """Load and return the configuration"""
    # Use the server's config loading function to handle the modular config structure
    try:
        from config.config_manager import load_config as load_server_config
        loaded_config = load_server_config()
        if loaded_config:
            return loaded_config
    except Exception as e:
        print(f"Failed to load config using config_manager: {e}")
        pass

    # Fallback to manual loading if that fails
    embeddings_path = os.path.join(project_root, 'config', 'embeddings.yaml')
    if not os.path.exists(embeddings_path):
        raise FileNotFoundError(f"Embeddings config file not found at {embeddings_path}")

    with open(embeddings_path, 'r') as file:
        embeddings_config = yaml.safe_load(file)

    # Also load base config.yaml if needed
    config_path = os.path.join(project_root, 'config', 'config.yaml')
    base_config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as file:
            base_config = yaml.safe_load(file) or {}

    # Merge embeddings config into base config
    base_config.update(embeddings_config)

    return base_config


@pytest.fixture
def st_embedding_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and return Sentence Transformers embedding configuration"""
    st_config = config.get('embeddings', {}).get('sentence_transformers', {})

    assert st_config.get('model'), "Sentence Transformers model must be specified in config"
    return st_config


@pytest.fixture
def test_text() -> str:
    """Return a test text for embedding"""
    return "This is a test sentence for embedding generation."


@pytest.fixture
def test_texts() -> list:
    """Return multiple test texts for batch embedding"""
    return [
        "First test sentence.",
        "Second test sentence with different length.",
        "Third sentence is here.",
        "Fourth and final test sentence."
    ]


def test_config_loading(st_embedding_config: Dict[str, Any]):
    """Test that the embedding configuration is loaded correctly"""
    assert st_embedding_config, "Sentence Transformers configuration should not be empty"
    assert "model" in st_embedding_config, "Model should be specified in config"
    assert st_embedding_config["model"], "Model should not be empty"
    assert "mode" in st_embedding_config, "Mode should be specified in config"
    assert st_embedding_config["mode"] in ["local", "remote"], "Mode must be 'local' or 'remote'"


def test_device_detection():
    """Test device detection logic"""
    from ai_services.providers.sentence_transformers_base import SentenceTransformersBaseService

    # Mock config
    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "auto"
            }
        }
    }

    service = SentenceTransformersBaseService(config)

    # Device should be set based on available hardware
    assert service.device in ["cuda", "mps", "cpu"], f"Invalid device: {service.device}"
    print(f"Detected device: {service.device}")


@pytest.mark.asyncio
async def test_local_embedding_generation(st_embedding_config: Dict[str, Any], test_text: str):
    """Test local embedding generation"""
    # Skip if mode is remote or if sentence-transformers is not installed
    if st_embedding_config.get("mode") == "remote":
        pytest.skip("Config is set to remote mode, skipping local test")

    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    # Create config for local mode
    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",  # Small, fast model for testing
                "mode": "local",
                "device": "cpu",  # Force CPU for consistent testing
                "normalize_embeddings": True,
                "batch_size": 4,
                "dimensions": 384  # all-MiniLM-L6-v2 has 384 dimensions
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    try:
        # Generate embedding
        embedding = await service.embed_query(test_text)

        # Validate embedding
        assert isinstance(embedding, list), "Embedding should be a list"
        assert len(embedding) > 0, "Embedding should not be empty"
        assert all(isinstance(x, (int, float)) for x in embedding), "All values should be numeric"

        # Check dimensions
        assert len(embedding) == 384, f"Expected 384 dimensions, got {len(embedding)}"

        print(f"Generated embedding with {len(embedding)} dimensions")

    finally:
        await service.close()


@pytest.mark.asyncio
async def test_batch_embedding_generation(st_embedding_config: Dict[str, Any], test_texts: list):
    """Test batch embedding generation"""
    # Skip if mode is remote or if sentence-transformers is not installed
    if st_embedding_config.get("mode") == "remote":
        pytest.skip("Config is set to remote mode, skipping local test")

    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "cpu",
                "normalize_embeddings": True,
                "batch_size": 2,  # Small batch for testing
                "dimensions": 384
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    try:
        # Generate batch embeddings
        embeddings = await service.embed_documents(test_texts)

        # Validate embeddings
        assert isinstance(embeddings, list), "Embeddings should be a list"
        assert len(embeddings) == len(test_texts), f"Expected {len(test_texts)} embeddings, got {len(embeddings)}"

        # Check each embedding
        for i, embedding in enumerate(embeddings):
            assert isinstance(embedding, list), f"Embedding {i} should be a list"
            assert len(embedding) == 384, f"Embedding {i} should have 384 dimensions"
            assert all(isinstance(x, (int, float)) for x in embedding), f"Embedding {i} should contain only numbers"

        print(f"Generated {len(embeddings)} embeddings successfully")

    finally:
        await service.close()


@pytest.mark.asyncio
async def test_dimensions_consistency(st_embedding_config: Dict[str, Any]):
    """Test that embeddings have consistent dimensions across multiple calls"""
    # Skip if mode is remote or if sentence-transformers is not installed
    if st_embedding_config.get("mode") == "remote":
        pytest.skip("Config is set to remote mode, skipping local test")

    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "cpu",
                "normalize_embeddings": True,
                "dimensions": 384
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    try:
        test_texts = [
            "Short text.",
            "This is a longer text with more content.",
            "Medium length text here."
        ]

        dimensions = []
        for text in test_texts:
            embedding = await service.embed_query(text)
            dimensions.append(len(embedding))

        # All embeddings should have the same dimensions
        assert len(set(dimensions)) == 1, f"Embeddings should have consistent dimensions, got: {dimensions}"
        print(f"All embeddings have consistent dimensions: {dimensions[0]}")

    finally:
        await service.close()


@pytest.mark.asyncio
async def test_get_dimensions(st_embedding_config: Dict[str, Any]):
    """Test the get_dimensions method"""
    # Skip if mode is remote or if sentence-transformers is not installed
    if st_embedding_config.get("mode") == "remote":
        pytest.skip("Config is set to remote mode, skipping local test")

    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "cpu",
                "dimensions": 384
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    try:
        # Get dimensions
        dims = await service.get_dimensions()
        assert isinstance(dims, int), "Dimensions should be an integer"
        assert dims == 384, f"Expected 384 dimensions, got {dims}"
        print(f"Model dimensions: {dims}")

    finally:
        await service.close()


@pytest.mark.asyncio
async def test_empty_text_handling():
    """Test that empty text is handled appropriately"""
    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "cpu"
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    try:
        # Empty text should raise ValueError
        with pytest.raises(ValueError, match="Text cannot be empty"):
            await service.embed_query("")

        # Whitespace-only text should also raise ValueError
        with pytest.raises(ValueError, match="Text cannot be empty"):
            await service.embed_query("   ")

    finally:
        await service.close()


@pytest.mark.asyncio
async def test_normalization():
    """Test embedding normalization"""
    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    import math

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "cpu",
                "normalize_embeddings": True
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    try:
        # Generate embedding
        embedding = await service.embed_query("Test normalization")

        # Calculate L2 norm
        norm = math.sqrt(sum(x * x for x in embedding))

        # Normalized embeddings should have L2 norm close to 1
        assert abs(norm - 1.0) < 0.01, f"Normalized embedding should have L2 norm ~1.0, got {norm}"
        print(f"Embedding L2 norm: {norm} (normalized)")

    finally:
        await service.close()


@pytest.mark.asyncio
async def test_remote_mode_with_mock():
    """Test remote mode with mocked HTTP calls"""
    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "BAAI/bge-m3",
                "mode": "remote",
                "api_key": "test_key",
                "base_url": "https://api-inference.huggingface.co/models",
                "normalize_embeddings": False,
                "dimensions": 1024
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize service (no actual HTTP call in remote mode init)
    initialized = await service.initialize()
    assert initialized, "Service should initialize successfully"

    # Mock the HTTP response
    mock_embedding = [0.1] * 1024  # Mock 1024-dimensional embedding

    with patch('aiohttp.ClientSession') as mock_session:
        # Create mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_embedding)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # Create mock session context
        mock_session_instance = AsyncMock()
        mock_session_instance.post = Mock(return_value=mock_response)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance

        try:
            # Test embedding
            embedding = await service.embed_query("Test text")

            # Validate
            assert isinstance(embedding, list), "Embedding should be a list"
            assert len(embedding) == 1024, f"Expected 1024 dimensions, got {len(embedding)}"
            print("Remote mode test successful with mocked API")

        finally:
            await service.close()


@pytest.mark.asyncio
async def test_error_handling_on_init():
    """Test error handling when model fails to load"""
    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    # Use a non-existent model
    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "nonexistent/model-that-does-not-exist-12345",
                "mode": "local",
                "device": "cpu"
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Initialize should fail gracefully
    initialized = await service.initialize()
    assert not initialized, "Service should fail to initialize with invalid model"
    print("Error handling test passed - invalid model handled gracefully")


@pytest.mark.asyncio
async def test_uninitialized_service_error():
    """Test that using service before initialization raises appropriate error"""
    try:
        from ai_services.implementations.embedding.sentence_transformers_embedding_service import (
            SentenceTransformersEmbeddingService
        )
    except ImportError:
        pytest.skip("sentence-transformers not installed")

    config = {
        "embeddings": {
            "sentence_transformers": {
                "model": "all-MiniLM-L6-v2",
                "mode": "local",
                "device": "cpu"
            }
        }
    }

    service = SentenceTransformersEmbeddingService(config)

    # Don't initialize - but the service will auto-initialize on first call
    # So we need to mock the initialize to return False
    with patch.object(service, 'initialize', new_callable=AsyncMock) as mock_init:
        mock_init.return_value = False

        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to initialize"):
            await service.embed_query("Test")

    print("Uninitialized service error test passed")
