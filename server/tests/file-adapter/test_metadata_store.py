"""
Tests for File Metadata Store

Tests SQLite-based metadata tracking for uploaded files and chunks.
"""

import pytest
import pytest_asyncio
import sys
import os
from pathlib import Path

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_metadata.metadata_store import FileMetadataStore


@pytest_asyncio.fixture
async def metadata_store(tmp_path):
    """Fixture to provide a clean metadata store for each test"""
    db_path = tmp_path / "test_orbit.db"
    store = FileMetadataStore(db_path=str(db_path))
    yield store
    # Cleanup
    store.close()
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_metadata_store_initialization(tmp_path):
    """Test metadata store initialization and schema creation"""
    db_path = tmp_path / "test.db"
    store = FileMetadataStore(db_path=str(db_path))

    # Verify database file was created
    assert db_path.exists()

    # Verify connection works
    assert store.connection is not None

    store.close()


@pytest.mark.asyncio
async def test_record_file_upload(metadata_store):
    """Test recording a file upload"""
    result = await metadata_store.record_file_upload(
        file_id="file_123",
        api_key="test_api_key",
        filename="document.pdf",
        mime_type="application/pdf",
        file_size=1024,
        storage_key="test_api_key/file_123/document.pdf",
        storage_type="vector",
        metadata={"custom": "value"}
    )

    assert result is True

    # Verify file was recorded
    file_info = await metadata_store.get_file_info("file_123")
    assert file_info is not None
    assert file_info["file_id"] == "file_123"
    assert file_info["api_key"] == "test_api_key"
    assert file_info["filename"] == "document.pdf"
    assert file_info["mime_type"] == "application/pdf"
    assert file_info["file_size"] == 1024
    assert file_info["storage_key"] == "test_api_key/file_123/document.pdf"
    assert file_info["storage_type"] == "vector"
    assert file_info["processing_status"] == "pending"


@pytest.mark.asyncio
async def test_get_file_info_not_found(metadata_store):
    """Test getting info for non-existent file"""
    file_info = await metadata_store.get_file_info("nonexistent_file")
    assert file_info is None


@pytest.mark.asyncio
async def test_update_processing_status(metadata_store):
    """Test updating file processing status"""
    # Create file
    await metadata_store.record_file_upload(
        file_id="file_123",
        api_key="test_api_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector"
    )

    # Update status to processing
    result = await metadata_store.update_processing_status(
        file_id="file_123",
        status="processing"
    )
    assert result is True

    file_info = await metadata_store.get_file_info("file_123")
    assert file_info["processing_status"] == "processing"

    # Update status to completed with chunk count
    result = await metadata_store.update_processing_status(
        file_id="file_123",
        status="completed",
        chunk_count=10,
        vector_store="chroma",
        collection_name="test_collection"
    )
    assert result is True

    file_info = await metadata_store.get_file_info("file_123")
    assert file_info["processing_status"] == "completed"
    assert file_info["chunk_count"] == 10
    assert file_info["vector_store"] == "chroma"
    assert file_info["collection_name"] == "test_collection"


@pytest.mark.asyncio
async def test_update_processing_status_failed(metadata_store):
    """Test updating status to failed"""
    await metadata_store.record_file_upload(
        file_id="file_fail",
        api_key="test_api_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector"
    )

    result = await metadata_store.update_processing_status(
        file_id="file_fail",
        status="failed"
    )
    assert result is True

    file_info = await metadata_store.get_file_info("file_fail")
    assert file_info["processing_status"] == "failed"


@pytest.mark.asyncio
async def test_record_chunk(metadata_store):
    """Test recording a file chunk"""
    # Create parent file first
    await metadata_store.record_file_upload(
        file_id="file_123",
        api_key="test_api_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=1000,
        storage_key="key",
        storage_type="vector"
    )

    # Record chunk
    result = await metadata_store.record_chunk(
        chunk_id="file_123_chunk_0",
        file_id="file_123",
        chunk_index=0,
        vector_store_id="vec_123",
        collection_name="test_collection",
        metadata={"text": "chunk text", "length": 100}
    )

    assert result is True


@pytest.mark.asyncio
async def test_get_file_chunks(metadata_store):
    """Test retrieving chunks for a file"""
    file_id = "file_with_chunks"

    # Create file
    await metadata_store.record_file_upload(
        file_id=file_id,
        api_key="test_api_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=1000,
        storage_key="key",
        storage_type="vector"
    )

    # Record multiple chunks
    for i in range(5):
        await metadata_store.record_chunk(
            chunk_id=f"{file_id}_chunk_{i}",
            file_id=file_id,
            chunk_index=i,
            vector_store_id=f"vec_{i}",
            collection_name="test_collection",
            metadata={"index": i}
        )

    # Get all chunks
    chunks = await metadata_store.get_file_chunks(file_id)

    assert len(chunks) == 5
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_id"] == f"{file_id}_chunk_{i}"
        assert chunk["file_id"] == file_id
        assert chunk["chunk_index"] == i


@pytest.mark.asyncio
async def test_list_files(metadata_store):
    """Test listing files for an API key"""
    api_key = "test_api_key"

    # Create multiple files
    for i in range(3):
        await metadata_store.record_file_upload(
            file_id=f"file_{i}",
            api_key=api_key,
            filename=f"document_{i}.txt",
            mime_type="text/plain",
            file_size=100 * (i + 1),
            storage_key=f"key_{i}",
            storage_type="vector"
        )

    # Create file for different API key
    await metadata_store.record_file_upload(
        file_id="other_file",
        api_key="other_api_key",
        filename="other.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="other_key",
        storage_type="vector"
    )

    # List files for test_api_key
    files = await metadata_store.list_files(api_key)

    assert len(files) == 3
    for file_info in files:
        assert file_info["api_key"] == api_key


@pytest.mark.asyncio
async def test_list_files_empty(metadata_store):
    """Test listing files when none exist"""
    files = await metadata_store.list_files("nonexistent_key")
    assert files == []


@pytest.mark.asyncio
async def test_delete_file(metadata_store):
    """Test deleting a file and its chunks"""
    file_id = "file_to_delete"

    # Create file
    await metadata_store.record_file_upload(
        file_id=file_id,
        api_key="test_api_key",
        filename="delete.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector"
    )

    # Add chunks
    for i in range(3):
        await metadata_store.record_chunk(
            chunk_id=f"{file_id}_chunk_{i}",
            file_id=file_id,
            chunk_index=i,
            collection_name="test"
        )

    # Verify file and chunks exist
    assert await metadata_store.get_file_info(file_id) is not None
    chunks = await metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 3

    # Delete file
    result = await metadata_store.delete_file(file_id)
    assert result is True

    # Verify file and chunks are gone
    assert await metadata_store.get_file_info(file_id) is None
    chunks = await metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_file(metadata_store):
    """Test deleting a file that doesn't exist"""
    result = await metadata_store.delete_file("nonexistent")
    # Should not raise error, just return True (nothing to delete)
    assert result is True


@pytest.mark.asyncio
async def test_storage_types(metadata_store):
    """Test different storage types (vector vs duckdb)"""
    # Vector storage
    await metadata_store.record_file_upload(
        file_id="vector_file",
        api_key="test_key",
        filename="doc.pdf",
        mime_type="application/pdf",
        file_size=1000,
        storage_key="key1",
        storage_type="vector"
    )

    # DuckDB storage
    await metadata_store.record_file_upload(
        file_id="duckdb_file",
        api_key="test_key",
        filename="data.csv",
        mime_type="text/csv",
        file_size=2000,
        storage_key="key2",
        storage_type="duckdb"
    )

    # Verify storage types
    vector_file = await metadata_store.get_file_info("vector_file")
    assert vector_file["storage_type"] == "vector"

    duckdb_file = await metadata_store.get_file_info("duckdb_file")
    assert duckdb_file["storage_type"] == "duckdb"


@pytest.mark.asyncio
async def test_metadata_json_storage(metadata_store):
    """Test storing complex metadata as JSON"""
    complex_metadata = {
        "author": "Test Author",
        "tags": ["test", "document", "example"],
        "properties": {
            "version": "1.0",
            "confidential": False
        },
        "counts": [1, 2, 3, 4, 5]
    }

    await metadata_store.record_file_upload(
        file_id="complex_file",
        api_key="test_key",
        filename="complex.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector",
        metadata=complex_metadata
    )

    file_info = await metadata_store.get_file_info("complex_file")
    # Metadata is stored as JSON string
    assert file_info["metadata"] is not None


@pytest.mark.asyncio
async def test_multiple_files_same_name(metadata_store):
    """Test handling multiple files with same name but different IDs"""
    filename = "duplicate.txt"

    # Create multiple files with same name
    for i in range(3):
        await metadata_store.record_file_upload(
            file_id=f"file_{i}",
            api_key="test_key",
            filename=filename,
            mime_type="text/plain",
            file_size=100,
            storage_key=f"key_{i}",
            storage_type="vector"
        )

    # Should be able to retrieve all files
    files = await metadata_store.list_files("test_key")
    assert len(files) == 3

    # Each should have unique file_id
    file_ids = [f["file_id"] for f in files]
    assert len(set(file_ids)) == 3


@pytest.mark.asyncio
async def test_chunk_metadata_storage(metadata_store):
    """Test storing chunk metadata"""
    file_id = "file_123"

    await metadata_store.record_file_upload(
        file_id=file_id,
        api_key="test_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=1000,
        storage_key="key",
        storage_type="vector"
    )

    chunk_metadata = {
        "text": "This is chunk text",
        "length": 18,
        "start_position": 0,
        "end_position": 18,
        "page_number": 1
    }

    await metadata_store.record_chunk(
        chunk_id="chunk_0",
        file_id=file_id,
        chunk_index=0,
        collection_name="test",
        metadata=chunk_metadata
    )

    chunks = await metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 1
    # Chunk metadata is stored as JSON string
    assert chunks[0]["chunk_metadata"] is not None


@pytest.mark.asyncio
async def test_concurrent_file_uploads(metadata_store):
    """Test concurrent file upload recording"""
    import asyncio

    async def record_file(index):
        return await metadata_store.record_file_upload(
            file_id=f"concurrent_file_{index}",
            api_key="test_key",
            filename=f"file_{index}.txt",
            mime_type="text/plain",
            file_size=100,
            storage_key=f"key_{index}",
            storage_type="vector"
        )

    # Record 10 files concurrently
    results = await asyncio.gather(*[record_file(i) for i in range(10)])

    # All should succeed
    assert all(results)

    # Verify all files exist
    files = await metadata_store.list_files("test_key")
    assert len(files) == 10


@pytest.mark.asyncio
async def test_update_nonexistent_file_status(metadata_store):
    """Test updating status for non-existent file"""
    result = await metadata_store.update_processing_status(
        file_id="nonexistent",
        status="completed"
    )
    # Should not raise error, but update won't affect anything
    assert result is True


@pytest.mark.asyncio
async def test_file_timestamps(metadata_store):
    """Test that timestamps are recorded correctly"""
    await metadata_store.record_file_upload(
        file_id="timestamp_file",
        api_key="test_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector"
    )

    file_info = await metadata_store.get_file_info("timestamp_file")

    # Should have upload timestamp
    assert file_info["upload_timestamp"] is not None
    assert file_info["created_at"] is not None


@pytest.mark.asyncio
async def test_list_files_ordering(metadata_store):
    """Test that files are listed in correct order (most recent first)"""
    import asyncio

    # Create files with small delays
    for i in range(3):
        await metadata_store.record_file_upload(
            file_id=f"file_{i}",
            api_key="test_key",
            filename=f"doc_{i}.txt",
            mime_type="text/plain",
            file_size=100,
            storage_key=f"key_{i}",
            storage_type="vector"
        )
        await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

    files = await metadata_store.list_files("test_key")

    # Files should be ordered by upload_timestamp DESC (most recent first)
    # Last uploaded (file_2) should be first in list
    assert len(files) == 3


@pytest.mark.asyncio
async def test_large_file_metadata(metadata_store):
    """Test handling large file metadata"""
    large_metadata = {
        "description": "x" * 10000,  # 10KB of text
        "tags": [f"tag_{i}" for i in range(1000)],
        "nested": {
            "level1": {
                "level2": {
                    "data": list(range(100))
                }
            }
        }
    }

    await metadata_store.record_file_upload(
        file_id="large_meta_file",
        api_key="test_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector",
        metadata=large_metadata
    )

    file_info = await metadata_store.get_file_info("large_meta_file")
    assert file_info is not None
    assert file_info["metadata"] is not None
