"""
Table-Aware Chunker

Detects markdown table blocks in text and keeps them as atomic units instead
of letting the standard paragraph/sentence/word recursion split a table
mid-row. Falls back to the normal recursive chunking for surrounding prose.
"""

import logging
import re
from typing import Any

from .base_chunker import Chunk
from .recursive_chunker import RecursiveChunker, RecursiveRules
from .utils import TokenizerProtocol

logger = logging.getLogger(__name__)

_TABLE_SEPARATOR_RE = re.compile(r'^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$')
_FENCED_CODE_BLOCK_RE = re.compile(r'```.*?```', re.DOTALL)


def _pipe_columns(line: str) -> int:
    """Number of columns implied by a markdown table row's pipe delimiters."""
    stripped = line.strip().removeprefix('|').removesuffix('|')
    return len(stripped.split('|'))


def detect_table_blocks(text: str) -> list[tuple[int, int]]:
    """
    Detect markdown table blocks (header row + separator row + data rows) in
    text via regex, independent of any upstream Docling table-structure data.
    Content inside fenced code blocks is never matched, and a separator row
    must carry the same number of pipe-delimited columns as the header row
    (a bare `---` line under `key | value` is a heading rule, not a table).

    Args:
        text: Markdown (or markdown-flattened) text to scan

    Returns:
        List of (start, end) character offsets, one per detected table block,
        in document order with no overlaps
    """
    if not text:
        return []

    lines = text.splitlines(keepends=True)
    line_starts = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line)

    fenced_ranges = [m.span() for m in _FENCED_CODE_BLOCK_RE.finditer(text)]

    def _in_fence(char_offset: int) -> bool:
        return any(start <= char_offset < end for start, end in fenced_ranges)

    spans = []
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        has_next = i + 1 < n
        if (
            '|' in stripped
            and stripped
            and has_next
            and not _in_fence(line_starts[i])
            and _TABLE_SEPARATOR_RE.fullmatch(lines[i + 1].strip())
            and _pipe_columns(lines[i + 1]) == _pipe_columns(lines[i])
        ):
            start = line_starts[i]
            j = i + 2
            while j < n and '|' in lines[j].strip() and lines[j].strip() and not _in_fence(line_starts[j]):
                j += 1
            last_line_index = j - 1
            end = line_starts[last_line_index] + len(lines[last_line_index].rstrip('\n'))
            spans.append((start, end))
            i = j
        else:
            i += 1

    return spans


def split_preserving_table_blocks(text: str) -> list[tuple[bool, str]]:
    """
    Split text into an ordered list of (is_table, segment_text) pieces, where
    each detected table block is its own segment and everything between/
    around them is kept as separate prose segments.
    """
    spans = detect_table_blocks(text)
    if not spans:
        return [(False, text)]

    segments: list[tuple[bool, str]] = []
    prev_end = 0
    for start, end in spans:
        if start > prev_end:
            segments.append((False, text[prev_end:start]))
        segments.append((True, text[start:end]))
        prev_end = end
    if prev_end < len(text):
        segments.append((False, text[prev_end:]))

    return segments


class TableAwareChunker(RecursiveChunker):
    """
    Recursive chunker that detects markdown table blocks and emits each one
    as a single, unsplit chunk, falling back to the standard paragraph ->
    sentence -> word recursion for surrounding prose.
    """

    def __init__(
        self,
        chunk_size: int = 2048,
        min_characters_per_chunk: int = 24,
        tokenizer: str | TokenizerProtocol | None = None
    ):
        """
        Initialize table-aware chunker.

        Args:
            chunk_size: Maximum chunk size (in tokens if tokenizer provided, else characters)
            min_characters_per_chunk: Minimum characters per chunk
            tokenizer: Optional tokenizer for token-aware chunking
        """
        prose_rules = RecursiveRules.default()
        super().__init__(
            chunk_size=chunk_size,
            min_characters_per_chunk=min_characters_per_chunk,
            rules=prose_rules,
            tokenizer=tokenizer
        )

    def _split_text_to_budget(self, text: str, max_tokens: int) -> list[str]:
        """
        Word-level fallback split guaranteeing every piece fits max_tokens.
        Used only when a table region can't be kept intact by row-group
        splitting alone (a lone row, or a header+separator pair with no
        rows, already exceeds the budget) - markdown table structure is not
        preserved in these pieces, but no piece is left oversized for the
        generic, row-unaware indexing-time splitter to break unpredictably.
        """
        words = text.split()
        if not words:
            return [text]

        pieces: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = current + [word]
            if current and self.count_tokens(' '.join(candidate)) > max_tokens:
                pieces.append(' '.join(current))
                current = [word]
            else:
                current = candidate
        if current:
            pieces.append(' '.join(current))

        return pieces

    def _split_oversized_row(self, header: str, separator: str, row: str) -> list[str]:
        """
        Split a single data row that doesn't fit chunk_size even alone with
        the header/separator. Only the row's own text is fragmented, so each
        piece still carries the header/separator for context.

        If the header+separator pair alone already meets or exceeds
        chunk_size, repeating them in every piece isn't budget-safe either -
        there is no table-structure unit left to preserve, so this falls back
        to a plain word-level split of the whole header+separator+row text,
        guaranteeing every piece still fits the budget instead of leaving one
        oversized chunk for the generic indexing-time splitter to break
        unpredictably.
        """
        overhead = self.count_tokens(f"{header}\n{separator}\n")
        if overhead >= self.chunk_size:
            return self._split_text_to_budget(f"{header}\n{separator}\n{row}", self.chunk_size)

        remaining_budget = self.chunk_size - overhead
        return [
            f"{header}\n{separator}\n{fragment}"
            for fragment in self._split_text_to_budget(row, remaining_budget)
        ]

    def _group_table_rows_to_budget(
        self, header: str, separator: str, data_rows: list[str]
    ) -> list[tuple[str, bool]]:
        """
        Greedily group a table's data rows into pieces that each fit within
        chunk_size, repeating the header and separator in every piece so each
        remains a self-contained, valid markdown table. Never splits a row
        across two row-group pieces; a lone row that still doesn't fit
        chunk_size alongside the header/separator is explicitly fragmented by
        `_split_oversized_row()` instead of being left oversized.

        Returns a list of (piece_text, row_was_fragmented) tuples.
        """
        def _assemble(rows: list[str]) -> str:
            return "\n".join([header, separator, *rows])

        groups: list[tuple[str, bool]] = []
        current_rows: list[str] = []

        for row in data_rows:
            candidate = current_rows + [row]
            if self.count_tokens(_assemble(candidate)) <= self.chunk_size:
                current_rows = candidate
                continue

            if current_rows:
                groups.append((_assemble(current_rows), False))
                current_rows = []

            if self.count_tokens(_assemble([row])) <= self.chunk_size:
                current_rows = [row]
            else:
                groups.extend(
                    (fragment, True) for fragment in self._split_oversized_row(header, separator, row)
                )

        if current_rows:
            groups.append((_assemble(current_rows), False))

        return groups

    def _table_chunks(self, segment_text: str, file_id: str, table_index: int) -> list[Chunk]:
        """
        Build one or more Chunks for a detected table block. A table that
        fits within chunk_size becomes a single chunk; an oversized table is
        pre-split by row-group here so the generic indexing-time budget split
        (which splits on plain text, not rows) never has to touch it. A
        header+separator pair with no data rows (or too few lines to be a
        well-formed table) that is itself oversized falls back to a plain
        word-level budget split.
        """
        token_count = self.count_tokens(segment_text)
        lines = segment_text.splitlines()

        if token_count <= self.chunk_size:
            return [Chunk(
                chunk_id="_pending",
                file_id=file_id,
                text=segment_text,
                chunk_index=0,
                metadata={
                    'level': 0,
                    'token_count': token_count,
                    'strategy': 'table_aware',
                    'is_table_block': True,
                    'content_type': 'table',
                    'table_index': table_index,
                }
            )]

        if len(lines) < 3:
            pieces = self._split_text_to_budget(segment_text, self.chunk_size)
            return [
                Chunk(
                    chunk_id="_pending",
                    file_id=file_id,
                    text=piece,
                    chunk_index=0,
                    metadata={
                        'level': 0,
                        'token_count': self.count_tokens(piece),
                        'strategy': 'table_aware',
                        'is_table_block': True,
                        'content_type': 'table',
                        'table_index': table_index,
                        'row_group_index': row_group_index,
                        'row_group_count': len(pieces),
                        'table_structure_preserved': False,
                    }
                )
                for row_group_index, piece in enumerate(pieces)
            ]

        header, separator, data_rows = lines[0], lines[1], lines[2:]
        row_groups = self._group_table_rows_to_budget(header, separator, data_rows)

        return [
            Chunk(
                chunk_id="_pending",
                file_id=file_id,
                text=group_text,
                chunk_index=0,
                metadata={
                    'level': 0,
                    'token_count': self.count_tokens(group_text),
                    'strategy': 'table_aware',
                    'is_table_block': True,
                    'content_type': 'table',
                    'table_index': table_index,
                    'row_group_index': row_group_index,
                    'row_group_count': len(row_groups),
                    **({'table_structure_preserved': False} if row_fragmented else {}),
                }
            )
            for row_group_index, (group_text, row_fragmented) in enumerate(row_groups)
        ]

    def chunk_text(self, text: str, file_id: str, metadata: dict[str, Any]) -> list[Chunk]:
        """
        Chunk text, keeping any detected markdown table block as one atomic
        chunk (or, if it exceeds chunk_size, as row-group pieces that never
        split a row) and recursively chunking the prose around it.

        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []

        segments = split_preserving_table_blocks(text)

        chunks: list[Chunk] = []
        table_index = 0
        for is_table, segment_text in segments:
            if not segment_text.strip():
                continue
            if is_table:
                chunks.extend(self._table_chunks(segment_text, file_id, table_index))
                table_index += 1
            else:
                chunks.extend(self._recursive_chunk(segment_text, level=0, file_id=file_id))

        for i, chunk in enumerate(chunks):
            chunk.chunk_id = self._generate_chunk_id(file_id, i)
            chunk.chunk_index = i
            chunk.metadata = {**metadata, **chunk.metadata}
            chunk.metadata['strategy'] = 'table_aware'

        logger.debug(f"Created {len(chunks)} chunks using table-aware chunking")
        return chunks
