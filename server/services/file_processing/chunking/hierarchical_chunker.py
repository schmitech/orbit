"""
Hierarchical Chunker

Chunks text at two levels: coarse "parent" chunks (e.g. sections) and fine
"leaf" chunks (e.g. sentences) nested inside each parent. Only leaves are
meant to be embedded/searched; parents carry their own text in
`db_metadata['text']` so retrieval can expand a leaf hit with its parent's
context. See docs/roadmap/chunking/hierarchical-chunking.md for the full
design and the reasoning behind the id/metadata handling below.
"""

from typing import Any

from .base_chunker import Chunk, TextChunker
from .recursive_chunker import RecursiveChunker
from .recursive_sentence_chunker import RecursiveSentenceChunker
from .utils import TokenizerProtocol


class HierarchicalChunker(TextChunker):
    """
    Two-level hierarchical chunking strategy: parent chunks (coarse) each
    containing leaf chunks (fine). Parents are chunked from the whole
    document; leaves are chunked independently from each parent's own text.
    """

    def __init__(
        self,
        parent_chunk_size: int = 4096,
        leaf_chunk_size: int = 512,
        min_characters_per_chunk: int = 24,
        tokenizer: str | TokenizerProtocol | None = None
    ):
        """
        Initialize hierarchical chunker.

        Args:
            parent_chunk_size: Max size of a parent chunk (tokens if tokenizer provided, else characters)
            leaf_chunk_size: Max size of a leaf chunk
            min_characters_per_chunk: Minimum characters per chunk, for both levels
            tokenizer: Optional tokenizer for token-aware chunking
        """
        super().__init__(tokenizer=tokenizer)
        self._parent_chunker = RecursiveChunker(
            chunk_size=parent_chunk_size,
            min_characters_per_chunk=min_characters_per_chunk,
            tokenizer=tokenizer
        )
        self._leaf_chunker = RecursiveSentenceChunker(
            chunk_size=leaf_chunk_size,
            min_characters_per_chunk=min_characters_per_chunk,
            tokenizer=tokenizer
        )

    def chunk_text(self, text: str, file_id: str, metadata: dict[str, Any]) -> list[Chunk]:
        """
        Chunk text into parent chunks, each with its own leaf chunks.

        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata

        Returns:
            Flat list of Chunk objects: all parents first (document order),
            then all leaves (document order, grouped by parent).
        """
        if not text or not text.strip():
            return []

        parents = self._parent_chunker.chunk_text(text, file_id, metadata)
        for parent in parents:
            parent.metadata = {**parent.metadata, 'level': 'parent'}
            parent.db_metadata = {'text': parent.text}

        leaves: list[Chunk] = []
        for parent in parents:
            parent_leaves = self._leaf_chunker.chunk_text(parent.text, file_id, metadata)
            for leaf in parent_leaves:
                leaf.metadata = {**leaf.metadata, 'level': 'leaf'}
                leaf.db_metadata = {'hierarchy_parent_id': parent.chunk_id}
            leaves.extend(parent_leaves)

        num_parents = len(parents)
        for i, leaf in enumerate(leaves):
            leaf.chunk_index = num_parents + i
            leaf.chunk_id = self._generate_chunk_id(file_id, leaf.chunk_index)

        return parents + leaves
