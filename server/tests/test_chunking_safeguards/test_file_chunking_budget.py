"""
Tests for Phase 1b — Extend the shared budget to uploaded-file chunking.

Validates:
1. FileVectorRetriever.index_file_chunks() validates and splits chunks against the
   resolved EmbeddingBudget before calling embedding endpoints.
2. A "character"/no-real-tokenizer configuration reports token counts explicitly
   labeled estimated=True rather than treating character counts as exact tokens.
3. Both token_chunker.py and fixed_chunker.py decode-failure fallbacks use the
   shared estimation convention (1 token ~= 3 characters), and recovered text is
   revalidated at the embedding boundary.
4. TokenChunker rejects tokenizers missing encode/decode methods rather than silently
   treating characters as tokens.
"""

from typing import Any, Optional
from unittest.mock import AsyncMock, Mock
import pytest

from retrievers.implementations.file.file_retriever import FileVectorRetriever
from services.file_processing.chunking.base_chunker import Chunk
from services.file_processing.chunking.fixed_chunker import FixedSizeChunker
from services.file_processing.chunking.token_chunker import TokenChunker
from services.file_processing.chunking.utils import SimpleTokenizer
from utils.embedding_budget import (
    EmbeddingBudget,
    resolve_embedding_budget,
)


class StrictBudgetFakeEmbeddingService:
    """Fake embedding service that fails if any input text exceeds the budget."""

    def __init__(self, budget: EmbeddingBudget, model: Optional[str] = None):
        self.budget = budget
        self.model = model
        self.embedded_texts: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        for text in texts:
            self.embedded_texts.append(text)
            if not self.budget.fits(text):
                pytest.fail(
                    f"Embedding service received document exceeding effective budget "
                    f"({self.budget.count(text).count} tokens > {self.budget.effective_max_tokens}): {text[:50]!r}"
                )
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    async def embed_documents_tracked(self, texts: list[str], usage_sink: dict = None) -> list[list[float]]:
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = sum(self.budget.count(t).count for t in texts)
        return await self.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        self.embedded_texts.append(text)
        if not self.budget.fits(text):
            pytest.fail(
                f"embed_query received document exceeding effective budget "
                f"({self.budget.count(text).count} tokens > {self.budget.effective_max_tokens}): {text[:50]!r}"
            )
        return [0.1, 0.2, 0.3, 0.4]


class FakeVectorStore:
    """Fake vector store recording writes."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def add_vectors(self, vectors, ids, metadata, collection_name, documents=None):
        self.calls.append({
            "vectors": vectors,
            "ids": ids,
            "metadata": metadata,
            "collection_name": collection_name,
            "documents": documents,
        })
        return True


# ============================================================================
# 1. Embedding boundary validation in FileVectorRetriever
# ============================================================================

@pytest.mark.asyncio
async def test_index_file_chunks_splits_oversized_chunk_against_resolved_budget():
    """index_file_chunks() must split any chunk whose text exceeds the resolved budget."""
    budget = resolve_embedding_budget(max_embedding_tokens=50, safety_margin=1.0)
    fake_embeddings = StrictBudgetFakeEmbeddingService(budget=budget)
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 50}})
    retriever.embeddings = fake_embeddings
    retriever._default_store = fake_store
    retriever.initialized = True

    # Paragraph text clearly exceeding 50 tokens (~150 characters for 50 tokens in estimated mode)
    oversized_text = (
        "First section of text that has plenty of details and explanations. "
        "It goes on to discuss several important topics in depth.\n\n"
        "Second section that continues with even more detailed paragraphs, "
        "ensuring that the overall token count is well above the fifty token limit.\n\n"
        "Third section adding more information to guarantee multiple split pieces."
    )

    chunks = [
        Chunk(
            chunk_id="chunk_oversized",
            file_id="file_123",
            text=oversized_text,
            chunk_index=0,
            metadata={"source": "test_doc.txt"},
        )
    ]

    success = await retriever.index_file_chunks(
        file_id="file_123",
        chunks=chunks,
        collection_name="test_collection",
        budget=budget,
    )

    assert success is True
    # The fake embedding service verified all received pieces fit within budget
    assert len(fake_embeddings.embedded_texts) > 1

    # Check that vector store received the split pieces with proper ID and metadata linkage
    assert len(fake_store.calls) == 1
    call = fake_store.calls[0]
    assert len(call["documents"]) == len(fake_embeddings.embedded_texts)
    assert len(call["ids"]) == len(fake_embeddings.embedded_texts)

    # Verify ID re-association: chunk_oversized_split_0, chunk_oversized_split_1, etc.
    for i, cid in enumerate(call["ids"]):
        assert cid == f"chunk_oversized_split_{i}"

    # Verify metadata linkage: parent_chunk_id, parent_chunk_index, split_index, split_count
    for i, meta in enumerate(call["metadata"]):
        assert meta["parent_chunk_id"] == "chunk_oversized"
        assert meta["parent_chunk_index"] == 0
        assert meta["chunk_index"] == i  # Strictly unique and sequential
        assert meta["split_index"] == i
        assert meta["split_count"] == len(call["ids"])
        assert meta["source"] == "test_doc.txt"
        assert meta["token_count"] > 0
        assert meta["token_count_estimated"] is True
        # Issue 4 verification: token_count must be a TokenInt carrying estimated=True
        assert isinstance(meta["token_count"], int)
        assert getattr(meta["token_count"], "estimated", False) is True


@pytest.mark.asyncio
async def test_index_file_chunks_configured_zero_max_tokens_raises_value_error(monkeypatch):
    """Explicitly configured max_embedding_tokens=0 must be honored and raise ValueError, not fall through to 7500."""
    from retrievers.base.abstract_vector_retriever import AbstractVectorRetriever

    fake_embeddings = StrictBudgetFakeEmbeddingService(
        budget=resolve_embedding_budget(max_embedding_tokens=100)
    )
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 0}})
    retriever.embeddings = fake_embeddings
    retriever._default_store = fake_store

    chunk = Chunk(chunk_id="c0", file_id="f0", text="Test content", chunk_index=0, metadata={})

    # In initialize(), avoid real DB connection by mocking super().initialize()
    monkeypatch.setattr(AbstractVectorRetriever, "initialize", AsyncMock())
    with pytest.raises(ValueError, match="max_embedding_tokens must be a positive integer, got 0"):
        await retriever.initialize()

    # And in index_file_chunks(), it rejects and logs the error rather than silently succeeding with 7500
    res = await retriever.index_file_chunks(file_id="f0", chunks=[chunk], collection_name="col")
    assert res is False


@pytest.mark.asyncio
async def test_index_file_chunks_sequential_unique_chunk_index_across_mixed_chunks():
    """Split pieces and non-split chunks must receive strictly unique sequential chunk_index values."""
    budget = resolve_embedding_budget(max_embedding_tokens=30, safety_margin=1.0)
    fake_embeddings = StrictBudgetFakeEmbeddingService(budget=budget)
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 30}})
    retriever.embeddings = fake_embeddings
    retriever._default_store = fake_store
    retriever.initialized = True

    # Chunk 0: small (fits budget of 30 tokens ~= 90 chars)
    chunk0 = Chunk(chunk_id="c0", file_id="f0", text="Short text chunk.", chunk_index=0, metadata={})
    # Chunk 1: oversized (>30 tokens), will be split into at least 2 pieces
    chunk1_text = (
        "Paragraph one with enough content to be oversized when counting tokens against budget.\n\n"
        "Paragraph two with additional words to guarantee it gets split into separate pieces."
    )
    chunk1 = Chunk(chunk_id="c1", file_id="f0", text=chunk1_text, chunk_index=1, metadata={})
    # Chunk 2: small (fits budget)
    chunk2 = Chunk(chunk_id="c2", file_id="f0", text="Trailing short chunk.", chunk_index=2, metadata={})

    success = await retriever.index_file_chunks(
        file_id="f0",
        chunks=[chunk0, chunk1, chunk2],
        collection_name="mixed_col",
        budget=budget,
    )

    assert success is True
    call = fake_store.calls[0]
    out_metas = call["metadata"]
    assert len(out_metas) >= 4

    # Every outgoing chunk must have a strictly unique, sequential chunk_index: [0, 1, 2, 3, ...]
    chunk_indices = [meta["chunk_index"] for meta in out_metas]
    assert chunk_indices == list(range(len(out_metas)))
    assert len(set(chunk_indices)) == len(chunk_indices)  # No duplicates!


@pytest.mark.asyncio
async def test_index_file_chunks_resolves_budget_from_model_clamping():
    """index_file_chunks() resolves budget using model limits when not explicitly passed."""
    # Cohere embed-english-v3.0 has known model limit of 512 tokens
    cohere_model = "embed-english-v3.0"
    expected_budget = resolve_embedding_budget(
        max_embedding_tokens=8000,
        model=cohere_model,
        safety_margin=0.95,
    )

    fake_embeddings = StrictBudgetFakeEmbeddingService(budget=expected_budget, model=cohere_model)
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 8000}})
    retriever.embeddings = fake_embeddings
    retriever._default_store = fake_store
    retriever.initialized = True

    # 600 tokens exceeds 512 * 0.95 = 486 effective max tokens
    text = "word " * 600
    chunk = Chunk(
        chunk_id="chunk_cohere",
        file_id="cohere_file",
        text=text,
        chunk_index=0,
        metadata={},
    )

    success = await retriever.index_file_chunks(
        file_id="cohere_file",
        chunks=[chunk],
        collection_name="cohere_col",
    )

    assert success is True
    # If budget wasn't clamped from model, text would not have been split and fake_embeddings would fail
    assert len(fake_embeddings.embedded_texts) > 1
    for embedded_text in fake_embeddings.embedded_texts:
        assert expected_budget.fits(embedded_text)


@pytest.mark.asyncio
async def test_index_file_chunks_legacy_query_fallback_obeys_budget():
    """index_file_chunks() validates budget even when falling back to embed_query."""
    budget = resolve_embedding_budget(max_embedding_tokens=30, safety_margin=1.0)
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 30}})
    retriever.embeddings = None  # Force embed_query fallback
    retriever._default_store = fake_store
    retriever.embedding_budget = budget

    received_queries = []

    async def mock_embed_query(text: str):
        received_queries.append(text)
        if not budget.fits(text):
            pytest.fail(f"embed_query received text exceeding budget: {text[:50]!r}")
        return [0.1, 0.2]

    retriever.embed_query = mock_embed_query

    oversized_text = "Sentence one with extra words to exceed budget. " * 10
    chunk = Chunk(chunk_id="c1", file_id="f1", text=oversized_text, chunk_index=0, metadata={})

    success = await retriever.index_file_chunks(
        file_id="f1",
        chunks=[chunk],
        collection_name="col",
    )

    assert success is True
    assert len(received_queries) > 1
    for query_text in received_queries:
        assert budget.fits(query_text)


@pytest.mark.asyncio
async def test_index_file_chunks_rejects_empty_or_unsplittable_chunk_with_clear_error(caplog):
    """index_file_chunks() rejects (returns False and logs clear error) when a chunk cannot be split."""
    budget = resolve_embedding_budget(max_embedding_tokens=1, safety_margin=1.0)
    fake_embeddings = StrictBudgetFakeEmbeddingService(budget=budget)
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 1}})
    retriever.embeddings = fake_embeddings
    retriever._default_store = fake_store

    # Whitespace-only chunk cannot produce nonempty piece
    empty_chunk = Chunk(chunk_id="c_empty", file_id="f1", text="    \n   ", chunk_index=0, metadata={})

    success = await retriever.index_file_chunks(
        file_id="f1",
        chunks=[empty_chunk],
        collection_name="col",
        budget=budget,
    )

    assert success is False
    assert "Cannot split empty or whitespace-only text" in caplog.text


# ============================================================================
# 2. Explicit estimated=True token counting on character tokenizer
# ============================================================================

def test_simple_tokenizer_reports_estimated_token_counts():
    """SimpleTokenizer must report counts explicitly labeled as estimated."""
    tokenizer = SimpleTokenizer()
    assert tokenizer.estimated is True

    count = tokenizer.count_tokens("Hello world")
    assert isinstance(count, int)
    assert count == 11
    assert count.estimated is True
    assert count.count == 11

    batch = tokenizer.count_tokens_batch(["Hello", "world!"])
    assert len(batch) == 2
    for c in batch:
        assert isinstance(c, int)
        assert c.estimated is True


def test_token_chunker_character_default_reports_estimated_counts():
    """TokenChunker with default / 'character' tokenizer reports estimated=True in metadata."""
    chunker = TokenChunker(chunk_size=100, overlap=10, tokenizer="character")
    assert chunker.tokenizer.estimated is True

    count = chunker.count_tokens("Hello world")
    assert isinstance(count, int)
    assert count.estimated is True

    chunks = chunker.chunk_text(
        "This is a paragraph of sample text for testing character tokenizer estimation labeling.",
        "file_1",
        {"source": "test.txt"},
    )
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata.get("estimated") is True
        assert chunk.metadata.get("token_count_estimated") is True
        token_count = chunk.metadata["token_count"]
        assert isinstance(token_count, int)
        assert getattr(token_count, "estimated", False) is True


def test_fixed_chunker_token_mode_character_reports_estimated():
    """FixedSizeChunker in token mode with character tokenizer reports estimated=True."""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10, use_tokens=True, tokenizer="character")
    chunks = chunker.chunk_text("Sample text for testing fixed chunker token mode.", "file_1", {})

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata.get("estimated") is True
        assert chunk.metadata.get("token_count_estimated") is True
        assert chunk.metadata["token_count"].estimated is True


# ============================================================================
# 3. Decode-failure fallback uses shared 1:3 convention & caught at boundary
# ============================================================================

def test_token_chunker_decode_failure_uses_shared_estimation_convention():
    """token_chunker.py decode-failure uses shared 1:3 ratio and labels estimated=True."""
    mock_tokenizer = Mock()
    # 20 tokens per slice, chunk_size=20
    mock_tokenizer.encode = Mock(return_value=list(range(20)))
    mock_tokenizer.decode = Mock(side_effect=RuntimeError("Decoder crashed"))
    mock_tokenizer.count_tokens = Mock(return_value=20)
    mock_tokenizer.estimated = False

    chunker = TokenChunker(chunk_size=20, overlap=0)
    chunker._tokenizer = mock_tokenizer

    # 100 character text
    text = "0123456789" * 10
    chunks = chunker.chunk_text(text, "f1", {})

    assert len(chunks) == 1
    # 20 tokens * 3 chars/token = 60 chars (the old convention would have been 20 * 4 = 80 chars)
    assert len(chunks[0].text) == 60
    assert chunks[0].text == text[:60]
    assert chunks[0].metadata["estimated"] is True
    assert chunks[0].metadata["token_count_estimated"] is True


def test_fixed_chunker_decode_failure_uses_shared_estimation_convention():
    """fixed_chunker.py token mode decode-failure uses shared 1:3 ratio and labels estimated=True."""
    mock_tokenizer = Mock()
    mock_tokenizer.encode = Mock(return_value=list(range(20)))
    mock_tokenizer.decode = Mock(side_effect=RuntimeError("Decoder crashed"))
    mock_tokenizer.count_tokens = Mock(return_value=20)
    mock_tokenizer.estimated = False

    chunker = FixedSizeChunker(chunk_size=20, overlap=0, use_tokens=True)
    chunker._tokenizer = mock_tokenizer

    text = "0123456789" * 10
    chunks = chunker.chunk_text(text, "f1", {})

    assert len(chunks) == 1
    # 20 tokens * 3 chars/token = 60 chars (not 80)
    assert len(chunks[0].text) == 60
    assert chunks[0].metadata["estimated"] is True
    assert chunks[0].metadata["token_count_estimated"] is True


@pytest.mark.asyncio
async def test_decode_failure_recovered_text_caught_by_embedding_boundary():
    """Text recovered from decode failure is revalidated and split at index_file_chunks() boundary."""
    # Embedding boundary enforces strict budget of 10 tokens (at 3 chars/token = 30 chars max)
    budget = resolve_embedding_budget(max_embedding_tokens=10, safety_margin=1.0)
    fake_embeddings = StrictBudgetFakeEmbeddingService(budget=budget)
    fake_store = FakeVectorStore()

    retriever = FileVectorRetriever(config={'files': {'max_embedding_tokens': 10}})
    retriever.embeddings = fake_embeddings
    retriever._default_store = fake_store
    retriever.initialized = True

    # Chunker with decode failure recovering 20 tokens * 3 = 60 chars
    mock_tokenizer = Mock()
    mock_tokenizer.encode = Mock(return_value=list(range(20)))
    mock_tokenizer.decode = Mock(side_effect=RuntimeError("Decoder error"))
    mock_tokenizer.count_tokens = Mock(return_value=20)
    mock_tokenizer.estimated = False

    chunker = TokenChunker(chunk_size=20, overlap=0)
    chunker._tokenizer = mock_tokenizer

    # Text has distinct sentences so split_text_to_budget splits cleanly
    text = "First small part here. Second small part here. Third small part here. Fourth small part here."
    recovered_chunks = chunker.chunk_text(text, "f_recovery", {})

    assert len(recovered_chunks) == 1
    # The recovered chunk has 60 chars (~20 tokens), which exceeds the retriever's 10 token budget
    assert len(recovered_chunks[0].text) == 60
    assert not budget.fits(recovered_chunks[0].text)

    # Pass recovered chunk into index_file_chunks()
    success = await retriever.index_file_chunks(
        file_id="f_recovery",
        chunks=recovered_chunks,
        collection_name="recovery_col",
        budget=budget,
    )

    assert success is True
    # The oversized recovered chunk was caught and split before hitting embedding service!
    assert len(fake_embeddings.embedded_texts) > 1
    for piece in fake_embeddings.embedded_texts:
        assert budget.fits(piece)


# ============================================================================
# 4. TokenChunker tokenizer validation
# ============================================================================

def test_token_chunker_rejects_bare_count_tokens_adapter():
    """TokenChunker rejects a tokenizer missing callable encode/decode methods."""
    class BareCounter:
        def count_tokens(self, text: str) -> int:
            return len(text)

    with pytest.raises(TypeError, match="must implement full TokenizerProtocol"):
        TokenChunker(chunk_size=100, tokenizer=BareCounter())


def test_token_chunker_rejects_missing_decode():
    """TokenChunker rejects a tokenizer that has encode but lacks decode."""
    class MissingDecode:
        def encode(self, text: str) -> list[int]:
            return [1, 2, 3]

        def count_tokens(self, text: str) -> int:
            return 3

    with pytest.raises(TypeError, match="must implement full TokenizerProtocol"):
        TokenChunker(chunk_size=100, tokenizer=MissingDecode())


def test_token_chunker_character_mode_slices_via_budget_instead_of_character_slicing():
    """In character default mode, TokenChunker slices via split_text_to_budget."""
    chunker = TokenChunker(chunk_size=20, overlap=0, tokenizer="character")

    text = (
        "Short paragraph one with some meaningful sentences.\n\n"
        "Second paragraph which should be separated into its own piece.\n\n"
        "Third paragraph following after."
    )

    chunks = chunker.chunk_text(text, "f_budget", {})
    assert len(chunks) > 1

    # Pieces are split against the budget, preserving paragraphs where possible
    for chunk in chunks:
        assert chunker.budget.fits(chunk.text)
        assert chunk.metadata["estimated"] is True
        assert chunk.metadata["strategy"] == "token"
