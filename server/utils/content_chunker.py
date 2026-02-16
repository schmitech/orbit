"""
Content chunking utilities for handling large web content.

This module provides intelligent content chunking for large documents (especially markdown)
to prevent exceeding LLM context limits and improve retrieval performance.

SPECIALIZATION:
This chunker is specialized for markdown web content from Firecrawl/web scraping.
It parses hierarchical markdown structure (headers) and chunks by sections.

For general file chunking (PDF, DOCX, TXT), see:
    server/services/file_processing/chunking/
    - FixedSizeChunker: Character-based chunking
    - SemanticChunker: Sentence-based chunking

KEY DIFFERENCES:
    File Chunking               vs    Web Content Chunking
    --------------                    --------------------
    Character-based                   Token-based
    Flat structure                    Hierarchical (H1-H6)
    Sentence/paragraph aware          Section/heading aware
    Returns Chunk objects             Returns dictionaries
    For uploaded files                For scraped web content
"""

import re
import hashlib
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MarkdownSection:
    """Represents a hierarchical section in a markdown document."""

    def __init__(self, level: int, title: str, content: str, start_pos: int = 0):
        self.level = level  # Header level (1-6)
        self.title = title
        self.content = content  # Content including the header
        self.start_pos = start_pos
        self.children: List[MarkdownSection] = []
        self.parent: Optional[MarkdownSection] = None

    def get_hierarchy_path(self) -> List[str]:
        """Get the hierarchical path from root to this section."""
        path = []
        current = self
        while current:
            if current.title:
                path.insert(0, current.title)
            current = current.parent
        return path

    def estimate_tokens(self) -> int:
        """Estimate token count (conservative: 1 token ≈ 3 chars to account for special tokens)."""
        return len(self.content) // 3


class ContentChunker:
    """
    Intelligent content chunker for markdown documents.

    Features:
    - Semantic chunking based on markdown structure
    - Preserves hierarchy and context
    - Configurable chunk sizes with overlap
    - Token estimation
    """

    def __init__(self,
                 max_chunk_tokens: int = 4000,
                 chunk_overlap_tokens: int = 200,
                 min_chunk_tokens: int = 500):
        """
        Initialize the content chunker.

        Args:
            max_chunk_tokens: Maximum tokens per chunk (default: 4000)
            chunk_overlap_tokens: Overlap between chunks (default: 200)
            min_chunk_tokens: Minimum tokens for a chunk (default: 500)
        """
        self.max_chunk_tokens = max_chunk_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens
        self.min_chunk_tokens = min_chunk_tokens

        # Regex pattern to match markdown headers
        self.header_pattern = re.compile(r'^(#{1,6})\s+(.+?)$', re.MULTILINE)

    def should_chunk(self, content: str) -> bool:
        """
        Determine if content should be chunked based on size.

        Args:
            content: The markdown content

        Returns:
            True if content should be chunked
        """
        estimated_tokens = len(content) // 3
        return estimated_tokens > self.max_chunk_tokens

    def chunk_markdown(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunk markdown content into semantic sections.

        Args:
            content: Markdown content to chunk
            metadata: Metadata about the source document

        Returns:
            List of chunk dictionaries with content and metadata
        """
        if not content:
            return []

        # Check if chunking is needed
        if not self.should_chunk(content):
            return [{
                "chunk_id": 0,
                "total_chunks": 1,
                "content": content,
                "section": metadata.get('title', 'Full Document'),
                "hierarchy": [metadata.get('title', 'Document')],
                "position": 0,
                "token_count": len(content) // 3,
                "overlap_with_prev": False,
                "overlap_with_next": False,
                "source_url": metadata.get('url', ''),
                "source_hash": self._hash_content(content)
            }]

        # Parse markdown structure
        sections = self._parse_markdown_structure(content)

        # Create chunks from sections
        chunks = self._create_chunks_from_sections(sections, metadata)

        # Add overlap between chunks
        chunks = self._add_chunk_overlap(chunks)

        # Add chunk metadata
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            chunk.update({
                "chunk_id": i,
                "total_chunks": total_chunks,
                "position": i,
                "source_url": metadata.get('url', ''),
                "source_hash": self._hash_content(content)
            })

        logger.info(f"Chunked content into {total_chunks} chunks (original: {len(content)//3} tokens)")

        return chunks

    def _parse_markdown_structure(self, content: str) -> List[MarkdownSection]:
        """
        Parse markdown content into hierarchical sections.

        Args:
            content: Markdown content

        Returns:
            List of top-level MarkdownSection objects
        """
        sections = []
        current_section = None
        section_stack = []  # Stack to track section hierarchy

        # Split content by headers
        last_end = 0

        for match in self.header_pattern.finditer(content):
            # Add content before this header
            if match.start() > last_end:
                if current_section:
                    current_section.content += content[last_end:match.start()]

            # Create new section for this header
            level = len(match.group(1))
            title = match.group(2).strip()
            start_pos = match.start()

            # Content starts with the header itself
            section_content = content[match.start():match.end()] + '\n'

            new_section = MarkdownSection(level, title, section_content, start_pos)

            # Handle hierarchy
            # Pop sections from stack that are at same or deeper level
            while section_stack and section_stack[-1].level >= level:
                section_stack.pop()

            # If stack is not empty, current section is a child
            if section_stack:
                parent = section_stack[-1]
                new_section.parent = parent
                parent.children.append(new_section)
            else:
                # Top-level section
                sections.append(new_section)

            section_stack.append(new_section)
            current_section = new_section
            last_end = match.end() + 1

        # Add remaining content to the last section
        if current_section and last_end < len(content):
            current_section.content += content[last_end:]

        # If no headers found, create a single section
        if not sections:
            sections.append(MarkdownSection(
                level=1,
                title="Document",
                content=content,
                start_pos=0
            ))

        return sections

    def _create_chunks_from_sections(self,
                                    sections: List[MarkdownSection],
                                    metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create chunks from parsed sections, respecting token limits.

        Args:
            sections: List of parsed markdown sections
            metadata: Source document metadata

        Returns:
            List of chunk dictionaries
        """
        chunks = []
        current_chunk = ""
        current_sections = []
        current_tokens = 0

        # Flatten sections into a list (depth-first traversal)
        flat_sections = self._flatten_sections(sections)

        for section in flat_sections:
            section_tokens = section.estimate_tokens()

            # If single section exceeds max, split it
            if section_tokens > self.max_chunk_tokens:
                # First, flush current chunk if any
                if current_chunk:
                    chunks.append(self._create_chunk_dict(
                        current_chunk, current_sections, current_tokens
                    ))
                    current_chunk = ""
                    current_sections = []
                    current_tokens = 0

                # Split large section into smaller chunks
                sub_chunks = self._split_large_section(section)
                chunks.extend(sub_chunks)
                continue

            # If adding this section would exceed limit, start new chunk
            if current_tokens + section_tokens > self.max_chunk_tokens:
                if current_chunk:
                    chunks.append(self._create_chunk_dict(
                        current_chunk, current_sections, current_tokens
                    ))

                # Start new chunk with this section
                current_chunk = section.content
                current_sections = [section]
                current_tokens = section_tokens
            else:
                # Add section to current chunk
                current_chunk += "\n" + section.content
                current_sections.append(section)
                current_tokens += section_tokens

        # Add final chunk
        if current_chunk:
            chunks.append(self._create_chunk_dict(
                current_chunk, current_sections, current_tokens
            ))

        return chunks

    def _flatten_sections(self, sections: List[MarkdownSection]) -> List[MarkdownSection]:
        """Flatten hierarchical sections into a list (depth-first)."""
        flat = []
        for section in sections:
            flat.append(section)
            if section.children:
                flat.extend(self._flatten_sections(section.children))
        return flat

    def _split_large_section(self, section: MarkdownSection) -> List[Dict[str, Any]]:
        """
        Split a large section that exceeds max chunk size into smaller chunks.

        Args:
            section: MarkdownSection that's too large

        Returns:
            List of chunk dictionaries
        """
        chunks = []
        content = section.content
        hierarchy = section.get_hierarchy_path()

        # Split by paragraphs (double newline)
        paragraphs = re.split(r'\n\s*\n', content)

        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(para) // 3

            if current_tokens + para_tokens > self.max_chunk_tokens:
                if current_chunk:
                    chunks.append({
                        "content": current_chunk.strip(),
                        "section": section.title,
                        "hierarchy": hierarchy,
                        "token_count": current_tokens,
                        "overlap_with_prev": False,
                        "overlap_with_next": False
                    })

                current_chunk = para
                current_tokens = para_tokens
            else:
                current_chunk += "\n\n" + para if current_chunk else para
                current_tokens += para_tokens

        # Add final chunk
        if current_chunk:
            chunks.append({
                "content": current_chunk.strip(),
                "section": section.title,
                "hierarchy": hierarchy,
                "token_count": current_tokens,
                "overlap_with_prev": False,
                "overlap_with_next": False
            })

        return chunks

    def _create_chunk_dict(self,
                          content: str,
                          sections: List[MarkdownSection],
                          token_count: int) -> Dict[str, Any]:
        """Create a chunk dictionary from content and sections."""
        # Get section title (first section in the chunk)
        section_title = sections[0].title if sections else "Content"

        # Get hierarchy (from first section)
        hierarchy = sections[0].get_hierarchy_path() if sections else ["Document"]

        return {
            "content": content.strip(),
            "section": section_title,
            "hierarchy": hierarchy,
            "token_count": token_count,
            "overlap_with_prev": False,
            "overlap_with_next": False
        }

    def _add_chunk_overlap(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add overlap between consecutive chunks.

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Updated chunks with overlap added
        """
        if len(chunks) <= 1 or self.chunk_overlap_tokens == 0:
            return chunks

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            current_chunk = chunks[i]

            # Get last N tokens from previous chunk
            prev_content = prev_chunk["content"]
            prev_words = prev_content.split()

            # Approximate: take last ~overlap_tokens worth of words
            overlap_word_count = self.chunk_overlap_tokens // 3  # Conservative estimate
            overlap_content = " ".join(prev_words[-overlap_word_count:])

            # Prepend to current chunk
            current_chunk["content"] = overlap_content + "\n\n" + current_chunk["content"]
            current_chunk["overlap_with_prev"] = True
            prev_chunk["overlap_with_next"] = True

        return chunks

    def _hash_content(self, content: str) -> str:
        """Generate a hash for content deduplication."""
        return hashlib.md5(content.encode()).hexdigest()


class ChunkCache:
    """
    Simple in-memory cache for content chunks.

    Used to avoid re-chunking the same content multiple times in a session.
    For production, this could be replaced with Redis or vector store caching.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.cache: Dict[str, List[Dict[str, Any]]] = {}
        self.access_order: List[str] = []

    def get(self, content_hash: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached chunks by content hash."""
        if content_hash in self.cache:
            # Update access order (LRU)
            self.access_order.remove(content_hash)
            self.access_order.append(content_hash)
            return self.cache[content_hash]
        return None

    def put(self, content_hash: str, chunks: List[Dict[str, Any]]):
        """Store chunks in cache."""
        # Evict oldest if cache is full
        if len(self.cache) >= self.max_size and content_hash not in self.cache:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]

        self.cache[content_hash] = chunks
        if content_hash not in self.access_order:
            self.access_order.append(content_hash)

    def clear(self):
        """Clear the cache."""
        self.cache.clear()
        self.access_order.clear()
