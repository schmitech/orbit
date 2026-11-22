"""
Hierarchical Chunker

Chunks text at two or more levels: one or more coarse "parent" levels (e.g.
sections, subsections) narrowing down to a fine "leaf" level (e.g.
sentences). Only leaves are meant to be embedded/searched; every parent
level carries its own text in `db_metadata['text']` (plus a link to its own
parent's chunk_id, for every parent level but the top) so retrieval can
expand a leaf hit with its immediate parent's context. See
docs/roadmap/complete/hierarchical-chunking.md for the full design and the
reasoning behind the id/metadata handling below.
"""

from itertools import pairwise
from typing import Any

from .base_chunker import Chunk, TextChunker
from .recursive_chunker import RecursiveChunker
from .recursive_sentence_chunker import RecursiveSentenceChunker
from .utils import TokenizerProtocol


class HierarchicalChunker(TextChunker):
    """
    N-level hierarchical chunking strategy: one or more parent levels
    (coarse-to-finer), each containing the next level's chunks, narrowing
    down to a leaf level (finest). Each level is chunked independently from
    its own parent's text (the whole document for the top level).
    """

    def __init__(
        self,
        parent_chunk_size: int = 4096,
        leaf_chunk_size: int = 512,
        min_characters_per_chunk: int = 24,
        tokenizer: str | TokenizerProtocol | None = None,
        intermediate_chunk_sizes: list[int] | None = None,
    ):
        """
        Initialize hierarchical chunker.

        Args:
            parent_chunk_size: Max size of the top parent level (tokens if tokenizer provided, else characters)
            leaf_chunk_size: Max size of a leaf chunk
            min_characters_per_chunk: Minimum characters per chunk, for every level
            tokenizer: Optional tokenizer for token-aware chunking
            intermediate_chunk_sizes: Optional max sizes for additional parent
                levels strictly between the top parent and the leaf level,
                ordered coarsest to finest (e.g. a 4096/1024/512 three-level
                hierarchy passes parent_chunk_size=4096,
                intermediate_chunk_sizes=[1024], leaf_chunk_size=512). Each
                size must be no larger than the previous level's; omit for
                the default two-level hierarchy.
        """
        super().__init__(tokenizer=tokenizer)

        intermediate_chunk_sizes = intermediate_chunk_sizes or []
        level_sizes = [parent_chunk_size, *intermediate_chunk_sizes]
        for prev_size, size in pairwise(level_sizes):
            if size > prev_size:
                raise ValueError(
                    "intermediate_chunk_sizes must be non-increasing from parent_chunk_size: "
                    f"{size} > {prev_size}"
                )
        if intermediate_chunk_sizes and intermediate_chunk_sizes[-1] < leaf_chunk_size:
            raise ValueError(
                "intermediate_chunk_sizes' last size must be >= leaf_chunk_size: "
                f"{intermediate_chunk_sizes[-1]} < {leaf_chunk_size}"
            )

        # Every level but the leaf splits on paragraphs-first (RecursiveChunker);
        # the leaf level splits on sentences-first (RecursiveSentenceChunker) -
        # matching the original two-level hierarchy's chunker choice per level.
        self._parent_chunkers = [
            RecursiveChunker(
                chunk_size=size,
                min_characters_per_chunk=min_characters_per_chunk,
                tokenizer=tokenizer
            )
            for size in level_sizes
        ]
        self._leaf_chunker = RecursiveSentenceChunker(
            chunk_size=leaf_chunk_size,
            min_characters_per_chunk=min_characters_per_chunk,
            tokenizer=tokenizer
        )

    @classmethod
    def from_config(
        cls,
        chunk_size: int,
        overlap: int,
        tokenizer: str | TokenizerProtocol | None,
        options: dict[str, Any],
    ) -> "HierarchicalChunker":
        """
        Build from the chunker-construction options _init_chunker assembles.

        `overlap` is accepted for signature uniformity with other chunkers'
        from_config, but unused here - HierarchicalChunker has no overlap
        parameter. `parent_chunk_size`/`leaf_chunk_size` default relative to
        `chunk_size` (4x and 1x respectively) unless overridden in options.
        """
        return cls(
            parent_chunk_size=options.get('parent_chunk_size', chunk_size * 4),
            leaf_chunk_size=options.get('leaf_chunk_size', chunk_size),
            min_characters_per_chunk=options.get('min_characters_per_chunk', 24),
            tokenizer=tokenizer,
            intermediate_chunk_sizes=options.get('intermediate_chunk_sizes'),
        )

    def chunk_text(self, text: str, file_id: str, metadata: dict[str, Any]) -> list[Chunk]:
        """
        Chunk text into one or more nested parent levels, narrowing down to leaves.

        Returns:
            Flat list of Chunk objects, in level order (top parents first,
            leaves last), each level in document order. Ids/indices are
            globally unique and sequential across the whole list.
        """
        if not text or not text.strip():
            return []

        # Top parent level: chunked from the whole document in a single call,
        # so the inner chunker's own final re-indexing pass already gives it
        # globally unique, sequential ids - no re-indexing needed here.
        top_level = self._parent_chunkers[0].chunk_text(text, file_id, metadata)
        for chunk in top_level:
            chunk.metadata = {**chunk.metadata, 'level': 'parent'}
            chunk.db_metadata = {'text': chunk.text}

        all_chunks = list(top_level)
        current_level = top_level
        next_index = len(all_chunks)

        # Each subsequent level is chunked per-parent (locally indexed, so it
        # must be globally re-indexed before being used as a parent for the
        # next level - see contract #1 in the roadmap doc) until the leaf level.
        remaining_parent_chunkers = self._parent_chunkers[1:]
        for level_chunker in remaining_parent_chunkers:
            current_level = self._chunk_next_level(
                current_level, level_chunker, file_id, metadata, is_leaf=False
            )
            for i, chunk in enumerate(current_level):
                chunk.chunk_index = next_index + i
                chunk.chunk_id = self._generate_chunk_id(file_id, chunk.chunk_index)
            next_index += len(current_level)
            all_chunks.extend(current_level)

        leaves = self._chunk_next_level(current_level, self._leaf_chunker, file_id, metadata, is_leaf=True)
        for i, leaf in enumerate(leaves):
            leaf.chunk_index = next_index + i
            leaf.chunk_id = self._generate_chunk_id(file_id, leaf.chunk_index)
        all_chunks.extend(leaves)

        return all_chunks

    @staticmethod
    def _chunk_next_level(
        parents: list[Chunk],
        chunker: TextChunker,
        file_id: str,
        metadata: dict[str, Any],
        is_leaf: bool,
    ) -> list[Chunk]:
        """Chunk each parent's own text slice into the next level's children."""
        children: list[Chunk] = []
        for parent in parents:
            parent_children = chunker.chunk_text(parent.text, file_id, metadata)
            for child in parent_children:
                if is_leaf:
                    child.metadata = {**child.metadata, 'level': 'leaf'}
                    child.db_metadata = {'hierarchy_parent_id': parent.chunk_id}
                else:
                    child.metadata = {**child.metadata, 'level': 'parent'}
                    child.db_metadata = {'text': child.text, 'hierarchy_parent_id': parent.chunk_id}
            children.extend(parent_children)
        return children
