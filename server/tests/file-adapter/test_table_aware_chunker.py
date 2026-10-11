"""
Tests for TableAwareChunker and table-block detection
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.chunking.table_aware_chunker import (
    TableAwareChunker,
    detect_table_blocks,
    split_preserving_table_blocks,
)

TABLE_MD = (
    "| Name | Age |\n"
    "| --- | --- |\n"
    "| Alice | 30 |\n"
    "| Bob | 25 |"
)

TEXT_WITH_TABLE = f"""Intro paragraph before the table.

{TABLE_MD}

Closing paragraph after the table.
"""

NO_TABLE_TEXT = """
Machine learning is a subset of artificial intelligence. It focuses on teaching
computers to learn from data. Deep learning is a type of machine learning.
"""

TWO_TABLES_TEXT = f"""First table below.

{TABLE_MD}

Some prose in between.

{TABLE_MD}

Done.
"""


def test_detect_table_blocks_finds_single_table():
    spans = detect_table_blocks(TEXT_WITH_TABLE)
    assert len(spans) == 1
    start, end = spans[0]
    assert TEXT_WITH_TABLE[start:end] == TABLE_MD


def test_detect_table_blocks_no_table():
    assert detect_table_blocks(NO_TABLE_TEXT) == []


def test_detect_table_blocks_finds_multiple_tables():
    spans = detect_table_blocks(TWO_TABLES_TEXT)
    assert len(spans) == 2
    for start, end in spans:
        assert TWO_TABLES_TEXT[start:end] == TABLE_MD


def test_detect_table_blocks_ignores_bare_pipe_lines():
    text = "a | b\nc | d\nnot a table, just text with a | pipe\n"
    assert detect_table_blocks(text) == []


def test_detect_table_blocks_ignores_heading_rule_after_pipe_text():
    # "key | value" followed by a bare "---" is a heading/thematic-break rule,
    # not a two-column table separator - the separator carries no delimiters.
    text = "key | value\n---\nmore text\n"
    assert detect_table_blocks(text) == []


def test_detect_table_blocks_ignores_tables_inside_fenced_code_blocks():
    text = f"Some prose.\n\n```\n{TABLE_MD}\n```\n\nMore prose.\n"
    assert detect_table_blocks(text) == []


def test_detect_table_blocks_finds_real_table_outside_fence_with_example_inside():
    text = f"```\n{TABLE_MD}\n```\n\n{TABLE_MD}\n"
    spans = detect_table_blocks(text)
    assert len(spans) == 1
    start, end = spans[0]
    assert text[start:end] == TABLE_MD
    # The matched span must be the real table after the fence, not the one inside it.
    assert start > text.index("```\n") + len(f"```\n{TABLE_MD}\n```")


def test_split_preserving_table_blocks_segments_prose_and_table():
    segments = split_preserving_table_blocks(TEXT_WITH_TABLE)
    is_table_flags = [is_table for is_table, _ in segments]
    assert True in is_table_flags
    table_segment = next(text for is_table, text in segments if is_table)
    assert table_segment == TABLE_MD
    for is_table, text in segments:
        if not is_table:
            assert "|" not in text or TABLE_MD not in text


def test_split_preserving_table_blocks_no_table_returns_whole_text():
    segments = split_preserving_table_blocks(NO_TABLE_TEXT)
    assert segments == [(False, NO_TABLE_TEXT)]


def test_table_aware_chunker_initialization():
    chunker = TableAwareChunker(chunk_size=200, min_characters_per_chunk=10)
    assert chunker.chunk_size == 200
    assert chunker.min_characters_per_chunk == 10


def test_table_aware_chunker_emits_table_as_single_unsplit_chunk():
    chunker = TableAwareChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(TEXT_WITH_TABLE, file_id="file1", metadata={})

    table_chunks = [c for c in chunks if c.metadata.get("is_table_block")]
    assert len(table_chunks) == 1
    assert table_chunks[0].text == TABLE_MD
    assert table_chunks[0].metadata["strategy"] == "table_aware"

    # No row of the table is split across chunks, and the table text is not
    # duplicated into any prose chunk.
    for chunk in chunks:
        if not chunk.metadata.get("is_table_block"):
            assert TABLE_MD not in chunk.text


def test_table_aware_chunker_small_chunk_size_does_not_split_table_rows():
    # chunk_size far smaller than the table's token count - the table must
    # still arrive as one atomic chunk rather than being split mid-row.
    chunker = TableAwareChunker(chunk_size=5, min_characters_per_chunk=5)
    chunks = chunker.chunk_text(TABLE_MD, file_id="file1", metadata={})

    assert len(chunks) == 1
    assert chunks[0].text == TABLE_MD
    assert chunks[0].metadata["is_table_block"] is True


def test_table_aware_chunker_no_table_falls_back_to_prose_chunking():
    chunker = TableAwareChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(NO_TABLE_TEXT, file_id="file1", metadata={})

    assert len(chunks) >= 1
    assert all(not c.metadata.get("is_table_block") for c in chunks)
    assert all(c.metadata.get("strategy") == "table_aware" for c in chunks)
    assert "".join(c.text for c in chunks).strip() != ""


def test_table_aware_chunker_multiple_tables_each_own_chunk():
    chunker = TableAwareChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(TWO_TABLES_TEXT, file_id="file1", metadata={})

    table_chunks = [c for c in chunks if c.metadata.get("is_table_block")]
    assert len(table_chunks) == 2
    for tc in table_chunks:
        assert tc.text == TABLE_MD


def test_table_aware_chunker_preserves_file_metadata():
    chunker = TableAwareChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(TEXT_WITH_TABLE, file_id="file1", metadata={"source": "doc.pdf"})
    assert all(c.metadata.get("source") == "doc.pdf" for c in chunks)
    assert all(c.file_id == "file1" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
