"""
Tests for Context-Enriched Chunking Metadata

Verifies the add_context_metadata() post-processing pass that enriches
chunks from any strategy with neighbor-context snippets and basic stats.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.chunking.base_chunker import Chunk
from services.file_processing.chunking.utils import add_context_metadata


def _make_chunks(texts):
    return [
        Chunk(chunk_id=f"c{i}", file_id="f1", text=text, chunk_index=i)
        for i, text in enumerate(texts)
    ]


def test_middle_chunk_gets_both_neighbors():
    chunks = _make_chunks(["first chunk text", "middle chunk text", "last chunk text"])
    add_context_metadata(chunks)

    assert chunks[1].metadata['preceding_context'] == "first chunk text"
    assert chunks[1].metadata['following_context'] == "last chunk text"


def test_first_chunk_has_no_preceding_context():
    chunks = _make_chunks(["first chunk text", "second chunk text"])
    add_context_metadata(chunks)

    assert chunks[0].metadata['preceding_context'] == ""
    assert chunks[0].metadata['following_context'] == "second chunk text"


def test_last_chunk_has_no_following_context():
    chunks = _make_chunks(["first chunk text", "second chunk text"])
    add_context_metadata(chunks)

    assert chunks[-1].metadata['following_context'] == ""
    assert chunks[-1].metadata['preceding_context'] == "first chunk text"


def test_single_chunk_has_no_neighbors():
    chunks = _make_chunks(["only chunk text"])
    add_context_metadata(chunks)

    assert chunks[0].metadata['preceding_context'] == ""
    assert chunks[0].metadata['following_context'] == ""


def test_word_and_char_counts():
    chunks = _make_chunks(["one two three"])
    add_context_metadata(chunks)

    assert chunks[0].metadata['word_count'] == 3
    assert chunks[0].metadata['char_count'] == len("one two three")


def test_snippet_truncated_to_snippet_chars():
    long_text = "x" * 500
    chunks = _make_chunks([long_text, "short"])
    add_context_metadata(chunks, snippet_chars=50)

    assert chunks[1].metadata['preceding_context'] == "x" * 50


def test_metadata_values_are_non_null_flat_scalars():
    chunks = _make_chunks(["a", "b", "c"])
    add_context_metadata(chunks)

    for chunk in chunks:
        for value in chunk.metadata.values():
            assert value is not None
            assert isinstance(value, (str, int, float, bool))
