"""
Recursive Sentence Chunker

Recursive chunking that prioritizes sentence boundaries ahead of paragraphs,
falling back to clause-level splitting (on `,`/`;`) for a single sentence too
long to fit, and finally to words. Distinct from `RecursiveChunker`'s default
rules, which split on paragraphs first.
"""

from typing import Any

from .base_chunker import Chunk
from .recursive_chunker import RecursiveChunker, RecursiveLevel, RecursiveRules
from .utils import TokenizerProtocol


class RecursiveSentenceChunker(RecursiveChunker):
    """
    Recursive chunker that splits on sentence boundaries before falling back
    to clauses and words.
    """

    def __init__(
        self,
        chunk_size: int = 2048,
        min_characters_per_chunk: int = 24,
        tokenizer: str | TokenizerProtocol | None = None
    ):
        """
        Initialize recursive sentence chunker.

        Args:
            chunk_size: Maximum chunk size (in tokens if tokenizer provided, else characters)
            min_characters_per_chunk: Minimum characters per chunk
            tokenizer: Optional tokenizer for token-aware chunking
        """
        rules = RecursiveRules([
            RecursiveLevel(delimiters=[". ", "! ", "? ", "\n"], include_delim="prev"),
            RecursiveLevel(delimiters=[", ", "; "], include_delim="prev"),
            RecursiveLevel(whitespace=True),
        ])
        super().__init__(
            chunk_size=chunk_size,
            min_characters_per_chunk=min_characters_per_chunk,
            rules=rules,
            tokenizer=tokenizer
        )

    def chunk_text(self, text: str, file_id: str, metadata: dict[str, Any]) -> list[Chunk]:
        """
        Chunk text using sentence-first recursive strategy.

        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata

        Returns:
            List of Chunk objects
        """
        chunks = super().chunk_text(text, file_id, metadata)
        for chunk in chunks:
            chunk.metadata['strategy'] = 'recursive_sentence'
        return chunks
