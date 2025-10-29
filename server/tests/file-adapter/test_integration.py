"""
Integration Tests for File Adapter System

End-to-end tests for file upload, processing, and query workflows.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.file_processing_service import FileProcessingService
from services.file_storage.filesystem_storage import FilesystemStorage
from services.file_metadata.metadata_store import FileMetadataStore


@pytest_asyncio.fixture
async def integrated_system(tmp_path):
    """
    Fixture providing a complete file processing system
    with all components initialized.
    """
    import os
    # Use a temporary database for test isolation
    test_db_path = str(tmp_path / "test_orbit.db")
    
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 200,
        'chunk_overlap': 50,
        'max_file_size': 10485760,  # 10MB
        'supported_types': [
            'text/plain',
            'text/markdown',
            'text/csv',
            'application/json',
        ]
    }

    # Initialize service with temporary database
    service = FileProcessingService(config)
    # Replace metadata store with one using temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    service.metadata_store.close()  # Close the default one
    service.metadata_store = FileMetadataStore(db_path=test_db_path)

    yield {
        'service': service,
        'storage_root': tmp_path / "uploads"
    }

    # Cleanup
    service.metadata_store.close()
    # Clean up test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_complete_upload_workflow(integrated_system):
    """Test complete upload → process → store workflow"""
    service = integrated_system['service']

    # Step 1: Upload file
    file_data = b"This is a comprehensive test document.\n" * 10
    filename = "integration_test.txt"
    mime_type = "text/plain"
    api_key = "integration_test_key"

    # Step 2: Process file
    result = await service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type=mime_type,
        api_key=api_key
    )

    # Step 3: Verify processing result
    assert result["status"] == "completed"
    assert result["filename"] == filename
    assert result["chunk_count"] > 0
    file_id = result["file_id"]

    # Step 4: Verify file is in metadata store
    file_info = await service.metadata_store.get_file_info(file_id)
    assert file_info is not None
    assert file_info["processing_status"] == "completed"

    # Step 5: Verify file is in storage
    storage_key = file_info["storage_key"]
    retrieved_data = await service.storage.get_file(storage_key)
    assert retrieved_data == file_data

    # Step 6: Verify chunks were created
    chunks = await service.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == result["chunk_count"]


@pytest.mark.asyncio
async def test_upload_multiple_files_workflow(integrated_system):
    """Test uploading multiple different file types"""
    service = integrated_system['service']
    api_key = "multi_file_test"

    files_to_upload = [
        (b"Plain text document", "document.txt", "text/plain"),
        (b"# Markdown Document\n\nWith content", "readme.md", "text/markdown"),
        (b'{"key": "value", "data": [1, 2, 3]}', "data.json", "application/json"),
        (b"id,name,value\n1,test,100\n2,demo,200", "data.csv", "text/csv"),
    ]

    file_ids = []

    # Upload all files
    for file_data, filename, mime_type in files_to_upload:
        result = await service.process_file(
            file_data=file_data,
            filename=filename,
            mime_type=mime_type,
            api_key=api_key
        )
        assert result["status"] == "completed"
        file_ids.append(result["file_id"])

    # Verify all files are listed
    files = await service.list_files(api_key)
    assert len(files) >= len(files_to_upload)

    # Verify each file can be retrieved
    for file_id in file_ids:
        retrieved = await service.get_file(file_id, api_key)
        assert len(retrieved) > 0


@pytest.mark.asyncio
async def test_upload_delete_workflow(integrated_system):
    """Test upload → delete → verify workflow"""
    service = integrated_system['service']
    api_key = "delete_test_key"

    # Upload file
    file_data = b"File to be deleted"
    result = await service.process_file(
        file_data=file_data,
        filename="delete_me.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    file_id = result["file_id"]

    # Verify file exists
    file_info = await service.metadata_store.get_file_info(file_id)
    assert file_info is not None

    # Delete file
    delete_success = await service.delete_file(file_id, api_key)
    assert delete_success is True

    # Verify file is gone from metadata
    file_info_after = await service.metadata_store.get_file_info(file_id)
    assert file_info_after is None

    # Verify file is gone from storage
    storage_key = file_info["storage_key"]
    file_exists = await service.storage.file_exists(storage_key)
    assert file_exists is False


@pytest.mark.asyncio
async def test_concurrent_uploads_workflow(integrated_system):
    """Test concurrent file uploads"""
    import asyncio

    service = integrated_system['service']
    api_key = "concurrent_test_key"

    async def upload_file(index):
        file_data = f"Concurrent file {index} content.\n" * 10
        return await service.process_file(
            file_data=file_data.encode(),
            filename=f"concurrent_{index}.txt",
            mime_type="text/plain",
            api_key=api_key
        )

    # Upload 10 files concurrently
    results = await asyncio.gather(*[upload_file(i) for i in range(10)])

    # Verify all uploads succeeded
    assert len(results) == 10
    for result in results:
        assert result["status"] == "completed"

    # Verify all files are tracked
    files = await service.list_files(api_key)
    assert len(files) == 10


@pytest.mark.asyncio
async def test_multi_tenancy_isolation(integrated_system):
    """Test that files are isolated by API key"""
    service = integrated_system['service']

    # Upload files with different API keys
    api_key_1 = "tenant_1"
    api_key_2 = "tenant_2"

    # Tenant 1 files
    result_1 = await service.process_file(
        file_data=b"Tenant 1 data",
        filename="tenant1_file.txt",
        mime_type="text/plain",
        api_key=api_key_1
    )

    # Tenant 2 files
    result_2 = await service.process_file(
        file_data=b"Tenant 2 data",
        filename="tenant2_file.txt",
        mime_type="text/plain",
        api_key=api_key_2
    )

    # Verify tenant 1 can only see their files
    files_1 = await service.list_files(api_key_1)
    assert len(files_1) == 1
    assert files_1[0]["api_key"] == api_key_1

    # Verify tenant 2 can only see their files
    files_2 = await service.list_files(api_key_2)
    assert len(files_2) == 1
    assert files_2[0]["api_key"] == api_key_2

    # Verify tenant 1 cannot access tenant 2's file
    with pytest.raises(PermissionError):
        await service.get_file(result_2["file_id"], api_key_1)

    # Verify tenant 2 cannot delete tenant 1's file
    with pytest.raises(PermissionError):
        await service.delete_file(result_1["file_id"], api_key_2)


@pytest.mark.asyncio
async def test_large_file_workflow(integrated_system):
    """Test processing larger files (within limits)"""
    service = integrated_system['service']
    api_key = "large_file_test"

    # Create 1MB file
    file_data = b"x" * (1024 * 1024)

    result = await service.process_file(
        file_data=file_data,
        filename="large_file.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    assert result["status"] == "completed"
    assert result["file_size"] == len(file_data)

    # Should create multiple chunks
    assert result["chunk_count"] > 10

    # Verify file can be retrieved
    file_id = result["file_id"]
    retrieved = await service.get_file(file_id, api_key)
    assert len(retrieved) == len(file_data)


@pytest.mark.asyncio
async def test_error_recovery_workflow(integrated_system):
    """Test system recovery from errors"""
    service = integrated_system['service']
    api_key = "error_test_key"

    # Try to upload unsupported file type
    try:
        await service.process_file(
            file_data=b"fake binary data",
            filename="image.png",
            mime_type="image/png",  # Not in supported types
            api_key=api_key
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # System should still be functional - upload valid file
    result = await service.process_file(
        file_data=b"Valid text file",
        filename="valid.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_file_lifecycle_workflow(integrated_system):
    """Test complete file lifecycle: upload → list → retrieve → delete"""
    service = integrated_system['service']
    api_key = "lifecycle_test"

    # Step 1: Upload
    file_data = b"Lifecycle test content"
    upload_result = await service.process_file(
        file_data=file_data,
        filename="lifecycle.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    file_id = upload_result["file_id"]
    assert upload_result["status"] == "completed"

    # Step 2: List files
    files = await service.list_files(api_key)
    assert len(files) == 1
    assert files[0]["file_id"] == file_id

    # Step 3: Retrieve file
    retrieved = await service.get_file(file_id, api_key)
    assert retrieved == file_data

    # Step 4: Delete file
    delete_success = await service.delete_file(file_id, api_key)
    assert delete_success is True

    # Step 5: Verify deletion
    files_after = await service.list_files(api_key)
    assert len(files_after) == 0


@pytest.mark.asyncio
async def test_chunking_strategies_comparison(tmp_path):
    """Test different chunking strategies produce different results"""
    import os
    # Test with fixed chunking
    test_db_fixed = str(tmp_path / "test_orbit_fixed.db")
    config_fixed = {
        'storage_root': str(tmp_path / "uploads_fixed"),
        'chunking_strategy': 'fixed',
        'chunk_size': 100,
        'chunk_overlap': 20
    }

    service_fixed = FileProcessingService(config_fixed)
    service_fixed.metadata_store.close()
    service_fixed.metadata_store = FileMetadataStore(db_path=test_db_fixed)

    # Test with semantic chunking
    test_db_semantic = str(tmp_path / "test_orbit_semantic.db")
    config_semantic = {
        'storage_root': str(tmp_path / "uploads_semantic"),
        'chunking_strategy': 'semantic',
        'chunk_size': 5,  # sentences
        'chunk_overlap': 1
    }

    service_semantic = FileProcessingService(config_semantic)
    service_semantic.metadata_store.close()
    service_semantic.metadata_store = FileMetadataStore(db_path=test_db_semantic)

    # Same content, different strategies
    file_data = b"First sentence. Second sentence. Third sentence. " * 10
    api_key = "chunk_comparison"

    result_fixed = await service_fixed.process_file(
        file_data=file_data,
        filename="test_fixed.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    result_semantic = await service_semantic.process_file(
        file_data=file_data,
        filename="test_semantic.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    # Chunk counts may differ
    fixed_chunks = result_fixed["chunks"]
    semantic_chunks = result_semantic["chunks"]

    # Both should have chunks
    assert len(fixed_chunks) > 0
    assert len(semantic_chunks) > 0

    # Verify strategy is recorded in metadata
    assert fixed_chunks[0].metadata["strategy"] == "fixed_size"
    assert semantic_chunks[0].metadata["strategy"] == "semantic"

    # Cleanup
    service_fixed.metadata_store.close()
    service_semantic.metadata_store.close()
    if os.path.exists(test_db_fixed):
        os.remove(test_db_fixed)
    if os.path.exists(test_db_semantic):
        os.remove(test_db_semantic)


@pytest.mark.asyncio
async def test_metadata_persistence(integrated_system):
    """Test that metadata persists across operations"""
    service = integrated_system['service']
    api_key = "metadata_test"

    # Upload file with metadata
    result = await service.process_file(
        file_data=b"Test content",
        filename="metadata_test.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    file_id = result["file_id"]

    # Get file info multiple times
    for _ in range(3):
        file_info = await service.metadata_store.get_file_info(file_id)
        assert file_info["file_id"] == file_id
        assert file_info["processing_status"] == "completed"


@pytest.mark.asyncio
async def test_storage_path_structure(integrated_system):
    """Test that storage paths are organized correctly"""
    service = integrated_system['service']
    storage_root = integrated_system['storage_root']
    api_key = "path_test"

    result = await service.process_file(
        file_data=b"Path test",
        filename="test.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    file_id = result["file_id"]

    # Verify file is stored in correct location
    expected_path = storage_root / api_key / file_id / "test.txt"
    assert expected_path.exists()

    # Verify metadata sidecar exists
    metadata_path = expected_path.parent / f"{expected_path.name}.metadata.json"
    assert metadata_path.exists()


@pytest.mark.asyncio
async def test_empty_file_handling(integrated_system):
    """Test handling of empty files throughout the pipeline"""
    service = integrated_system['service']
    api_key = "empty_test"

    result = await service.process_file(
        file_data=b"",
        filename="empty.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    assert result["status"] == "completed"
    assert result["file_size"] == 0

    # Should be retrievable
    file_id = result["file_id"]
    retrieved = await service.get_file(file_id, api_key)
    assert retrieved == b""


@pytest.mark.asyncio
async def test_special_characters_workflow(integrated_system):
    """Test handling files with special characters"""
    service = integrated_system['service']
    api_key = "special_chars_test"

    # Unicode content and filename
    file_data = "Test with special chars: äöü 中文 emoji 😀".encode('utf-8')
    filename = "test_文件_😀.txt"

    result = await service.process_file(
        file_data=file_data,
        filename=filename,
        mime_type="text/plain",
        api_key=api_key
    )

    assert result["status"] == "completed"
    assert result["filename"] == filename

    # Verify content is preserved
    file_id = result["file_id"]
    retrieved = await service.get_file(file_id, api_key)
    assert retrieved == file_data


@pytest.mark.asyncio
async def test_system_under_load(integrated_system):
    """Test system behavior under higher load"""
    import asyncio

    service = integrated_system['service']
    api_key = "load_test"

    async def upload_and_delete(index):
        # Upload
        result = await service.process_file(
            file_data=f"Load test {index}".encode(),
            filename=f"load_{index}.txt",
            mime_type="text/plain",
            api_key=api_key
        )

        file_id = result["file_id"]

        # Retrieve
        await service.get_file(file_id, api_key)

        # Delete
        await service.delete_file(file_id, api_key)

        return True

    # Run 20 operations concurrently
    results = await asyncio.gather(*[upload_and_delete(i) for i in range(20)])

    # All should succeed
    assert all(results)


@pytest.mark.asyncio
async def test_idempotent_operations(integrated_system):
    """Test idempotency of certain operations"""
    service = integrated_system['service']
    api_key = "idempotent_test"

    # Upload file
    result = await service.process_file(
        file_data=b"Test content",
        filename="test.txt",
        mime_type="text/plain",
        api_key=api_key
    )

    file_id = result["file_id"]

    # Delete once
    success1 = await service.delete_file(file_id, api_key)
    assert success1 is True

    # Try to delete again - should not crash
    # (behavior depends on implementation)
    try:
        success2 = await service.delete_file(file_id, api_key)
        # If it returns False, that's fine
        assert success2 is False
    except FileNotFoundError:
        # If it raises FileNotFoundError, that's also acceptable
        pass
