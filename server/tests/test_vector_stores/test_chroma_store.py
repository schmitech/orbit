"""
Tests for ChromaStore metadata sanitization.

Regression coverage for: chunk metadata containing a dict-valued field
(e.g. HTMLProcessor's `meta_tags`, merged into every chunk's metadata)
caused ChromaDB's upsert() to reject the whole batch with
"Expected metadata value to be a str, int, float, bool, SparseVector,
list, or None, got {} which is a dict in upsert" — silently failing
indexing for the file (status still 'completed', but no collection_name).
"""

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from vector_stores.base.base_store import StoreConfig
from vector_stores.implementations.chroma_store import ChromaStore, _sanitize_chroma_metadata


def test_sanitize_chroma_metadata_json_encodes_dict_values():
    metadata = {
        "file_id": "file_1",
        "chunk_index": 0,
        "meta_tags": {},
        "nested": {"a": 1},
        "tags": ["x", "y"],
        "count": 3,
        "ok": True,
        "missing": None,
    }

    sanitized = _sanitize_chroma_metadata(metadata)

    assert sanitized["file_id"] == "file_1"
    assert sanitized["chunk_index"] == 0
    assert sanitized["meta_tags"] == "{}"
    assert sanitized["nested"] == '{"a": 1}'
    # Non-dict values pass through unchanged (Chroma accepts lists natively).
    assert sanitized["tags"] == ["x", "y"]
    assert sanitized["count"] == 3
    assert sanitized["ok"] is True
    assert sanitized["missing"] is None


@pytest.mark.asyncio
async def test_add_vectors_with_empty_dict_metadata_value():
    """An empty-dict metadata field (the HTML meta_tags case) must not fail
    the whole upsert; previously it raised inside chromadb and add_vectors
    returned False."""
    store = ChromaStore(StoreConfig(name="test", connection_params={}))
    assert await store.connect()

    try:
        success = await store.add_vectors(
            vectors=[[0.1, 0.2, 0.3]],
            ids=["chunk_1"],
            metadata=[{"file_id": "file_1", "chunk_index": 0, "meta_tags": {}}],
            collection_name="test_collection",
            documents=["some chunk text"],
        )
        assert success is True

        results = await store.search_vectors(
            query_vector=[0.1, 0.2, 0.3],
            limit=1,
            collection_name="test_collection",
        )
        assert len(results) == 1
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_add_vectors_with_nested_dict_metadata_value():
    """A non-empty nested dict value must also be preserved, not dropped."""
    store = ChromaStore(StoreConfig(name="test", connection_params={}))
    assert await store.connect()

    try:
        success = await store.add_vectors(
            vectors=[[0.4, 0.5, 0.6]],
            ids=["chunk_2"],
            metadata=[{"file_id": "file_2", "props": {"version": "1.0"}}],
            collection_name="test_collection_2",
            documents=["other chunk text"],
        )
        assert success is True
    finally:
        await store.disconnect()
