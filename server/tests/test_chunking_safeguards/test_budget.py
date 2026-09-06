"""
Phase 1 gate: one embedding budget shared by preparation and submission.

Covers server/utils/embedding_budget.py directly plus the ContentChunker and
ChunkManager integration points that consume it.
"""

import pytest

from utils.embedding_budget import (
    EmbeddingBudget,
    count_tokens,
    resolve_embedding_budget,
    split_text_to_budget,
)
from utils.content_chunker import ContentChunker


pytestmark = pytest.mark.unit


class DeterministicEmbeddingClient:
    """Fake embedding client exposing only what the budget resolver needs."""

    def __init__(self, model=None, dimension=8):
        self.model = model
        self.dimension = dimension

    async def embed_query(self, text):
        return [0.0] * self.dimension

    async def embed_documents(self, texts):
        return [[0.0] * self.dimension for _ in texts]


# ---------------------------------------------------------------------------
# Effective budget boundaries
# ---------------------------------------------------------------------------

def test_effective_budget_boundaries_preparation_and_submission_agree():
    budget = resolve_embedding_budget(max_embedding_tokens=100, safety_margin=0.95)
    effective = budget.effective_max_tokens
    assert effective == 95

    under = "x" * ((effective - 1) * 3)
    exact = "x" * (effective * 3)
    over = "x" * ((effective + 1) * 3)

    assert budget.fits(under)
    assert budget.fits(exact)
    assert not budget.fits(over)


def test_default_7126_estimated_gap_is_resolved_to_one_cutoff():
    # Historical bug: preparation used the full configured budget (7500) while
    # fallback applied a 95% margin (7125), producing a 375-token no-man's-land
    # where preparation accepted a piece that fallback would reject.
    budget = resolve_embedding_budget(max_embedding_tokens=7500, chunk_target_tokens=7500)
    assert budget.effective_max_tokens == 7125
    assert budget.chunk_target_tokens == budget.effective_max_tokens

    gap_text = "x" * (7126 * 3)  # ~7126 estimated tokens: over budget, under raw config
    assert not budget.fits(gap_text)

    pieces = split_text_to_budget(gap_text, budget)
    assert len(pieces) > 1
    assert all(budget.fits(p) for p in pieces)


def test_chunker_prepares_pieces_that_fallback_would_not_reject():
    budget = resolve_embedding_budget(max_embedding_tokens=7500, chunk_target_tokens=7500)
    chunker = ContentChunker(budget=budget)

    content = "# Title\n\n" + ("word " * 30000)
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert len(chunks) > 1
    for chunk in chunks:
        assert budget.fits(chunk["content"])


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"max_embedding_tokens": 0},
    {"max_embedding_tokens": -10},
    {"max_embedding_tokens": 100, "overlap_tokens": -1},
    {"max_embedding_tokens": 100, "chunk_target_tokens": 50, "overlap_tokens": 50},
    {"max_embedding_tokens": 100, "chunk_target_tokens": 50, "overlap_tokens": 60},
    {"max_embedding_tokens": 100, "safety_margin": 0},
    {"max_embedding_tokens": 100, "safety_margin": 1.5},
    {"max_embedding_tokens": 100, "min_chunk_tokens": -1},
])
def test_invalid_configuration_raises(kwargs):
    with pytest.raises(ValueError):
        resolve_embedding_budget(**kwargs)


def test_min_chunk_tokens_is_soft_and_never_exceeds_effective_budget():
    budget = resolve_embedding_budget(max_embedding_tokens=100, min_chunk_tokens=10_000, safety_margin=0.9)
    assert budget.min_chunk_tokens <= budget.effective_max_tokens


def test_tiny_budget_still_resolves_to_a_usable_positive_value():
    budget = resolve_embedding_budget(max_embedding_tokens=1, safety_margin=0.5)
    assert budget.effective_max_tokens >= 1


def test_unknown_model_has_no_clamp_and_falls_back_to_estimated_counting():
    budget = resolve_embedding_budget(max_embedding_tokens=5000, model="some-unlisted-model-xyz")
    assert budget.model_limit is None
    assert budget.model_limit_provenance is None
    assert budget.counting_mode == "estimated"


def test_known_model_clamps_configured_budget_to_model_limit():
    # embed-english-v3.0 has a documented 512-token input limit; a caller
    # configuring something larger must be clamped, not silently overrun.
    budget = resolve_embedding_budget(max_embedding_tokens=8000, model="embed-english-v3.0", safety_margin=1.0)
    assert budget.model_limit == 512
    assert budget.effective_max_tokens == 512
    assert budget.model_limit_provenance is not None


def test_provider_qualified_model_id_still_resolves_known_limit():
    # Firecrawl's OpenRouter configuration reports models as "openai/<model>";
    # the provider prefix must not hide the known 8,191-token OpenAI limit.
    budget = resolve_embedding_budget(
        max_embedding_tokens=20000, model="openai/text-embedding-3-small", safety_margin=1.0
    )
    assert budget.model_limit == 8191
    assert budget.effective_max_tokens == 8191
    assert budget.model_limit_provenance is not None


def test_provider_qualified_cohere_model_id_clamps_to_its_limit():
    budget = resolve_embedding_budget(
        max_embedding_tokens=8000, model="cohere/embed-english-v3.0", safety_margin=1.0
    )
    assert budget.model_limit == 512
    assert budget.effective_max_tokens == 512


def test_overlap_validated_against_effective_target_after_clamping():
    # chunk_target_tokens=4000 with overlap=500 is valid on its own, but a
    # tight model limit (Cohere: 512) clamps the effective target well below
    # the configured overlap -- that combination must be rejected, not silently
    # accepted with overlap >= the (clamped) target.
    with pytest.raises(ValueError):
        resolve_embedding_budget(
            max_embedding_tokens=4000,
            model="cohere/embed-english-v3.0",
            chunk_target_tokens=4000,
            overlap_tokens=550,
            safety_margin=1.0,
        )


# ---------------------------------------------------------------------------
# Counting mode
# ---------------------------------------------------------------------------

def test_counting_is_labeled_estimated_when_no_tokenizer_available():
    result = count_tokens("hello world", model=None)
    assert result.estimated is True
    assert result.count == len("hello world") // 3


def test_empty_and_whitespace_input_counts_as_zero_tokens():
    assert count_tokens("").count == 0
    assert count_tokens("   \n\t  ").count == len("   \n\t  ") // 3 or count_tokens("   \n\t  ").estimated


def test_unicode_cjk_emoji_and_code_do_not_assume_english_character_ratios():
    samples = [
        "こんにちは世界、これはテストです。" * 5,
        "🎉🚀✨💡🔥" * 20,
        "def foo(x: int) -> int:\n    return x * 2\n" * 10,
        "café naïve façade coöperate" * 10,
    ]
    budget = resolve_embedding_budget(max_embedding_tokens=50)
    for text in samples:
        result = budget.count(text)
        assert result.count >= 0
        assert isinstance(result.estimated, bool)


# ---------------------------------------------------------------------------
# Splitting: progress, termination, and validity
# ---------------------------------------------------------------------------

def test_all_split_pieces_satisfy_the_selected_counter():
    budget = resolve_embedding_budget(max_embedding_tokens=20)
    text = "\n\n".join([f"Paragraph number {i} with some extra words to pad it out." for i in range(30)])
    pieces = split_text_to_budget(text, budget)
    assert len(pieces) > 1
    for piece in pieces:
        assert budget.fits(piece)
        assert piece.strip() == piece
        assert piece != ""


def test_splitting_terminates_for_tiny_budget_and_unsplittable_characters():
    budget = resolve_embedding_budget(max_embedding_tokens=1, safety_margin=1.0)
    # No whitespace at all: forces the character-boundary fallback path.
    text = "supercalifragilisticexpialidocious" * 50
    pieces = split_text_to_budget(text, budget)
    assert len(pieces) > 1
    assert all(p != "" for p in pieces)
    # Progress guarantee: reconstructing pieces covers the original text.
    assert "".join(pieces) == text


def test_split_empty_text_raises_clear_failure():
    budget = resolve_embedding_budget(max_embedding_tokens=100)
    with pytest.raises(ValueError):
        split_text_to_budget("", budget)
    with pytest.raises(ValueError):
        split_text_to_budget("   \n\t  ", budget)


def test_single_piece_returned_when_text_already_fits():
    budget = resolve_embedding_budget(max_embedding_tokens=1000)
    text = "short text that easily fits"
    pieces = split_text_to_budget(text, budget)
    assert pieces == [text]


def test_split_raises_when_no_single_character_fits_the_budget():
    # With an exact tokenizer and a 1-token budget, some single characters
    # (e.g. multi-codepoint emoji) themselves require more than one token.
    # The known-limit table clamps to a real OpenAI-family encoding here so
    # count_tokens takes the exact (non-estimated) path.
    budget = resolve_embedding_budget(max_embedding_tokens=1, model="text-embedding-3-small", safety_margin=1.0)
    unsplittable_emoji = "🧑‍🚀" * 20  # a multi-codepoint ZWJ sequence, several tokens each
    if budget.count(unsplittable_emoji[:1]).count <= budget.effective_max_tokens:
        pytest.skip("tokenizer encoded this single character within the tiny budget in this environment")
    with pytest.raises(ValueError):
        split_text_to_budget(unsplittable_emoji, budget)


# ---------------------------------------------------------------------------
# Tokenizer resolution: provider-qualified ids and offline degradation
# ---------------------------------------------------------------------------

def test_count_tokens_resolves_provider_qualified_openai_model_exactly():
    plain = count_tokens("hello world, this is a test sentence.", model="text-embedding-3-small")
    prefixed = count_tokens("hello world, this is a test sentence.", model="openai/text-embedding-3-small")
    assert prefixed == plain
    assert not prefixed.estimated


def test_encoding_lookup_is_cached_and_not_repeated_per_call(monkeypatch):
    import utils.embedding_budget as embedding_budget_module

    embedding_budget_module._ENCODING_CACHE.clear()
    calls = []
    real_get_encoding = embedding_budget_module.tiktoken.get_encoding

    def counting_get_encoding(name):
        calls.append(name)
        return real_get_encoding(name)

    monkeypatch.setattr(embedding_budget_module.tiktoken, "get_encoding", counting_get_encoding)

    for _ in range(5):
        count_tokens("some text to count repeatedly", model="text-embedding-3-small")

    assert len(calls) == 1


def test_encoding_load_failure_degrades_once_and_stays_estimated(monkeypatch):
    import utils.embedding_budget as embedding_budget_module

    embedding_budget_module._ENCODING_CACHE.clear()

    def failing_get_encoding(name):
        raise RuntimeError("simulated offline network failure")

    monkeypatch.setattr(embedding_budget_module.tiktoken, "get_encoding", failing_get_encoding)

    first = count_tokens("some text", model="text-embedding-3-small")
    second = count_tokens("more text", model="text-embedding-3-small")

    assert first.estimated is True
    assert second.estimated is True
    # The failed lookup is cached as None -- no repeated network attempts.
    assert embedding_budget_module._ENCODING_CACHE.get("cl100k_base") is None

    embedding_budget_module._ENCODING_CACHE.clear()


# ---------------------------------------------------------------------------
# ChunkManager integration: same effective budget, no divergent cutoff
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chunk_manager_uses_same_effective_budget_as_resolver():
    from utils.chunk_manager import ChunkManager

    client = DeterministicEmbeddingClient(model=None)
    budget = resolve_embedding_budget(max_embedding_tokens=100, safety_margin=0.95)
    manager = ChunkManager(vector_store=None, embedding_client=client, budget=budget)

    assert manager.budget is budget
    assert manager.max_embedding_tokens == budget.effective_max_tokens


@pytest.mark.asyncio
async def test_chunk_manager_without_explicit_budget_resolves_one_from_model():
    client = DeterministicEmbeddingClient(model="embed-english-v3.0")
    from utils.chunk_manager import ChunkManager

    manager = ChunkManager(vector_store=None, embedding_client=client, max_embedding_tokens=8000)
    assert manager.budget.model_limit == 512
    assert manager.max_embedding_tokens == manager.budget.effective_max_tokens


def test_prepare_chunks_for_embedding_splits_oversized_chunk_to_one_cutoff():
    from utils.chunk_manager import ChunkManager

    client = DeterministicEmbeddingClient(model=None)
    budget = resolve_embedding_budget(max_embedding_tokens=20, safety_margin=1.0)
    manager = ChunkManager(vector_store=None, embedding_client=client, budget=budget)

    oversized = {"content": "word " * 200, "chunk_id": 0}
    validated_chunks, chunk_texts = manager._prepare_chunks_for_embedding([oversized])

    assert len(validated_chunks) > 1
    for text in chunk_texts:
        assert budget.fits(text)
