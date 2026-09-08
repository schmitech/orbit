"""
Phase 6 (scaled down): an offline integration smoke test through the full
Firecrawl chunking pipeline -- ContentChunker -> ChunkManager (embedding
recovery + ingestion state) -> retrieval -> IntentFirecrawlRetriever
formatting -- using fakes, no network/credentials/real delays.

This is not the full benchmarked/instrumented Phase 6 originally scoped;
see the roadmap's Phase 6 completion note for what was scaled down and why.
"""

import pytest
from retrievers.implementations.intent.intent_firecrawl_retriever import IntentFirecrawlRetriever
from utils.chunk_manager import ChunkManager, IngestionStatus
from utils.content_chunker import ContentChunker
from utils.embedding_budget import resolve_embedding_budget
from utils.embedding_recovery import RecoveryConfig

pytestmark = pytest.mark.unit


def _wikipedia_like_markdown() -> str:
    sections = []
    for i in range(20):
        sections.append(
            f"## Section {i}\n\n"
            + ("This is a sentence about the industrial revolution. " * 40)
        )
    return "# Industrial Revolution\n\nAn introductory paragraph before any heading.\n\n" + "\n\n".join(sections)


class FakeEmbeddingClient:
    """Deterministic embedding client: fails a scripted set of texts once,
    then succeeds -- exercises the recovery path without real network/delay."""

    def __init__(self, fail_once_texts=None):
        self.fail_once_texts = set(fail_once_texts or [])
        self._already_failed = set()
        self.batch_size = 1

    async def embed_documents_tracked(self, texts, usage_sink=None):
        vectors = []
        for text in texts:
            if text in self.fail_once_texts and text not in self._already_failed:
                self._already_failed.add(text)
                raise _TransientError()
            # A cheap deterministic "embedding": length-based, so unrelated
            # texts don't collide, without needing a real model.
            vectors.append([float(len(text) % 97), float(hash(text) % 101)])
        if usage_sink is not None:
            usage_sink.update({
                "prompt_tokens": sum(len(t) for t in texts), "completion_tokens": 0,
                "total_tokens": sum(len(t) for t in texts), "provider": "fake",
                "model": "fake-embed", "reported": True,
            })
        return vectors

    async def embed_query(self, text):
        return [float(len(text) % 97), float(hash(text) % 101)]


class _TransientError(Exception):
    def __init__(self):
        super().__init__("temporarily unavailable")
        self.status_code = 503


class FakeVectorStore:
    """Minimal in-memory vector store: cosine-free nearest match by a fixed
    similarity so ranking is deterministic for the test."""

    def __init__(self):
        self.writes = {}

    async def add_vectors(self, vectors, ids, metadata, collection_name=None):
        for vector_id, vector, meta in zip(ids, vectors, metadata):
            self.writes[vector_id] = (vector, meta)
        return True

    async def search_vectors(self, query_vector, limit=10, collection_name=None, filter_metadata=None):
        results = []
        for vector_id, (vector, meta) in self.writes.items():
            if filter_metadata and any(meta.get(k) != v for k, v in filter_metadata.items()):
                continue
            # Deterministic pseudo-similarity: closer position -> higher score.
            score = 1.0 / (1.0 + abs(vector[0] - query_vector[0]))
            results.append({"id": vector_id, "score": score, "metadata": meta})
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    async def get_vector(self, vector_id, collection_name=None):
        if vector_id not in self.writes:
            return None
        vector, meta = self.writes[vector_id]
        return {"id": vector_id, "vector": vector, "metadata": meta}


async def test_full_pipeline_chunk_embed_store_retrieve_format():
    """Happy path end to end: chunking preserves source coverage, every
    submitted piece fits the shared budget, ingestion completes, retrieval
    returns ranked results, and formatting stays within the context budget."""
    budget = resolve_embedding_budget(
        max_embedding_tokens=300, model=None, chunk_target_tokens=150, overlap_tokens=20,
    )
    markdown = _wikipedia_like_markdown()
    chunker = ContentChunker(budget=budget)
    chunks = chunker.chunk_markdown(markdown, {"title": "Industrial Revolution", "url": "https://example.com/ir"})

    assert len(chunks) > 1
    for chunk in chunks:
        assert budget.fits(chunk["content"])

    # Source spans, taken in order, reconstruct the original content exactly
    # (Phase 2's content-preservation guarantee).
    reconstructed = "".join(markdown[start:end] for start, end in (c["source_span"] for c in chunks))
    assert reconstructed == markdown

    client = FakeEmbeddingClient()
    store = FakeVectorStore()
    manager = ChunkManager(
        store, client, budget=budget,
        recovery_config=RecoveryConfig(max_attempts=len(chunks) + 5, deadline_seconds=5.0, base_delay=0.0, max_delay=0.0),
    )

    result = await manager.store_chunks(chunks, "https://example.com/ir", {"title": "Industrial Revolution"})
    assert result.status == IngestionStatus.COMPLETE
    assert result.stored_count == result.expected_count

    relevant = await manager.retrieve_chunks(
        query="industrial revolution", source_url="https://example.com/ir", top_k=3, min_score=0.0,
    )
    assert relevant

    retriever = object.__new__(IntentFirecrawlRetriever)
    retriever.max_retrieval_context_tokens = 300
    retriever.retrieval_context_budget = resolve_embedding_budget(max_embedding_tokens=300, safety_margin=1.0)
    formatted = retriever._format_chunked_results(
        chunks=relevant, source_url="https://example.com/ir", page_metadata={"title": "Industrial Revolution"},
        total_content_size=len(markdown), ingestion_status=result.status,
    )
    assert retriever.retrieval_context_budget.count(formatted).count <= retriever.retrieval_context_budget.effective_max_tokens
    assert "RELEVANT SECTION" in formatted


async def test_pipeline_recovers_a_transient_batch_failure_then_completes():
    """One piece fails transiently on the first attempt; the shared recovery
    budget retries it and ingestion still reaches COMPLETE, not PARTIAL."""
    budget = resolve_embedding_budget(max_embedding_tokens=300, chunk_target_tokens=150, overlap_tokens=20)
    markdown = _wikipedia_like_markdown()
    chunker = ContentChunker(budget=budget)
    chunks = chunker.chunk_markdown(markdown, {"title": "Doc", "url": "https://example.com/transient"})

    flaky_text = chunks[len(chunks) // 2]["content"]
    client = FakeEmbeddingClient(fail_once_texts={flaky_text})
    store = FakeVectorStore()
    manager = ChunkManager(
        store, client, budget=budget,
        recovery_config=RecoveryConfig(max_attempts=len(chunks) + 5, deadline_seconds=5.0, base_delay=0.0, max_delay=0.0),
    )

    result = await manager.store_chunks(chunks, "https://example.com/transient", {})

    assert result.status == IngestionStatus.COMPLETE


async def test_pipeline_falls_back_to_bounded_excerpt_when_all_embeddings_fail():
    """Every embedding call fails permanently -- ingestion is FAILED, and the
    retriever's raw-content fallback still returns a bounded, non-empty
    result rather than an unbounded dump or an unhandled error."""
    class AlwaysFailingClient:
        batch_size = 1

        async def embed_documents_tracked(self, texts, usage_sink=None):
            raise _TransientError()

    budget = resolve_embedding_budget(max_embedding_tokens=300, chunk_target_tokens=150, overlap_tokens=20)
    markdown = _wikipedia_like_markdown()
    chunker = ContentChunker(budget=budget)
    chunks = chunker.chunk_markdown(markdown, {"title": "Doc", "url": "https://example.com/all-fail"})

    manager = ChunkManager(
        FakeVectorStore(), AlwaysFailingClient(), budget=budget,
        recovery_config=RecoveryConfig(max_attempts=3, deadline_seconds=2.0, base_delay=0.0, max_delay=0.0),
    )

    result = await manager.store_chunks(chunks, "https://example.com/all-fail", {})
    assert result.status == IngestionStatus.FAILED
    assert result.stored_count == 0

    retriever = object.__new__(IntentFirecrawlRetriever)
    retriever.max_retrieval_context_tokens = 300
    retriever.retrieval_context_budget = resolve_embedding_budget(max_embedding_tokens=300, safety_margin=1.0)
    fallback = retriever._format_firecrawl_results(
        [{"url": "https://example.com/all-fail", "success": True, "markdown": markdown}], template={},
    )

    assert retriever.retrieval_context_budget.count(fallback).count <= retriever.retrieval_context_budget.effective_max_tokens
    assert fallback.strip()
