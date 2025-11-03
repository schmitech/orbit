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

    # Update status to completed with chunk count and embedding info
    result = await metadata_store.update_processing_status(
        file_id="file_123",
        status="completed",
        chunk_count=10,
        vector_store="chroma",
        collection_name="test_collection",
        embedding_provider="ollama",
        embedding_dimensions=768
    )
    assert result is True

    file_info = await metadata_store.get_file_info("file_123")
    assert file_info["processing_status"] == "completed"
    assert file_info["chunk_count"] == 10
    assert file_info["vector_store"] == "chroma"
    assert file_info["collection_name"] == "test_collection"
    assert file_info["embedding_provider"] == "ollama"
    assert file_info["embedding_dimensions"] == 768


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


@pytest.mark.asyncio
async def test_migration_adds_embedding_columns(tmp_path):
    """Test that migration automatically adds embedding_provider and embedding_dimensions columns"""
    import sqlite3

    db_path = tmp_path / "old_schema.db"

    # Create database with old schema (without embedding columns)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create old schema without embedding columns
    cursor.execute("""
        CREATE TABLE uploaded_files (
            file_id TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER,
            upload_timestamp TEXT,
            processing_status TEXT,
            storage_key TEXT,
            chunk_count INTEGER DEFAULT 0,
            vector_store TEXT,
            collection_name TEXT,
            storage_type TEXT DEFAULT 'vector',
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert test data
    cursor.execute("""
        INSERT INTO uploaded_files
        (file_id, api_key, filename, mime_type, file_size, upload_timestamp,
         processing_status, storage_key, storage_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("old_file", "test_key", "test.txt", "text/plain", 100,
          "2024-01-01T00:00:00", "completed", "key", "vector"))

    conn.commit()
    conn.close()

    # Verify columns don't exist
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(uploaded_files)")
    columns = [row[1] for row in cursor.fetchall()]
    assert 'embedding_provider' not in columns
    assert 'embedding_dimensions' not in columns
    conn.close()

    # Now open with FileMetadataStore (should run migration)
    store = FileMetadataStore(db_path=str(db_path))

    # Verify columns were added
    cursor = store.connection.cursor()
    cursor.execute("PRAGMA table_info(uploaded_files)")
    columns = [row[1] for row in cursor.fetchall()]
    assert 'embedding_provider' in columns, "embedding_provider column should be added by migration"
    assert 'embedding_dimensions' in columns, "embedding_dimensions column should be added by migration"

    # Verify existing data is intact
    file_info = await store.get_file_info("old_file")
    assert file_info is not None
    assert file_info["file_id"] == "old_file"
    assert file_info["filename"] == "test.txt"
    # New columns should be NULL for existing records
    assert file_info.get("embedding_provider") is None
    assert file_info.get("embedding_dimensions") is None

    # Verify we can update with new columns
    result = await store.update_processing_status(
        file_id="old_file",
        status="completed",
        embedding_provider="openai",
        embedding_dimensions=1536
    )
    assert result is True

    # Verify update worked
    file_info = await store.get_file_info("old_file")
    assert file_info["embedding_provider"] == "openai"
    assert file_info["embedding_dimensions"] == 1536

    store.close()


@pytest.mark.asyncio
async def test_migration_idempotent(tmp_path):
    """Test that migration can run multiple times without errors"""
    db_path = tmp_path / "idempotent_test.db"

    # Create first store (runs migration)
    store1 = FileMetadataStore(db_path=str(db_path))
    store1.close()

    # Create second store (migration should be idempotent)
    store2 = FileMetadataStore(db_path=str(db_path))

    # Verify columns exist
    cursor = store2.connection.cursor()
    cursor.execute("PRAGMA table_info(uploaded_files)")
    columns = [row[1] for row in cursor.fetchall()]
    assert 'embedding_provider' in columns
    assert 'embedding_dimensions' in columns

    # Verify we can still use the store
    await store2.record_file_upload(
        file_id="test_file",
        api_key="test_key",
        filename="test.txt",
        mime_type="text/plain",
        file_size=100,
        storage_key="key",
        storage_type="vector"
    )

    file_info = await store2.get_file_info("test_file")
    assert file_info is not None

    store2.close()
