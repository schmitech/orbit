"""
Tests for hierarchical-chunking retrieval: FileVectorRetriever.get_chunk()
and parent-expansion (Phase 2/3 of docs/roadmap/chunking/hierarchical-chunking.md).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from retrievers.implementations.file.file_retriever import FileVectorRetriever


def make_retriever(encryptor=None) -> FileVectorRetriever:
    retriever = FileVectorRetriever(config={'files': {}})
    retriever.metadata_store = AsyncMock()
    retriever._encryptor = encryptor
    return retriever


def result(chunk_id: str, confidence: float, hierarchy_parent_id: str | None, content: str = "leaf text") -> dict:
    chunk_metadata = {'hierarchy_parent_id': hierarchy_parent_id} if hierarchy_parent_id else {}
    return {
        'content': content,
        'metadata': {'chunk_id': chunk_id, 'confidence': confidence},
        'file_metadata': {'chunk_metadata': chunk_metadata},
    }


@pytest.mark.asyncio
async def test_get_chunk_returns_plain_db_metadata():
    retriever = make_retriever()
    retriever.metadata_store.get_chunk_info.return_value = {
        'chunk_metadata': {'text': 'parent section text'}
    }
    data = await retriever.get_chunk("file1_chunk_0")
    assert data == {'text': 'parent section text'}


@pytest.mark.asyncio
async def test_get_chunk_returns_none_when_missing():
    retriever = make_retriever()
    retriever.metadata_store.get_chunk_info.return_value = None
    assert await retriever.get_chunk("missing") is None


@pytest.mark.asyncio
async def test_get_chunk_decrypts_encrypted_envelope():
    class FakeEncryptor:
        def decrypt(self, payload: bytes, aad: bytes) -> bytes:
            assert aad == b"parent_1"
            return b'{"text": "decrypted parent text"}'

    retriever = make_retriever(encryptor=FakeEncryptor())
    retriever.metadata_store.get_chunk_info.return_value = {
        'chunk_metadata': {'encrypted': True, 'payload': b'\x00'.hex()}
    }
    data = await retriever.get_chunk("parent_1")
    assert data == {'text': 'decrypted parent text'}


@pytest.mark.asyncio
async def test_get_chunk_without_encryptor_returns_none_for_encrypted_envelope():
    retriever = make_retriever(encryptor=None)
    retriever.metadata_store.get_chunk_info.return_value = {
        'chunk_metadata': {'encrypted': True, 'payload': 'aa'}
    }
    assert await retriever.get_chunk("parent_1") is None


@pytest.mark.asyncio
async def test_expand_attaches_parent_text_to_single_result():
    retriever = make_retriever()
    retriever.get_chunk = AsyncMock(return_value={'text': 'parent context'})
    results = [result("leaf_0", 0.9, "parent_0")]

    await retriever._expand_hierarchical_parents(results)

    retriever.get_chunk.assert_awaited_once_with("parent_0")
    assert "parent context" in results[0]['content']
    assert "leaf text" in results[0]['content']


@pytest.mark.asyncio
async def test_expand_dedups_shared_parent_across_siblings():
    retriever = make_retriever()
    retriever.get_chunk = AsyncMock(return_value={'text': 'shared parent'})
    low = result("leaf_0", 0.5, "parent_0")
    high = result("leaf_1", 0.9, "parent_0")
    results = [low, high]

    await retriever._expand_hierarchical_parents(results)

    retriever.get_chunk.assert_awaited_once_with("parent_0")
    assert "shared parent" in high['content']
    assert "shared parent" not in low['content']


@pytest.mark.asyncio
async def test_expand_is_noop_for_non_hierarchical_results():
    retriever = make_retriever()
    retriever.get_chunk = AsyncMock()
    results = [result("leaf_0", 0.9, None)]
    original_content = results[0]['content']

    await retriever._expand_hierarchical_parents(results)

    retriever.get_chunk.assert_not_awaited()
    assert results[0]['content'] == original_content


@pytest.mark.asyncio
async def test_expand_skips_silently_on_missing_parent():
    retriever = make_retriever()
    retriever.get_chunk = AsyncMock(return_value=None)
    results = [result("leaf_0", 0.9, "parent_missing")]
    original_content = results[0]['content']

    await retriever._expand_hierarchical_parents(results)

    assert results[0]['content'] == original_content


@pytest.mark.asyncio
async def test_expand_skips_silently_on_get_chunk_exception():
    retriever = make_retriever()
    retriever.get_chunk = AsyncMock(side_effect=RuntimeError("boom"))
    results = [result("leaf_0", 0.9, "parent_0")]
    original_content = results[0]['content']

    await retriever._expand_hierarchical_parents(results)

    assert results[0]['content'] == original_content


@pytest.mark.asyncio
async def test_expand_truncates_to_per_parent_char_limit():
    retriever = make_retriever()
    retriever.hierarchy_parent_char_limit = 10
    retriever.get_chunk = AsyncMock(return_value={'text': 'x' * 100})
    results = [result("leaf_0", 0.9, "parent_0")]

    await retriever._expand_hierarchical_parents(results)

    assert 'x' * 10 in results[0]['content']
    assert 'x' * 11 not in results[0]['content']


@pytest.mark.asyncio
async def test_expand_truncates_to_total_request_char_budget():
    retriever = make_retriever()
    retriever.hierarchy_parent_char_limit = 100
    retriever.hierarchy_total_parent_char_limit = 10
    retriever.get_chunk = AsyncMock(side_effect=[{'text': 'a' * 10}, {'text': 'b' * 10}])
    results = [result("leaf_0", 0.9, "parent_0"), result("leaf_1", 0.9, "parent_1", content="other leaf")]

    await retriever._expand_hierarchical_parents(results)

    # First group consumes the entire total budget; second group gets nothing attached.
    assert 'a' * 10 in results[0]['content']
    assert 'b' not in results[1]['content']
