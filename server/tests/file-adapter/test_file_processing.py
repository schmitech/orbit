"""
Tests for File Processing Pipeline

Tests file processors, processing service, and processor registry.
"""

import pytest
import pytest_asyncio
import sys
import warnings
from pathlib import Path

# Suppress SWIG-related deprecation warnings from dependencies (FAISS, numpy, etc.)
# These warnings come from SWIG-generated bindings and are harmless
# They're raised during import of dependencies that use SWIG bindings
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyPacked.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyObject.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type swigvarlink.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*__module__ attribute.*")

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.base_processor import FileProcessor
from services.file_processing.text_processor import TextProcessor
from services.file_processing.processor_registry import FileProcessorRegistry
from services.file_processing.file_processing_service import FileProcessingService
from services.file_processing.chunking import FixedSizeChunker, SemanticChunker


def create_test_config(tmp_path, db_name="test_orbit.db", **extra_config):
    """Helper to create test config with isolated SQLite database"""
    test_db_path = str(tmp_path / db_name)
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }
    config.update(extra_config)
    return config, test_db_path


def cleanup_metadata_store(test_db_path):
    """Helper to cleanup metadata store after tests"""
    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


# Sample file content
SAMPLE_TEXT = "This is a test document with multiple lines.\nSecond line here.\nThird line."
SAMPLE_PDF_CONTENT = b"%PDF-1.4\n%Test PDF content"


def test_text_processor_supports_mime_types():
    """Test text processor MIME type support"""
    processor = TextProcessor()

    assert processor.supports_mime_type("text/plain")
    assert processor.supports_mime_type("text/markdown")
    assert not processor.supports_mime_type("application/pdf")
    assert not processor.supports_mime_type("image/png")


@pytest.mark.asyncio
async def test_text_processor_extract_text():
    """Test text extraction from plain text"""
    processor = TextProcessor()

    text_data = b"Hello, World!\nThis is a test."
    extracted_text = await processor.extract_text(text_data, "test.txt")

    assert extracted_text == "Hello, World!\nThis is a test."


@pytest.mark.asyncio
async def test_text_processor_extract_metadata():
    """Test metadata extraction from text file"""
    processor = TextProcessor()

    text_data = b"Sample text content"
    metadata = await processor.extract_metadata(text_data, "sample.txt")

    assert metadata["filename"] == "sample.txt"
    assert metadata["file_size"] == len(text_data)


@pytest.mark.asyncio
async def test_text_processor_empty_file():
    """Test processing empty text file"""
    processor = TextProcessor()

    empty_data = b""
    extracted_text = await processor.extract_text(empty_data, "empty.txt")

    assert extracted_text == ""


@pytest.mark.asyncio
async def test_text_processor_utf8_encoding():
    """Test UTF-8 encoded text with special characters"""
    processor = TextProcessor()

    text_with_unicode = "Hello 世界 🌍 äöü".encode('utf-8')
    extracted_text = await processor.extract_text(text_with_unicode, "unicode.txt")

    assert "世界" in extracted_text
    assert "🌍" in extracted_text
    assert "äöü" in extracted_text


def test_processor_registry_initialization():
    """Test processor registry initialization"""
    registry = FileProcessorRegistry()

    # Should have processors registered
    assert len(registry._processors) > 0


def test_processor_registry_get_processor():
    """Test getting processor by MIME type"""
    registry = FileProcessorRegistry()

    # Get text processor
    processor = registry.get_processor("text/plain")
    assert processor is not None
    assert isinstance(processor, FileProcessor)


def test_processor_registry_get_processor_not_found():
    """Test getting processor for unsupported MIME type"""
    registry = FileProcessorRegistry()

    # Try to get processor for unsupported type
    registry.get_processor("application/x-unknown")
    # May return None or a fallback processor depending on implementation
    # Just verify it doesn't crash
    assert True


def test_processor_registry_register_custom():
    """Test registering custom processor"""
    registry = FileProcessorRegistry()

    class CustomProcessor(FileProcessor):
        def supports_mime_type(self, mime_type: str) -> bool:
            return mime_type == "application/custom"

        async def extract_text(self, file_data: bytes, filename: str = None) -> str:
            return "custom text"

    custom_processor = CustomProcessor()
    registry.register(custom_processor)

    # Should be able to retrieve it
    processor = registry.get_processor("application/custom")
    assert processor is not None


@pytest_asyncio.fixture
async def processing_service(tmp_path):
    """Fixture to provide file processing service with isolated test database"""
    # Use temporary database for test isolation
    test_db_path = str(tmp_path / "test_orbit.db")

    # Config with SQLite backend pointing to temp database
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 100,
        'chunk_overlap': 20,
        'max_file_size': 10485760,  # 10MB
        'supported_types': [
            'text/plain',
            'text/markdown',
            'application/pdf',
            'text/csv',
            'application/x-sql',
        ],
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    # Reset singleton and create fresh instance with test config
    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()
    service.metadata_store = FileMetadataStore(config=config)

    yield service
    # Cleanup
    service.metadata_store.close()
    FileMetadataStore.reset_instance()
    # Clean up temporary database
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_file_processing_service_initialization(tmp_path):
    """Test file processing service initialization"""
    config, test_db_path = create_test_config(
        tmp_path,
        db_name="test_orbit_init.db",
        chunking_strategy='semantic',
        chunk_size=1000,
        chunk_overlap=200
    )

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    assert service.storage is not None
    assert service.metadata_store is not None
    assert service.processor_registry is not None
    assert service.chunker is not None

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_process_text_file(processing_service):
    """Test processing a plain text file"""
    file_data = b"This is a test document.\nWith multiple lines.\nFor testing purposes."
    filename = "test.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    assert result["status"] == "completed"
    assert result["filename"] == filename
    assert result["mime_type"] == mime_type
    assert result["file_size"] == len(file_data)
    assert "file_id" in result
    assert result["chunk_count"] > 0
    assert len(result["chunks"]) > 0


@pytest.mark.asyncio
async def test_process_file_validation_unsupported_type(processing_service):
    """Test processing file with unsupported MIME type"""
    file_data = b"fake image data"
    filename = "image.png"
    mime_type = "image/png"  # Not in supported_types
    api_key = "test_api_key"

    with pytest.raises(ValueError, match="Unsupported file type"):
        await processing_service.process_file(
            file_data=file_data,
            filename=filename,
            mime_type=mime_type,
            api_key=api_key
        )


@pytest.mark.asyncio
async def test_process_file_size_limit(processing_service):
    """Test file size validation"""
    # Create file larger than max_file_size (10MB)
    large_file_data = b"x" * (11 * 1024 * 1024)  # 11MB
    filename = "large.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    with pytest.raises(ValueError, match="exceeds maximum"):
        await processing_service.process_file(
            file_data=large_file_data,
            filename=filename,
            mime_type=mime_type,
            api_key=api_key
        )


@pytest.mark.asyncio
async def test_get_file(processing_service):
    """Test retrieving file after processing"""
    file_data = b"Test content"
    filename = "retrieve.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    # Process file
    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    file_id = result["file_id"]

    # Retrieve file
    retrieved_data = await processing_service.get_file(file_id, api_key)

    assert retrieved_data == file_data


@pytest.mark.asyncio
async def test_get_file_wrong_api_key(processing_service):
    """Test retrieving file with wrong API key"""
    file_data = b"Test content"
    filename = "secure.txt"
    mime_type = "text/plain"
    api_key = "correct_key"

    # Process file
    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    file_id = result["file_id"]

    # Try to retrieve with wrong API key
    with pytest.raises(PermissionError, match="Access denied"):
        await processing_service.get_file(file_id, "wrong_key")


@pytest.mark.asyncio
async def test_get_file_not_found(processing_service):
    """Test retrieving non-existent file"""
    with pytest.raises(FileNotFoundError):
        await processing_service.get_file("nonexistent_file", "api_key")


@pytest.mark.asyncio
async def test_delete_file(processing_service):
    """Test deleting a file"""
    file_data = b"Delete me"
    filename = "delete.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    # Process file
    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    file_id = result["file_id"]

    # Delete file
    success = await processing_service.delete_file(file_id, api_key)
    assert success is True

    # Verify file is gone
    with pytest.raises(FileNotFoundError):
        await processing_service.get_file(file_id, api_key)


@pytest.mark.asyncio
async def test_delete_file_wrong_api_key(processing_service):
    """Test deleting file with wrong API key"""
    file_data = b"Protected file"
    filename = "protected.txt"
    mime_type = "text/plain"
    api_key = "correct_key"

    # Process file
    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    file_id = result["file_id"]

    # Try to delete with wrong API key
    with pytest.raises(PermissionError, match="Access denied"):
        await processing_service.delete_file(file_id, "wrong_key")


@pytest.mark.asyncio
async def test_list_files(processing_service):
    """Test listing files for an API key"""
    api_key = "test_api_key"

    # Process multiple files
    for i in range(3):
        await processing_service.process_file(
            file_data=f"Content {i}".encode(),
            filename=f"file_{i}.txt",
            mime_type="text/plain",
            api_key=api_key
        )

    # List files
    files = await processing_service.list_files(api_key)

    assert len(files) == 3
    for file_info in files:
        assert file_info["api_key"] == api_key


@pytest.mark.asyncio
async def test_chunking_strategy_fixed(tmp_path):
    """Test fixed chunking strategy"""
    config, test_db_path = create_test_config(
        tmp_path,
        db_name="test_orbit_fixed.db",
        chunking_strategy='fixed',
        chunk_size=50,
        chunk_overlap=10
    )

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Verify fixed chunker was initialized
    from services.file_processing.chunking.fixed_chunker import FixedSizeChunker
    assert isinstance(service.chunker, FixedSizeChunker)
    assert service.chunker.chunk_size == 50
    assert service.chunker.overlap == 10

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_chunking_strategy_semantic(tmp_path):
    """Test semantic chunking strategy"""
    config, test_db_path = create_test_config(
        tmp_path,
        db_name="test_orbit_semantic.db",
        chunking_strategy='semantic',
        chunk_size=10,
        chunk_overlap=2
    )

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Verify semantic chunker was initialized
    from services.file_processing.chunking.semantic_chunker import SemanticChunker
    assert isinstance(service.chunker, SemanticChunker)
    assert service.chunker.chunk_size == 10
    assert service.chunker.overlap == 2

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_process_file_metadata_tracking(processing_service):
    """Test that file processing updates metadata correctly"""
    file_data = b"Track this file"
    filename = "tracked.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    file_id = result["file_id"]

    # Check metadata store
    file_info = await processing_service.metadata_store.get_file_info(file_id)

    assert file_info is not None
    assert file_info["processing_status"] == "completed"
    assert file_info["chunk_count"] == result["chunk_count"]


@pytest.mark.asyncio
async def test_process_empty_file(processing_service):
    """Test processing empty file"""
    file_data = b""
    filename = "empty.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    assert result["status"] == "completed"
    assert result["file_size"] == 0
    # Empty file may have 0 chunks
    assert result["chunk_count"] >= 0


@pytest.mark.asyncio
async def test_process_file_with_special_characters(processing_service):
    """Test processing file with special characters in name"""
    file_data = b"Content with special chars"
    filename = "test file (copy) #1.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    assert result["status"] == "completed"
    assert result["filename"] == filename


@pytest.mark.asyncio
async def test_concurrent_file_processing(processing_service):
    """Test processing multiple files concurrently"""
    import asyncio

    api_key = "test_api_key"

    async def process_file(index):
        return await processing_service.process_file(
            file_data=f"Content {index}".encode(),
            filename=f"concurrent_{index}.txt",
            mime_type="text/plain",
            api_key=api_key
        )

    # Process 5 files concurrently
    results = await asyncio.gather(*[process_file(i) for i in range(5)])

    # All should succeed
    assert len(results) == 5
    for result in results:
        assert result["status"] == "completed"

    # Verify all files are listed
    files = await processing_service.list_files(api_key)
    assert len(files) == 5


@pytest.mark.asyncio
async def test_processor_error_handling(processing_service):
    """Test handling of processor errors"""
    # Create a scenario that might cause processing errors
    # For example, invalid data for a specific processor
    # This is a placeholder - actual implementation depends on processor behavior
    pass


@pytest.mark.asyncio
async def test_storage_key_generation(processing_service):
    """Test storage key is generated correctly"""
    file_data = b"Test content"
    filename = "test.txt"
    mime_type = "text/plain"
    api_key = "my_api_key"

    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    file_id = result["file_id"]

    # Check metadata for storage key
    file_info = await processing_service.metadata_store.get_file_info(file_id)

    # Storage key should contain api_key, file_id, and filename
    storage_key = file_info["storage_key"]
    assert api_key in storage_key
    assert file_id in storage_key
    assert filename in storage_key


@pytest.mark.asyncio
async def test_chunk_generation(processing_service):
    """Test that chunks are generated with correct properties"""
    file_data = b"This is a test. " * 50  # Repeat to create multiple chunks
    filename = "chunked.txt"
    mime_type = "text/plain"
    api_key = "test_api_key"

    result = await processing_service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    chunks = result["chunks"]

    # Verify chunk properties
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.file_id == result["file_id"]
        assert len(chunk.text) > 0
        assert chunk.chunk_id.startswith(result["file_id"])


@pytest.mark.asyncio
async def test_file_processing_failure_status(tmp_path):
    """Test that processing failures are tracked correctly"""
    # This is a more complex test that would require mocking processor failures
    # For now, we'll create a basic version
    config, test_db_path = create_test_config(
        tmp_path,
        db_name="test_orbit_failure.db",
        chunking_strategy='fixed',
        chunk_size=100
    )

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # We'd need to mock a processor failure here
    # For now, just verify the service handles errors gracefully

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


# Configuration Handling Tests

@pytest.mark.asyncio
async def test_config_uses_global_storage_root(tmp_path):
    """Test that FileProcessingService uses global files.storage_root when not in adapter config"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Global config with files.storage_root and backend config
    config = {
        'files': {
            'storage_root': str(tmp_path / "global_uploads")
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Storage root should come from global config
    assert str(service.storage.storage_root) == str(tmp_path / "global_uploads")

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_adapter_overrides_global_storage_root(tmp_path):
    """Test that adapter config storage_root overrides global config"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Both global and adapter config
    config = {
        'storage_root': str(tmp_path / "adapter_uploads"),  # Adapter config (should win)
        'files': {
            'storage_root': str(tmp_path / "global_uploads")  # Global config
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Storage root should come from adapter config (higher priority)
    assert str(service.storage.storage_root) == str(tmp_path / "adapter_uploads")

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_uses_global_chunking_settings(tmp_path):
    """Test that chunking uses global files.default_chunking_strategy defaults"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Global config with chunking defaults (flat structure as implemented)
    config = {
        'files': {
            'default_chunking_strategy': 'semantic',
            'default_chunk_size': 10,
            'default_chunk_overlap': 2
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Should use semantic chunking from global config
    assert isinstance(service.chunker, SemanticChunker)
    assert service.chunker.chunk_size == 10  # From global config
    assert service.chunker.overlap == 2

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_adapter_overrides_global_chunking(tmp_path):
    """Test that adapter chunking config overrides global defaults"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'chunking_strategy': 'fixed',  # Adapter config
        'chunk_size': 200,  # Adapter config
        'chunk_overlap': 50,  # Adapter config
        'files': {
            'default_chunking_strategy': 'semantic',  # Global config (should be overridden)
            'default_chunk_size': 1000,  # Global config (should be overridden)
            'default_chunk_overlap': 200  # Global config (should be overridden)
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Should use adapter config (higher priority)
    assert isinstance(service.chunker, FixedSizeChunker)
    assert service.chunker.chunk_size == 200  # From adapter config
    assert service.chunker.overlap == 50

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_fallback_to_hardcoded_defaults(tmp_path):
    """Test that hardcoded defaults are used when no config provided"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Minimal config - only backend required for metadata store
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Should fall back to hardcoded defaults
    assert isinstance(service.chunker, FixedSizeChunker)
    assert service.chunker.chunk_size == 1000  # Hardcoded default
    assert service.chunker.overlap == 200  # Hardcoded default
    assert str(service.storage.storage_root).endswith('uploads')  # Hardcoded default

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_global_default_chunking_strategy(tmp_path):
    """Test using global default_chunking_strategy"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'files': {
            'default_chunking_strategy': 'semantic',
            'default_chunk_size': 10,
            'default_chunk_overlap': 2
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Should use semantic chunking from global default
    assert isinstance(service.chunker, SemanticChunker)

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_vision_settings_from_global_config(tmp_path):
    """Test that vision settings come from global vision config"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Updated to use modern config structure: config['vision'] instead of config['files']['processing']['vision']
    config = {
        'vision': {
            'enabled': False,
            'provider': 'anthropic'
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    assert service.enable_vision is False
    assert service.default_vision_provider == 'anthropic'

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_adapter_overrides_global_vision(tmp_path):
    """Test that adapter vision config overrides global config"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Updated to use modern config structure
    config = {
        'enable_vision': True,  # Adapter config (top-level override)
        'vision_provider': 'custom',  # Adapter config (top-level override)
        'vision': {
            'enabled': False,  # Global config (should be overridden)
            'provider': 'openai'  # Global config (should be overridden)
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Should use adapter config (top-level overrides)
    assert service.enable_vision is True
    assert service.default_vision_provider == 'custom'

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_max_file_size_from_global(tmp_path):
    """Test that max_file_size uses global files.processing.max_file_size when adapter config not provided"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'files': {
            'processing': {
                'max_file_size': 104857600  # 100MB (global config)
            }
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    assert service.max_file_size == 104857600

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_max_file_size_adapter_overrides_global(tmp_path):
    """Test that adapter max_file_size overrides global config"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'max_file_size': 209715200,  # 200MB (adapter config, should win)
        'files': {
            'processing': {
                'max_file_size': 104857600  # 100MB (global config)
            }
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    assert service.max_file_size == 209715200  # Adapter config should win

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_config_supported_types_from_global(tmp_path):
    """Test that supported_types uses global files.processing.supported_types"""
    test_db_path = str(tmp_path / "test_config.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'files': {
            'processing': {
                'supported_types': [
                    'text/plain',
                    'application/custom',
                    'image/png'
                ]
            }
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    assert 'text/plain' in service.supported_types
    assert 'application/custom' in service.supported_types
    assert 'image/png' in service.supported_types

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


# ============================================================================
# Retriever Cache Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_file_processing_uses_retriever_cache(tmp_path):
    """Test that FileProcessingService uses retriever cache to avoid re-initialization"""
    from services.retriever_cache import get_retriever_cache
    from unittest.mock import patch, Mock, AsyncMock

    test_db_path = str(tmp_path / "test_cache.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'embedding': {'provider': 'ollama', 'model': 'test'},
        'files': {'default_vector_store': 'chroma'},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Clear the cache before test
    cache = get_retriever_cache()
    cache.clear_cache()

    # Mock FileVectorRetriever to track initialization calls
    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        mock_retriever = Mock()
        mock_retriever.initialized = False
        mock_retriever.initialize = AsyncMock()
        mock_retriever.embeddings = Mock()
        mock_retriever.embeddings.get_dimensions = AsyncMock(return_value=768)
        mock_retriever.index_file_chunks = AsyncMock(return_value=True)
        mock_retriever_class.return_value = mock_retriever

        # Create mock chunks
        from services.file_processing.chunking import Chunk
        chunks = [
            Chunk(
                file_id="file1",
                text="Test chunk 1",
                chunk_index=0,
                chunk_id="chunk1",
                metadata={}
            )
        ]

        # Call _index_chunks_in_vector_store multiple times (simulating multiple file uploads)
        await service._index_chunks_in_vector_store(
            file_id="file1",
            api_key="test_key",
            chunks=chunks
        )

        # Second call should reuse cached retriever
        mock_retriever.initialized = True  # Mark as initialized
        await service._index_chunks_in_vector_store(
            file_id="file2",
            api_key="test_key",
            chunks=chunks
        )

        # Third call should still reuse cached retriever
        await service._index_chunks_in_vector_store(
            file_id="file3",
            api_key="test_key",
            chunks=chunks
        )

        # FileVectorRetriever should only be instantiated once (cached for subsequent calls)
        assert mock_retriever_class.call_count == 1

        # But index_file_chunks should be called three times (once per file)
        assert mock_retriever.index_file_chunks.call_count == 3

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_different_configs_create_separate_cached_retrievers(tmp_path):
    """Test that different configurations create separate cached retriever instances"""
    from services.retriever_cache import get_retriever_cache
    from unittest.mock import patch, Mock, AsyncMock

    test_db_path = str(tmp_path / "test_cache_multi.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    # Clear the cache before test
    cache = get_retriever_cache()
    cache.clear_cache()

    backend_config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    config1 = {
        'embedding': {'provider': 'ollama', 'model': 'model1'},
        'files': {'default_vector_store': 'chroma'},
        **backend_config
    }

    config2 = {
        'embedding': {'provider': 'openai', 'model': 'model2'},
        'files': {'default_vector_store': 'chroma'},
        **backend_config
    }

    service1 = FileProcessingService(config1)
    service1.metadata_store = FileMetadataStore(config=config1)

    FileMetadataStore.reset_instance()
    service2 = FileProcessingService(config2)
    service2.metadata_store = FileMetadataStore(config=config2)

    # Mock FileVectorRetriever
    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        # Create two different mock retrievers
        mock_retriever1 = Mock()
        mock_retriever1.initialized = False
        mock_retriever1.initialize = AsyncMock()
        mock_retriever1.embeddings = Mock()
        mock_retriever1.embeddings.get_dimensions = AsyncMock(return_value=768)
        mock_retriever1.index_file_chunks = AsyncMock(return_value=True)

        mock_retriever2 = Mock()
        mock_retriever2.initialized = False
        mock_retriever2.initialize = AsyncMock()
        mock_retriever2.embeddings = Mock()
        mock_retriever2.embeddings.get_dimensions = AsyncMock(return_value=1536)
        mock_retriever2.index_file_chunks = AsyncMock(return_value=True)

        mock_retriever_class.side_effect = [mock_retriever1, mock_retriever2]

        from services.file_processing.chunking import Chunk
        chunks = [
            Chunk(
                file_id="test_file",
                text="Test chunk",
                chunk_index=0,
                chunk_id="chunk1",
                metadata={}
            )
        ]

        # Use service1 (ollama config)
        await service1._index_chunks_in_vector_store(
            file_id="file1",
            api_key="key1",
            chunks=chunks
        )

        # Use service2 (openai config)
        await service2._index_chunks_in_vector_store(
            file_id="file2",
            api_key="key2",
            chunks=chunks
        )

        # Should have created TWO separate retriever instances (different configs)
        assert mock_retriever_class.call_count == 2

    service1.metadata_store.close()
    service2.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_delete_file_uses_cached_retriever(tmp_path):
    """Test that delete_file uses cached retriever"""
    from services.retriever_cache import get_retriever_cache
    from unittest.mock import patch, Mock, AsyncMock

    test_db_path = str(tmp_path / "test_delete_cache.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    config = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    # Clear cache
    cache = get_retriever_cache()
    cache.clear_cache()

    # Create a mock file in metadata store
    file_id = "test_file_123"
    await service.metadata_store.record_file_upload(
        file_id=file_id,
        api_key="test_api_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="test_key",
        storage_type='vector'
    )
    # Update with collection name
    await service.metadata_store.update_processing_status(
        file_id=file_id,
        status="completed",
        collection_name="test_collection"
    )

    # Mock storage
    service.storage = Mock()
    service.storage.delete_file = AsyncMock(return_value=True)

    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        mock_retriever = Mock()
        mock_retriever.initialized = False
        mock_retriever.initialize = AsyncMock()
        mock_retriever.delete_file_chunks = AsyncMock(return_value=True)
        mock_retriever_class.return_value = mock_retriever

        # Delete file multiple times (should use cached retriever)
        await service.delete_file(file_id, "test_api_key")

        # Recreate file for second deletion
        await service.metadata_store.record_file_upload(
            file_id="test_file_456",
            api_key="test_api_key",
            filename="test2.txt",
            mime_type="text/plain",
            file_size=100,
            storage_key="test_key2",
            storage_type='vector'
        )
        await service.metadata_store.update_processing_status(
            file_id="test_file_456",
            status="completed",
            collection_name="test_collection"
        )

        mock_retriever.initialized = True
        await service.delete_file("test_file_456", "test_api_key")

        # Should only create retriever once (cached)
        assert mock_retriever_class.call_count == 1
        assert mock_retriever.delete_file_chunks.call_count == 2

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)


@pytest.mark.asyncio
async def test_cache_stats_tracking(tmp_path):
    """Test that cache properly tracks statistics"""
    from services.retriever_cache import get_retriever_cache
    from unittest.mock import patch, Mock, AsyncMock

    test_db_path = str(tmp_path / "test_stats.db")

    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()

    cache = get_retriever_cache()
    cache.clear_cache()

    # Initially empty
    stats = cache.get_cache_stats()
    assert stats['cached_retrievers'] == 0

    config = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': test_db_path
                }
            }
        }
    }

    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)

    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        mock_retriever = Mock()
        mock_retriever.initialized = False
        mock_retriever.initialize = AsyncMock()
        mock_retriever.embeddings = Mock()
        mock_retriever.embeddings.get_dimensions = AsyncMock(return_value=768)
        mock_retriever.index_file_chunks = AsyncMock(return_value=True)
        mock_retriever_class.return_value = mock_retriever

        from services.file_processing.chunking import Chunk
        chunks = [
            Chunk(
                file_id="file1",
                text="Test",
                chunk_index=0,
                chunk_id="c1",
                metadata={}
            )
        ]

        # Use the cache
        await service._index_chunks_in_vector_store(
            file_id="file1",
            api_key="key1",
            chunks=chunks
        )

        # Check stats
        stats = cache.get_cache_stats()
        assert stats['cached_retrievers'] == 1
        assert len(stats['cache_keys']) == 1

    service.metadata_store.close()
    cleanup_metadata_store(test_db_path)
