"""
Phase 4 gate: explicit ingestion completeness and recoverable cache state.

Covers ChunkManager.store_chunks's structured IngestionResult (complete /
partial / failed), idempotent retry of only the missing pieces, and
generation isolation in retrieve_chunks so changed content, model, or budget
never mixes pieces from different generations of the same URL.
"""

from unittest.mock import AsyncMock

import pytest
from utils.chunk_manager import ChunkManager, IngestionStatus
from utils.embedding_recovery import RecoveryConfig

pytestmark = pytest.mark.unit


def _chunks(n, prefix="chunk"):
    return [
        {"content": f"{prefix} {i}", "chunk_id": i, "total_chunks": n}
        for i in range(n)
    ]


class ScriptedEmbeddingClient:
    """Embeds successfully unless the text is in `fail_texts` (checked once
    per call, so retries with the same text can be scripted to succeed)."""

    def __init__(self, fail_texts=None, dimension=3):
        self.fail_texts = set(fail_texts or [])
        self.dimension = dimension
        self.calls = []
        # One text per provider call, so one failing piece never drags down
        # the whole batch -- matches the packing behavior real providers
        # expose via a batch_size cap.
        self.batch_size = 1

    async def embed_documents_tracked(self, texts, usage_sink=None):
        self.calls.append(list(texts))
        if usage_sink is not None:
            usage_sink.update({
                "prompt_tokens": len(texts), "completion_tokens": 0, "total_tokens": len(texts),
                "provider": "fake", "model": "fake-model", "reported": True,
            })
        vectors = []
        for text in texts:
            if text in self.fail_texts:
                raise FakeTransientError()
            vectors.append([0.1] * self.dimension)
        return vectors


class FakeTransientError(Exception):
    def __init__(self):
        super().__init__("transient")
        self.status_code = 503


class RecordingVectorStore:
    """Records every add_vectors call; can be configured to fail specific ids."""

    def __init__(self, fail_ids=None):
        self.fail_ids = set(fail_ids or [])
        self.writes = {}  # id -> (vector, metadata)
        self.calls = []

    async def add_vectors(self, vectors, ids, metadata, collection_name=None):
        self.calls.append(list(ids))
        if any(i in self.fail_ids for i in ids):
            return False
        for vector_id, vector, meta in zip(ids, vectors, metadata):
            self.writes[vector_id] = (vector, meta)
        return True

    async def search_vectors(self, query_vector, limit=10, collection_name=None, filter_metadata=None):
        results = []
        for vector_id, (vector, meta) in self.writes.items():
            if filter_metadata and any(meta.get(k) != v for k, v in filter_metadata.items()):
                continue
            results.append({"id": vector_id, "score": 1.0, "metadata": meta})
        return results[:limit]

    async def get_vector(self, vector_id, collection_name=None):
        if vector_id not in self.writes:
            return None
        vector, meta = self.writes[vector_id]
        return {"id": vector_id, "vector": vector, "metadata": meta}

    async def delete_by_metadata(self, metadata_filter, collection_name=None):
        to_delete = [
            vector_id for vector_id, (_, meta) in self.writes.items()
            if all(meta.get(k) == v for k, v in metadata_filter.items())
        ]
        for vector_id in to_delete:
            del self.writes[vector_id]
        return True


class AddOnlyVectorStore(RecordingVectorStore):
    """Mimics the default persistent Chroma adapter: add_vectors rejects any
    id that already exists (no upsert) instead of overwriting it."""

    async def add_vectors(self, vectors, ids, metadata, collection_name=None):
        self.calls.append(list(ids))
        if any(i in self.writes for i in ids):
            return False
        for vector_id, vector, meta in zip(ids, vectors, metadata):
            self.writes[vector_id] = (vector, meta)
        return True


def _no_delay_config(**overrides):
    # max_attempts is a shared budget across every piece in the call (Phase
    # 3), not per piece -- keep it generous here so these tests exercise
    # ingestion-state behavior, not the attempt budget itself.
    kwargs = {"max_attempts": 20, "deadline_seconds": 5.0, "base_delay": 0.0, "max_delay": 0.0, "max_concurrency": 4}
    kwargs.update(overrides)
    return RecoveryConfig(**kwargs)


# ---------------------------------------------------------------------------
# Structured status: complete / partial / failed
# ---------------------------------------------------------------------------

async def test_all_pieces_succeed_yields_complete_status():
    client = ScriptedEmbeddingClient()
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    result = await manager.store_chunks(_chunks(3), "https://example.com/a", metadata={})

    assert result.status == IngestionStatus.COMPLETE
    assert result.expected_count == 3
    assert result.stored_count == 3
    assert result.failed_count == 0
    assert result.failed_ids == []


async def test_one_failure_among_several_yields_partial_and_recovers_on_retry():
    """A partial result: complete cache lookup is false, and the next
    ingestion attempt recovers only the missing piece."""
    client = ScriptedEmbeddingClient(fail_texts={"chunk 1"})
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    first = await manager.store_chunks(_chunks(3), "https://example.com/b", metadata={})

    assert first.status == IngestionStatus.PARTIAL
    assert first.stored_count == 2
    assert first.failed_count == 1
    assert await manager.has_cached_chunks("https://example.com/b") is False

    # Fix the underlying failure and retry with the same content.
    client.fail_texts.clear()
    second = await manager.store_chunks(_chunks(3), "https://example.com/b", metadata={})

    assert second.status == IngestionStatus.COMPLETE
    assert second.stored_count == 3
    # Only the missing piece was re-embedded -- not the whole document.
    assert client.calls[-1] == ["chunk 1"]


async def test_successful_pieces_are_not_duplicated_on_retry():
    client = ScriptedEmbeddingClient(fail_texts={"chunk 1"})
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    await manager.store_chunks(_chunks(3), "https://example.com/c", metadata={})
    client.fail_texts.clear()
    await manager.store_chunks(_chunks(3), "https://example.com/c", metadata={})

    # chunk 0 and chunk 2 were only ever embedded once each.
    all_embedded = [text for call in client.calls for text in call]
    assert all_embedded.count("chunk 0") == 1
    assert all_embedded.count("chunk 2") == 1
    assert len(store.writes) == 3


async def test_all_embeddings_failing_yields_failed_status():
    client = ScriptedEmbeddingClient(fail_texts={"chunk 0", "chunk 1"})
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    result = await manager.store_chunks(_chunks(2), "https://example.com/d", metadata={})

    assert result.status == IngestionStatus.FAILED
    assert result.stored_count == 0
    assert result.failed_count == 2


async def test_vector_store_failure_distinguished_from_embedding_failure():
    """A vector-store write failure produces a partial result with a
    vector-store-specific failure reason, distinct from an embedding failure,
    and the piece is retried (not re-embedded) if unresolved before retry."""
    chunks = _chunks(2)

    # Piece ids are deterministic ("{url_hash}:{generation_id}_p{index}"), so
    # a store that rejects writes whose id encodes index 1 fails only that
    # one piece.
    class FailingStore(RecordingVectorStore):
        async def add_vectors(self, vectors, ids, metadata, collection_name=None):
            self.calls.append(list(ids))
            if any("_p1" in i for i in ids):
                return False
            for vector_id, vector, meta in zip(ids, vectors, metadata):
                self.writes[vector_id] = (vector, meta)
            return True

    failing_store = FailingStore()
    manager2 = ChunkManager(failing_store, ScriptedEmbeddingClient(), recovery_config=_no_delay_config())

    result = await manager2.store_chunks(chunks, "https://example.com/e", metadata={})

    assert result.status == IngestionStatus.PARTIAL
    assert result.stored_count == 1
    assert result.failed_count == 1
    assert any(reason == "vector_store_write_failed" for reason in result.failure_reasons.values())


# ---------------------------------------------------------------------------
# Generation isolation
# ---------------------------------------------------------------------------

async def test_changed_content_creates_a_new_generation_and_retrieval_isolates_it():
    client = ScriptedEmbeddingClient()
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    first = await manager.store_chunks(_chunks(3, prefix="old"), "https://example.com/f", metadata={})
    assert first.status == IngestionStatus.COMPLETE

    second = await manager.store_chunks(_chunks(2, prefix="new"), "https://example.com/f", metadata={})
    assert second.status == IngestionStatus.COMPLETE
    assert second.generation_id != first.generation_id

    # Only the latest generation's pieces are visible via metadata filtering.
    results = await store.search_vectors(query_vector=[0.1, 0.1, 0.1], limit=10,
                                          filter_metadata={"source_url": "https://example.com/f",
                                                            "generation_id": second.generation_id})
    contents = {r["metadata"]["content"] for r in results}
    assert contents == {"new 0", "new 1"}


async def test_retrieve_chunks_filters_to_the_latest_generation():
    client = ScriptedEmbeddingClient()
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    await manager.store_chunks(_chunks(2, prefix="v1"), "https://example.com/g", metadata={})
    await manager.store_chunks(_chunks(2, prefix="v2"), "https://example.com/g", metadata={})

    manager.embedding_client.embed_query = AsyncMock(return_value=[0.1, 0.1, 0.1])
    retrieved = await manager.retrieve_chunks(query="q", source_url="https://example.com/g", top_k=10, min_score=0.0)

    assert {c["content"] for c in retrieved} == {"v2 0", "v2 1"}


# ---------------------------------------------------------------------------
# Cache TTL and explicit invalidation
# ---------------------------------------------------------------------------

async def test_invalidate_cache_clears_ingestion_state_for_retry():
    client = ScriptedEmbeddingClient()
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    await manager.store_chunks(_chunks(2), "https://example.com/h", metadata={})
    assert await manager.has_cached_chunks("https://example.com/h") is True

    await manager.invalidate_cache("https://example.com/h")

    assert await manager.has_cached_chunks("https://example.com/h") is False
    # A fresh call re-embeds from scratch rather than treating it as complete.
    client.calls.clear()
    result = await manager.store_chunks(_chunks(2), "https://example.com/h", metadata={})
    assert result.status == IngestionStatus.COMPLETE
    assert client.calls  # re-embedded, not skipped


# ---------------------------------------------------------------------------
# New manager instance after "restart": no durable retry claimed
# ---------------------------------------------------------------------------

async def test_new_manager_instance_does_not_inherit_prior_partial_state():
    """A new ChunkManager (simulating a process restart) has no memory of a
    prior partial ingestion -- it treats the source as uncached and rebuilds
    idempotently, per the roadmap's explicit no-durable-retry guarantee."""
    client = ScriptedEmbeddingClient(fail_texts={"chunk 1"})
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    first = await manager.store_chunks(_chunks(3), "https://example.com/i", metadata={})
    assert first.status == IngestionStatus.PARTIAL

    fresh_manager = ChunkManager(store, ScriptedEmbeddingClient(), recovery_config=_no_delay_config())
    assert await fresh_manager.has_cached_chunks("https://example.com/i") is False

    second = await fresh_manager.store_chunks(_chunks(3), "https://example.com/i", metadata={})
    assert second.status == IngestionStatus.COMPLETE


async def test_restart_retry_recognizes_already_written_ids_on_add_only_store():
    """A store whose add_vectors rejects (rather than upserts) an id that
    already exists -- the default persistent Chroma adapter's behavior --
    must not report an already-stored piece as a failed write on retry after
    a simulated restart with the same deterministic ids."""
    client = ScriptedEmbeddingClient()
    store = AddOnlyVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    first = await manager.store_chunks(_chunks(2), "https://example.com/j", metadata={})
    assert first.status == IngestionStatus.COMPLETE
    stored_ids = set(store.writes.keys())

    # Simulate a restart: a fresh manager has no cache/pending state, so it
    # re-embeds and retries the same deterministic ids against a store that
    # already has them.
    fresh_manager = ChunkManager(store, ScriptedEmbeddingClient(), recovery_config=_no_delay_config())
    second = await fresh_manager.store_chunks(_chunks(2), "https://example.com/j", metadata={})

    assert second.status == IngestionStatus.COMPLETE
    assert second.failed_count == 0
    assert set(store.writes.keys()) == stored_ids


async def test_invalidate_cache_clears_pending_state_for_every_prior_generation():
    """An older partial generation's pending map must not survive
    invalidation and later report false completion after its confirmed
    pieces are deleted by delete_by_metadata."""
    client = ScriptedEmbeddingClient(fail_texts={"old 1"})
    store = RecordingVectorStore()
    manager = ChunkManager(store, client, recovery_config=_no_delay_config())

    old_partial = await manager.store_chunks(_chunks(3, prefix="old"), "https://example.com/k", metadata={})
    assert old_partial.status == IngestionStatus.PARTIAL
    old_generation_id = old_partial.generation_id

    client.fail_texts.clear()
    new_complete = await manager.store_chunks(_chunks(2, prefix="new"), "https://example.com/k", metadata={})
    assert new_complete.status == IngestionStatus.COMPLETE

    await manager.invalidate_cache("https://example.com/k")

    url_hash = manager._hash_url("https://example.com/k")
    assert f"{url_hash}:{old_generation_id}" not in manager._ingestion_state
    assert f"{url_hash}:{old_generation_id}" not in manager._pending_pieces

    # Re-ingesting the old content must re-embed and re-store everything --
    # not report COMPLETE after storing only the piece that was pending.
    client.calls.clear()
    result = await manager.store_chunks(_chunks(3, prefix="old"), "https://example.com/k", metadata={})

    assert result.status == IngestionStatus.COMPLETE
    assert len(client.calls) == 3
