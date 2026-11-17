"""
Tests for RecursiveSentenceChunker
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.chunking.base_chunker import Chunk
from services.file_processing.chunking.recursive_sentence_chunker import RecursiveSentenceChunker


NO_PARAGRAPH_BREAK_TEXT = (
    "Machine learning is a subset of artificial intelligence. "
    "It focuses on teaching computers to learn from data. "
    "Deep learning is a type of machine learning. "
    "It uses neural networks with multiple layers. "
    "These networks can learn complex patterns."
)

# A single sentence (no ". "/"! "/"? " boundaries) too long to fit in one
# chunk, but with comma-separated clauses to fall back on.
LONG_SINGLE_SENTENCE = (
    "This report covers quarterly revenue growth, year-over-year cost reduction, "
    "customer acquisition trends, churn analysis across every region, "
    "and a detailed breakdown of operating expenses by department"
)


def test_recursive_sentence_chunker_initialization():
    chunker = RecursiveSentenceChunker(chunk_size=200, min_characters_per_chunk=10)
    assert chunker.chunk_size == 200
    assert chunker.min_characters_per_chunk == 10


def test_splits_on_sentences_even_without_paragraph_breaks():
    # The default RecursiveChunker only splits at paragraph breaks first;
    # this text has none, so a small chunk_size should still force a split
    # at sentence boundaries rather than falling straight to word-splitting.
    chunker = RecursiveSentenceChunker(chunk_size=80, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(NO_PARAGRAPH_BREAK_TEXT, "file1", {})

    assert len(chunks) > 1
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert chunk.metadata["strategy"] == "recursive_sentence"
        assert chunk.text.strip().endswith(".") or chunk == chunks[-1]


def test_falls_back_to_clause_splitting_for_oversized_single_sentence():
    # Large enough that clause-level splitting alone covers it, without
    # falling further to word-level splitting.
    chunker = RecursiveSentenceChunker(chunk_size=60, min_characters_per_chunk=5)
    chunks = chunker.chunk_text(LONG_SINGLE_SENTENCE, "file1", {})

    assert len(chunks) > 1
    # Clause-level splitting happens on ", "/"; ", so chunk boundaries should
    # land on a comma rather than mid-word, and the text is preserved exactly.
    joined = "".join(c.text for c in chunks)
    assert joined == LONG_SINGLE_SENTENCE
    for chunk in chunks[:-1]:
        assert chunk.text.rstrip().endswith(",")


def test_short_text_single_chunk():
    chunker = RecursiveSentenceChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text("This is a short sentence.", "file1", {})

    assert len(chunks) == 1
    assert chunks[0].text == "This is a short sentence."
    assert chunks[0].metadata["strategy"] == "recursive_sentence"


def test_empty_text_returns_no_chunks():
    chunker = RecursiveSentenceChunker()
    assert chunker.chunk_text("", "file1", {}) == []
    assert chunker.chunk_text("   ", "file1", {}) == []
