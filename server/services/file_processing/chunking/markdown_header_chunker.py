"""
Markdown Header Chunker

Recursive chunking with a markdown-header level ahead of paragraphs, so each
chunk stays attached to the header of the section it belongs to. Falls back to
the standard paragraph -> sentence -> word recursion for oversized sections or
header-less text.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Union

from .base_chunker import Chunk
from .recursive_chunker import RecursiveChunker, RecursiveRules, RecursiveLevel
from .utils import TokenizerProtocol

logger = logging.getLogger(__name__)

_HEADER_PATTERN = r'(?m)^#{1,6}\s'
_HEADER_LINE_PATTERN = re.compile(r'^(#{1,6})\s+(.*)$', re.MULTILINE)


class MarkdownHeaderChunker(RecursiveChunker):
    """
    Recursive chunker that splits on markdown headers (H1-H6) before falling
    back to paragraphs, sentences, and words.
    """

    def __init__(
        self,
        chunk_size: int = 2048,
        min_characters_per_chunk: int = 24,
        tokenizer: Optional[Union[str, TokenizerProtocol]] = None
    ):
        """
        Initialize markdown header chunker.

        Args:
            chunk_size: Maximum chunk size (in tokens if tokenizer provided, else characters)
            min_characters_per_chunk: Minimum characters per chunk
            tokenizer: Optional tokenizer for token-aware chunking
        """
        rules = RecursiveRules([
            RecursiveLevel(regex=_HEADER_PATTERN, include_delim="next"),
            RecursiveLevel(delimiters=["\n\n", "\n\n\n"], include_delim="prev"),
            RecursiveLevel(delimiters=[". ", "! ", "? ", "\n"], include_delim="prev"),
            RecursiveLevel(whitespace=True),
        ])
        super().__init__(
            chunk_size=chunk_size,
            min_characters_per_chunk=min_characters_per_chunk,
            rules=rules,
            tokenizer=tokenizer
        )

    def chunk_text(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text using markdown-header-aware recursive strategy.

        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata

        Returns:
            List of Chunk objects
        """
        chunks = super().chunk_text(text, file_id, metadata)

        # Chunks are emitted in document order, so a header's metadata is
        # carried forward to the continuation chunks produced when its
        # section falls back to paragraph/sentence/word recursion for being
        # oversized - otherwise those chunks would lose their section.
        current_header = None
        current_header_level = None

        for chunk in chunks:
            chunk.metadata['strategy'] = 'markdown_header'
            header_match = _HEADER_LINE_PATTERN.match(chunk.text.lstrip())
            if header_match:
                current_header_level = len(header_match.group(1))
                current_header = header_match.group(2).strip()

            if current_header is not None:
                chunk.metadata['header_level'] = current_header_level
                chunk.metadata['section_header'] = current_header

        return chunks
