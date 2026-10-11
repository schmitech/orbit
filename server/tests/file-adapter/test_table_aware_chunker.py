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
    assert table_chunks[0].metadata["content_type"] == "table"
    assert table_chunks[0].metadata["table_index"] == 0

    # No row of the table is split across chunks, and the table text is not
    # duplicated into any prose chunk.
    for chunk in chunks:
        if not chunk.metadata.get("is_table_block"):
            assert TABLE_MD not in chunk.text


def test_table_aware_chunker_small_chunk_size_splits_by_row_group_not_mid_row():
    # chunk_size smaller than the table's token count, but large enough to
    # hold the header/separator plus one full row - the table must be split
    # into row-group pieces (header+separator repeated in each), never
    # mid-row, instead of the generic text-based budget split.
    chunker = TableAwareChunker(chunk_size=45, min_characters_per_chunk=5)
    chunks = chunker.chunk_text(TABLE_MD, file_id="file1", metadata={})

    header, separator = TABLE_MD.splitlines()[:2]
    data_rows = TABLE_MD.splitlines()[2:]

    assert len(chunks) > 1
    seen_rows: list[str] = []
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["is_table_block"] is True
        assert chunk.metadata["content_type"] == "table"
        assert chunk.metadata["table_index"] == 0
        assert chunk.metadata["row_group_index"] == i
        assert chunk.metadata["row_group_count"] == len(chunks)
        lines = chunk.text.splitlines()
        assert lines[0] == header
        assert lines[1] == separator
        seen_rows.extend(lines[2:])

    # Every original data row appears exactly once, in order, across pieces -
    # no row dropped, duplicated, or split across two pieces.
    assert seen_rows == data_rows


def test_table_aware_chunker_small_table_gets_single_chunk_with_table_metadata():
    chunker = TableAwareChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(TABLE_MD, file_id="file1", metadata={})

    assert len(chunks) == 1
    assert chunks[0].text == TABLE_MD
    assert chunks[0].metadata["is_table_block"] is True
    assert chunks[0].metadata["content_type"] == "table"
    assert chunks[0].metadata["table_index"] == 0
    assert "row_group_index" not in chunks[0].metadata
    assert "row_group_count" not in chunks[0].metadata


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
        assert tc.metadata["content_type"] == "table"
    assert [tc.metadata["table_index"] for tc in table_chunks] == [0, 1]


def test_table_aware_chunker_oversized_row_is_fragmented_within_budget():
    # A single data row (with header+separator) that alone exceeds chunk_size
    # must still be split into budget-fitting pieces, rather than being
    # emitted as one oversized chunk for the generic indexing-time splitter
    # to break unpredictably.
    header = "| Name | Notes |"
    separator = "| --- | --- |"
    row = "| Alice | " + " ".join(f"note{i}" for i in range(40)) + " |"
    table_text = f"{header}\n{separator}\n{row}"

    chunk_size = 60
    chunker = TableAwareChunker(chunk_size=chunk_size, min_characters_per_chunk=5)
    chunks = chunker.chunk_text(table_text, file_id="file1", metadata={})

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.metadata["content_type"] == "table"
        assert chunk.metadata["table_structure_preserved"] is False
        # The critical guarantee: every emitted piece fits the budget, so
        # nothing oversized reaches the generic, row-unaware budget splitter.
        assert chunker.count_tokens(chunk.text) <= chunk_size
        assert chunk.text.startswith(f"{header}\n{separator}\n")


def test_table_aware_chunker_oversized_row_with_oversized_header_falls_back_to_budget():
    # Regression: when the header+separator pair alone already meets or
    # exceeds chunk_size, repeating them alongside a row fragment is not
    # budget-safe either - _split_oversized_row() must fall back to a plain
    # word-level split of the whole header+separator+row text rather than
    # emitting one oversized chunk that reaches the generic, row-unaware
    # indexing-time splitter.
    header = "| " + " | ".join(f"Column{i}" for i in range(15)) + " |"
    separator = "| " + " | ".join(["---"] * 15) + " |"
    row = "| " + " | ".join(f"value{i}" for i in range(15)) + " |"
    table_text = f"{header}\n{separator}\n{row}"

    chunk_size = 30
    chunker = TableAwareChunker(chunk_size=chunk_size, min_characters_per_chunk=5)

    # Sanity-check this reproduces the reported shape: header+separator alone
    # already exceeds chunk_size, and the whole table is far larger still.
    assert chunker.count_tokens(f"{header}\n{separator}\n") > chunk_size
    assert chunker.count_tokens(table_text) > chunk_size

    chunks = chunker.chunk_text(table_text, file_id="file1", metadata={})

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.metadata["content_type"] == "table"
        assert chunk.metadata["table_structure_preserved"] is False
        # The critical guarantee: no piece reaches the generic indexing-time
        # splitter oversized, even when header+separator alone don't fit.
        assert chunker.count_tokens(chunk.text) <= chunk_size


def test_table_aware_chunker_header_separator_only_oversized_table_falls_back():
    # A table with no data rows (just header+separator) that is itself
    # oversized has no row to preserve - it must fall back to a plain,
    # budget-safe split instead of being left as one oversized chunk.
    header = "| " + " | ".join(f"Column{i}" for i in range(20)) + " |"
    separator = "| " + " | ".join(["---"] * 20) + " |"
    table_text = f"{header}\n{separator}"

    chunk_size = 20
    chunker = TableAwareChunker(chunk_size=chunk_size, min_characters_per_chunk=5)
    chunks = chunker.chunk_text(table_text, file_id="file1", metadata={})

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.metadata["content_type"] == "table"
        assert chunk.metadata["table_structure_preserved"] is False
        assert chunker.count_tokens(chunk.text) <= chunk_size


def test_table_aware_chunker_preserves_file_metadata():
    chunker = TableAwareChunker(chunk_size=2048, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(TEXT_WITH_TABLE, file_id="file1", metadata={"source": "doc.pdf"})
    assert all(c.metadata.get("source") == "doc.pdf" for c in chunks)
    assert all(c.file_id == "file1" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
