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

    def chunk_text(self, text: str, file_id: str, metadata: dict[str, Any]) -> list[Chunk]:
        """
        Chunk text, keeping any detected markdown table block as one atomic
        chunk and recursively chunking the prose around it.

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
        for is_table, segment_text in segments:
            if not segment_text.strip():
                continue
            if is_table:
                token_count = self.count_tokens(segment_text)
                chunks.append(Chunk(
                    chunk_id="_pending",
                    file_id=file_id,
                    text=segment_text,
                    chunk_index=0,
                    metadata={
                        'level': 0,
                        'token_count': token_count,
                        'strategy': 'table_aware',
                        'is_table_block': True,
                    }
                ))
            else:
                chunks.extend(self._recursive_chunk(segment_text, level=0, file_id=file_id))

        for i, chunk in enumerate(chunks):
            chunk.chunk_id = self._generate_chunk_id(file_id, i)
            chunk.chunk_index = i
            chunk.metadata = {**metadata, **chunk.metadata}
            chunk.metadata['strategy'] = 'table_aware'

        logger.debug(f"Created {len(chunks)} chunks using table-aware chunking")
        return chunks
