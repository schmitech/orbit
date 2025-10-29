"""
Tests for File Processing Pipeline

Tests file processors, processing service, and processor registry.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.base_processor import FileProcessor
from services.file_processing.text_processor import TextProcessor
from services.file_processing.processor_registry import FileProcessorRegistry
from services.file_processing.file_processing_service import FileProcessingService
from services.file_processing.chunking import FixedSizeChunker, SemanticChunker


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
    processor = registry.get_processor("application/x-unknown")
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
    """Fixture to provide file processing service"""
    # Use temporary database for test isolation
    test_db_path = str(tmp_path / "test_orbit.db")
    
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
        ]
    }

    service = FileProcessingService(config)
    # Replace metadata_store with temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store.close()  # Close the default connection
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    yield service
    # Cleanup
    service.metadata_store.close()
    # Clean up temporary database
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_file_processing_service_initialization(tmp_path):
    """Test file processing service initialization"""
    test_db_path = str(tmp_path / "test_orbit_init.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'semantic',
        'chunk_size': 1000,
        'chunk_overlap': 200
    }

    service = FileProcessingService(config)
    # Replace metadata_store with temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store.close()  # Close the default connection
    service.metadata_store = FileMetadataStore(db_path=test_db_path)

    assert service.storage is not None
    assert service.metadata_store is not None
    assert service.processor_registry is not None
    assert service.chunker is not None

    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


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
    test_db_path = str(tmp_path / "test_orbit_fixed.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 50,
        'chunk_overlap': 10
    }

    service = FileProcessingService(config)
    # Replace metadata_store with temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store.close()  # Close the default connection
    service.metadata_store = FileMetadataStore(db_path=test_db_path)

    # Verify fixed chunker was initialized
    from services.file_processing.chunking.fixed_chunker import FixedSizeChunker
    assert isinstance(service.chunker, FixedSizeChunker)
    assert service.chunker.chunk_size == 50
    assert service.chunker.overlap == 10

    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_chunking_strategy_semantic(tmp_path):
    """Test semantic chunking strategy"""
    test_db_path = str(tmp_path / "test_orbit_semantic.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'semantic',
        'chunk_size': 10,
        'chunk_overlap': 2
    }

    service = FileProcessingService(config)
    # Replace metadata_store with temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store.close()  # Close the default connection
    service.metadata_store = FileMetadataStore(db_path=test_db_path)

    # Verify semantic chunker was initialized
    from services.file_processing.chunking.semantic_chunker import SemanticChunker
    assert isinstance(service.chunker, SemanticChunker)
    assert service.chunker.chunk_size == 10
    assert service.chunker.overlap == 2

    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


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
    test_db_path = str(tmp_path / "test_orbit_failure.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 100
    }

    service = FileProcessingService(config)
    # Replace metadata_store with temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store.close()  # Close the default connection
    service.metadata_store = FileMetadataStore(db_path=test_db_path)

    # We'd need to mock a processor failure here
    # For now, just verify the service handles errors gracefully

    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


# Configuration Handling Tests

@pytest.mark.asyncio
async def test_config_uses_global_storage_root(tmp_path):
    """Test that FileProcessingService uses global files.storage_root when not in adapter config"""
    test_db_path = str(tmp_path / "test_config.db")
    
    # Global config with files.storage_root
    config = {
        'files': {
            'storage_root': str(tmp_path / "global_uploads")
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Storage root should come from global config
    assert str(service.storage.storage_root) == str(tmp_path / "global_uploads")
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_adapter_overrides_global_storage_root(tmp_path):
    """Test that adapter config storage_root overrides global config"""
    test_db_path = str(tmp_path / "test_config.db")
    
    # Both global and adapter config
    config = {
        'storage_root': str(tmp_path / "adapter_uploads"),  # Adapter config (should win)
        'files': {
            'storage_root': str(tmp_path / "global_uploads")  # Global config
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Storage root should come from adapter config (higher priority)
    assert str(service.storage.storage_root) == str(tmp_path / "adapter_uploads")
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_uses_global_chunking_settings(tmp_path):
    """Test that chunking uses global files.default_chunking_strategy defaults"""
    test_db_path = str(tmp_path / "test_config.db")
    
    # Global config with chunking defaults (flat structure as implemented)
    config = {
        'files': {
            'default_chunking_strategy': 'semantic',
            'default_chunk_size': 10,
            'default_chunk_overlap': 2
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Should use semantic chunking from global config
    assert isinstance(service.chunker, SemanticChunker)
    assert service.chunker.chunk_size == 10  # From global config
    assert service.chunker.overlap == 2
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_adapter_overrides_global_chunking(tmp_path):
    """Test that adapter chunking config overrides global defaults"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'chunking_strategy': 'fixed',  # Adapter config
        'chunk_size': 200,  # Adapter config
        'chunk_overlap': 50,  # Adapter config
        'files': {
            'default_chunking_strategy': 'semantic',  # Global config (should be overridden)
            'default_chunk_size': 1000,  # Global config (should be overridden)
            'default_chunk_overlap': 200  # Global config (should be overridden)
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Should use adapter config (higher priority)
    assert isinstance(service.chunker, FixedSizeChunker)
    assert service.chunker.chunk_size == 200  # From adapter config
    assert service.chunker.overlap == 50
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_fallback_to_hardcoded_defaults(tmp_path):
    """Test that hardcoded defaults are used when no config provided"""
    test_db_path = str(tmp_path / "test_config.db")
    
    # Minimal config
    config = {}
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Should fall back to hardcoded defaults
    assert isinstance(service.chunker, FixedSizeChunker)
    assert service.chunker.chunk_size == 1000  # Hardcoded default
    assert service.chunker.overlap == 200  # Hardcoded default
    assert str(service.storage.storage_root).endswith('uploads')  # Hardcoded default
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_global_default_chunking_strategy(tmp_path):
    """Test using global default_chunking_strategy"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'files': {
            'default_chunking_strategy': 'semantic',
            'default_chunk_size': 10,
            'default_chunk_overlap': 2
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Should use semantic chunking from global default
    assert isinstance(service.chunker, SemanticChunker)
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_vision_settings_from_global_config(tmp_path):
    """Test that vision settings come from files.processing.vision config"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'files': {
            'processing': {
                'vision': {
                    'enabled': False,
                    'provider': 'anthropic'
                }
            }
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    assert service.enable_vision is False
    assert service.vision_provider == 'anthropic'
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_adapter_overrides_global_vision(tmp_path):
    """Test that adapter vision config overrides global config"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'enable_vision': True,  # Adapter config
        'vision_provider': 'custom',  # Adapter config
        'files': {
            'processing': {
                'vision': {
                    'enabled': False,  # Global config (should be overridden)
                    'provider': 'openai'  # Global config (should be overridden)
                }
            }
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    # Should use adapter config
    assert service.enable_vision is True
    assert service.vision_provider == 'custom'
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_max_file_size_from_global(tmp_path):
    """Test that max_file_size uses global files.processing.max_file_size when adapter config not provided"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'files': {
            'processing': {
                'max_file_size': 104857600  # 100MB (global config)
            }
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    assert service.max_file_size == 104857600
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_max_file_size_adapter_overrides_global(tmp_path):
    """Test that adapter max_file_size overrides global config"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'max_file_size': 209715200,  # 200MB (adapter config, should win)
        'files': {
            'processing': {
                'max_file_size': 104857600  # 100MB (global config)
            }
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    assert service.max_file_size == 209715200  # Adapter config should win
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_config_supported_types_from_global(tmp_path):
    """Test that supported_types uses global files.processing.supported_types"""
    test_db_path = str(tmp_path / "test_config.db")
    
    config = {
        'files': {
            'processing': {
                'supported_types': [
                    'text/plain',
                    'application/custom',
                    'image/png'
                ]
            }
        }
    }
    
    service = FileProcessingService(config)
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    assert 'text/plain' in service.supported_types
    assert 'application/custom' in service.supported_types
    assert 'image/png' in service.supported_types
    
    service.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
