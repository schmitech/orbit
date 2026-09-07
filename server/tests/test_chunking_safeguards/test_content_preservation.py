"""
Phase 2 gate: content preservation and bounded overlap.

Covers ContentChunker.chunk_markdown source-span coverage, preamble/heading
preservation (fenced-code headings ignored), overlap bounds, and final chunk
IDs/positions/token counts.
"""

import re

import pytest

from utils.content_chunker import ContentChunker
from utils.embedding_budget import resolve_embedding_budget


pytestmark = pytest.mark.unit


def _budget(chunk_target, overlap=0, min_chunk=0):
    return resolve_embedding_budget(
        max_embedding_tokens=chunk_target + overlap + 50,
        chunk_target_tokens=chunk_target,
        overlap_tokens=overlap,
        min_chunk_tokens=min_chunk,
        model=None,  # estimated counting: len(text) // 3
    )


def _reconstruct(content, chunks):
    """Join chunks' non-overlap source spans, collapsing whitespace, and
    compare against the original content with whitespace collapsed too."""
    spans = sorted(c["source_span"] for c in chunks)
    joined = ""
    prev_end = None
    for s, e in spans:
        if prev_end is not None and s > prev_end:
            joined += " "
        joined += content[s:e]
        prev_end = e
    return re.sub(r"\s+", " ", joined).strip()


def _normalize(text):
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Preamble, headings, fenced code
# ---------------------------------------------------------------------------

def test_preamble_before_first_heading_is_preserved():
    content = "Intro paragraph before any heading. " * 10 + "\n\n# Heading\n\n" + ("Body text. " * 10)
    chunker = ContentChunker(budget=_budget(chunk_target=20, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert _reconstruct(content, chunks) == _normalize(content)
    assert any("Intro paragraph" in c["content"] for c in chunks)


def test_no_headings_document_is_preserved():
    content = "Just plain text with no headings at all. " * 20
    chunker = ContentChunker(budget=_budget(chunk_target=15, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert _reconstruct(content, chunks) == _normalize(content)


def test_nested_headings_preserve_hierarchy():
    content = (
        "# Top\n\nTop content here that is reasonably long for testing purposes.\n\n"
        "## Child\n\nChild content here that is reasonably long for testing purposes.\n\n"
        "### Grandchild\n\nGrandchild content here that is reasonably long for testing.\n"
    )
    chunker = ContentChunker(budget=_budget(chunk_target=10, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert _reconstruct(content, chunks) == _normalize(content)
    grandchild_chunk = next(c for c in chunks if c["section"] == "Grandchild")
    assert grandchild_chunk["hierarchy"] == ["Top", "Child", "Grandchild"]


def test_fenced_code_heading_is_not_treated_as_section():
    content = (
        "# Real Heading\n\nSome real content.\n\n"
        "```markdown\n# Not A Real Heading\njust an example in code\n```\n\n"
        "More real content after the code fence, long enough to matter here.\n"
    )
    chunker = ContentChunker(budget=_budget(chunk_target=50, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert all(c["section"] != "Not A Real Heading" for c in chunks)
    assert _reconstruct(content, chunks) == _normalize(content)


def test_table_and_long_unbroken_string_are_preserved():
    table = "| A | B |\n| - | - |\n| 1 | 2 |\n"
    long_string = "x" * 500
    content = f"# Section\n\n{table}\n\n{long_string}\n\nTrailing short content.\n"
    chunker = ContentChunker(budget=_budget(chunk_target=30, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert _reconstruct(content, chunks) == _normalize(content)


def test_unicode_and_punctuation_preserved():
    content = "# Título\n\n" + ("Café naïve façade 你好世界 emoji 🎉 test. " * 15)
    chunker = ContentChunker(budget=_budget(chunk_target=12, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert _reconstruct(content, chunks) == _normalize(content)


# ---------------------------------------------------------------------------
# Overlap bounds
# ---------------------------------------------------------------------------

def test_zero_overlap_produces_no_overlap_fields():
    content = "# A\n\n" + ("word " * 200) + "\n\n# B\n\n" + ("other " * 200)
    chunker = ContentChunker(budget=_budget(chunk_target=30, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert len(chunks) > 1
    for c in chunks:
        assert c["overlap_span"] is None
        assert c["overlap_with_prev"] is False


def test_small_overlap_does_not_duplicate_whole_previous_chunk():
    content = "# A\n\n" + ("alpha " * 300) + "\n\n# B\n\n" + ("beta " * 300)
    chunker = ContentChunker(budget=_budget(chunk_target=40, overlap=5))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert len(chunks) > 1
    for i, c in enumerate(chunks[1:], start=1):
        if c["overlap_span"] is None:
            continue
        prev_span = chunks[i - 1]["source_span"]
        prev_len = prev_span[1] - prev_span[0]
        overlap_len = c["overlap_span"][1] - c["overlap_span"][0]
        # The bug this guards against: `words[-0:]` silently returns the
        # entire previous chunk when the computed overlap size is zero.
        assert overlap_len <= prev_len
        assert chunker.budget.count(c["content"]).count > chunker.budget.count(
            content[chunks[i]["source_span"][0]:chunks[i]["source_span"][1]]
        ).count


def test_overlap_near_maximum_still_fits_budget():
    content = "# A\n\n" + ("token " * 500) + "\n\n# B\n\n" + ("piece " * 500)
    overlap = 18
    chunker = ContentChunker(budget=_budget(chunk_target=20, overlap=overlap))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert len(chunks) > 1
    for c in chunks:
        assert chunker.budget.fits(c["content"])


def test_overlap_with_prev_and_next_flags_are_consistent():
    content = "# A\n\n" + ("word " * 200) + "\n\n# B\n\n" + ("more " * 200) + "\n\n# C\n\n" + ("still " * 200)
    chunker = ContentChunker(budget=_budget(chunk_target=25, overlap=6))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    for i in range(len(chunks) - 1):
        assert chunks[i]["overlap_with_next"] == (chunks[i + 1]["overlap_span"] is not None)


# ---------------------------------------------------------------------------
# Budget compliance and identity
# ---------------------------------------------------------------------------

def test_every_final_chunk_fits_chunk_target_and_embedding_budget():
    content = "# A\n\n" + ("lorem ipsum dolor sit amet " * 100) + "\n\n# B\n\n" + ("consectetur adipiscing elit " * 100)
    chunker = ContentChunker(budget=_budget(chunk_target=30, overlap=8))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    for c in chunks:
        assert chunker.budget.fits(c["content"])


def test_chunk_ids_are_unique_and_positions_describe_final_pieces():
    content = "# A\n\n" + ("word " * 300) + "\n\n# B\n\n" + ("piece " * 300)
    chunker = ContentChunker(budget=_budget(chunk_target=20, overlap=4))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    ids = [c["chunk_id"] for c in chunks]
    assert ids == list(range(len(chunks)))
    positions = [c["position"] for c in chunks]
    assert positions == ids
    for c in chunks:
        assert c["total_chunks"] == len(chunks)


def test_source_spans_are_ordered_and_nonoverlapping():
    content = "# A\n\n" + ("word " * 300) + "\n\n# B\n\n" + ("piece " * 300)
    chunker = ContentChunker(budget=_budget(chunk_target=20, overlap=4))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    spans = [c["source_span"] for c in chunks]
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 <= s2


def test_paragraph_separators_are_not_dropped_from_spans():
    content = "# A\n\n" + ("para one text here. " * 30) + "\n\n" + ("para two text here. " * 30)
    chunker = ContentChunker(budget=_budget(chunk_target=15, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    spans = sorted(c["source_span"] for c in chunks)
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 == s2, "paragraph separators must remain covered, not skipped"

    joined = "".join(content[s:e] for s, e in spans)
    assert joined == content


def test_leading_blank_lines_before_first_heading_are_preserved():
    content = "\n\n\n# Heading\n\n" + ("Body text here. " * 30)
    chunker = ContentChunker(budget=_budget(chunk_target=15, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    spans = sorted(c["source_span"] for c in chunks)
    assert spans[0][0] == 0
    joined = "".join(content[s:e] for s, e in spans)
    assert joined == content


def test_large_whitespace_only_document_is_split_to_budget():
    content = " " * 300
    chunker = ContentChunker(budget=_budget(chunk_target=10, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert len(chunks) > 1
    for c in chunks:
        assert chunker.budget.fits(c["content"])
    spans = sorted(c["source_span"] for c in chunks)
    joined = "".join(content[s:e] for s, e in spans)
    assert joined == content


def test_long_whitespace_separator_not_remerged_over_budget():
    content = "# A\n\nword" + (" " * 300) + "word word " * 30
    chunker = ContentChunker(budget=_budget(chunk_target=10, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert len(chunks) > 1
    for c in chunks:
        assert chunker.budget.fits(c["content"])
    spans = sorted(c["source_span"] for c in chunks)
    joined = "".join(content[s:e] for s, e in spans)
    assert joined == content


def test_unclosed_fence_extends_to_end_of_document():
    content = (
        "# Real Heading\n\nSome real content.\n\n"
        "```markdown\n"
        "# Not A Real Heading, inside an unterminated fence\n"
        "more code-like text with no closing fence\n"
    )
    chunker = ContentChunker(budget=_budget(chunk_target=50, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert all("Not A Real Heading" != c["section"] for c in chunks)
    assert _reconstruct(content, chunks) == _normalize(content)


def test_single_character_over_tiny_budget_raises_instead_of_emitting_invalid_chunk():
    content = "# A\n\n" + "🎉" * 5
    # An exact tokenizer where a single emoji costs more tokens than the budget allows.
    budget = resolve_embedding_budget(
        max_embedding_tokens=10,
        chunk_target_tokens=1,
        overlap_tokens=0,
        model="text-embedding-3-small",
    )
    chunker = ContentChunker(budget=budget)

    with pytest.raises(ValueError):
        chunker.chunk_markdown(content, metadata={"url": "https://example.com"})


def test_trailing_short_content_is_not_dropped():
    content = "# A\n\n" + ("word " * 200) + "\n\n# B\n\nshort tail."
    chunker = ContentChunker(budget=_budget(chunk_target=20, overlap=0))
    chunks = chunker.chunk_markdown(content, metadata={"url": "https://example.com"})

    assert any("short tail." in c["content"] for c in chunks)
    assert _reconstruct(content, chunks) == _normalize(content)
