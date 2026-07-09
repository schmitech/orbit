"""
Tests for MarkdownHeaderChunker
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.chunking.base_chunker import Chunk
from services.file_processing.chunking.markdown_header_chunker import MarkdownHeaderChunker
from services.file_processing.chunking.recursive_chunker import RecursiveChunker


MARKDOWN_TEXT = """# Title

Intro paragraph before any section.

## Section One

This is the content of section one. It has a couple of sentences to work with.

## Section Two

This is the content of section two, which is a different topic entirely.
"""

NO_HEADER_TEXT = """
Machine learning is a subset of artificial intelligence. It focuses on teaching
computers to learn from data. Deep learning is a type of machine learning.
It uses neural networks with multiple layers. These networks can learn complex patterns.
"""


def test_markdown_header_chunker_initialization():
    chunker = MarkdownHeaderChunker(chunk_size=200, min_characters_per_chunk=10)
    assert chunker.chunk_size == 200
    assert chunker.min_characters_per_chunk == 10


def test_markdown_header_chunker_keeps_headers_with_sections():
    chunker = MarkdownHeaderChunker(chunk_size=100, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(MARKDOWN_TEXT, "file1", {})

    assert len(chunks) >= 1
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert chunk.metadata["strategy"] == "markdown_header"

    # Each header-led chunk should carry section_header/header_level metadata
    header_chunks = [c for c in chunks if "section_header" in c.metadata]
    assert any(c.metadata["section_header"] == "Section One" for c in header_chunks)
    assert any(c.metadata["section_header"] == "Section Two" for c in header_chunks)

    # No chunk should contain text from both "Section One" and "Section Two"
    for chunk in chunks:
        assert not ("section one" in chunk.text.lower() and "section two" in chunk.text.lower())


def test_markdown_header_chunker_oversized_section_falls_back_to_recursive():
    # Small chunk_size forces the header-level split to recurse into
    # paragraph/sentence/word splitting, same as RecursiveChunker would.
    chunker = MarkdownHeaderChunker(chunk_size=20, min_characters_per_chunk=5)
    chunks = chunker.chunk_text(MARKDOWN_TEXT, "file1", {})

    assert len(chunks) > 3
    for chunk in chunks:
        assert chunk.metadata["strategy"] == "markdown_header"


def test_markdown_header_chunker_continuation_chunks_keep_section_metadata():
    # chunk_size=80 forces "## Section One" and its body into separate chunks
    # since header+body together exceed the limit; the body chunk must still
    # carry the section_header/header_level of the section it belongs to.
    chunker = MarkdownHeaderChunker(chunk_size=80, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(MARKDOWN_TEXT, "file1", {})

    section_one_chunks = [c for c in chunks if "section one" in c.text.lower()]
    assert len(section_one_chunks) >= 2
    for chunk in section_one_chunks:
        assert chunk.metadata["section_header"] == "Section One"
        assert chunk.metadata["header_level"] == 2

    section_two_chunks = [c for c in chunks if "section two" in c.text.lower()]
    assert len(section_two_chunks) >= 2
    for chunk in section_two_chunks:
        assert chunk.metadata["section_header"] == "Section Two"
        assert chunk.metadata["header_level"] == 2


def test_markdown_header_chunker_no_headers_matches_recursive_chunker():
    md_chunker = MarkdownHeaderChunker(chunk_size=100, min_characters_per_chunk=24)
    recursive_chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=24)

    md_chunks = md_chunker.chunk_text(NO_HEADER_TEXT, "file1", {})
    recursive_chunks = recursive_chunker.chunk_text(NO_HEADER_TEXT, "file1", {})

    assert [c.text for c in md_chunks] == [c.text for c in recursive_chunks]
    for chunk in md_chunks:
        assert "section_header" not in chunk.metadata


def test_markdown_header_chunker_empty_text():
    chunker = MarkdownHeaderChunker(chunk_size=100, min_characters_per_chunk=24)
    chunks = chunker.chunk_text("", "file1", {})
    assert chunks == []
