"""
Recursive Chunker

Recursively splits text using hierarchical rules (paragraphs → sentences → words).
Handles complex document structures better than simple chunking.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Literal
from dataclasses import dataclass

from .base_chunker import TextChunker, Chunk
from .utils import split_sentences, TokenizerProtocol, get_tokenizer

logger = logging.getLogger(__name__)


@dataclass
class RecursiveLevel:
    """
    Defines a level in the recursive chunking hierarchy.
    
    Attributes:
        delimiters: List of delimiters to split on (e.g., ["\n\n"] for paragraphs)
        include_delim: Whether to include delimiter in chunk ("prev", "next", or None)
        whitespace: If True, split on whitespace instead of delimiters
    """
    delimiters: Optional[List[str]] = None
    include_delim: Optional[Literal["prev", "next"]] = "prev"
    whitespace: bool = False


class RecursiveRules:
    """
    Defines recursive chunking rules with hierarchical levels.
    
    Example:
        rules = RecursiveRules([
            RecursiveLevel(delimiters=["\n\n"], include_delim="prev"),  # Paragraphs
            RecursiveLevel(delimiters=[". ", "! ", "? "], include_delim="prev"),  # Sentences
            RecursiveLevel(whitespace=True),  # Words
        ])
    """
    
    def __init__(self, levels: Optional[List[RecursiveLevel]] = None):
        """
        Initialize recursive rules.
        
        Args:
            levels: List of RecursiveLevel objects defining chunking hierarchy.
                If None, uses default: paragraphs → sentences → words
        """
        if levels is None:
            # Default: paragraphs → sentences → words
            levels = [
                RecursiveLevel(delimiters=["\n\n", "\n\n\n"], include_delim="prev"),
                RecursiveLevel(delimiters=[". ", "! ", "? ", "\n"], include_delim="prev"),
                RecursiveLevel(whitespace=True),
            ]
        self.levels = levels
    
    def __len__(self) -> int:
        """Return number of levels."""
        return len(self.levels)
    
    def __getitem__(self, index: int) -> RecursiveLevel:
        """Get level by index."""
        return self.levels[index]
    
    @classmethod
    def default(cls) -> "RecursiveRules":
        """Create default recursive rules."""
        return cls()


class RecursiveChunker(TextChunker):
    """
    Recursive chunking strategy.
    
    Splits text recursively using hierarchical rules:
    - First level: paragraphs (double newlines)
    - Second level: sentences (periods, exclamation marks, etc.)
    - Third level: words (whitespace)
    
    Handles complex document structures better than simple chunking.
    """
    
    def __init__(
        self,
        chunk_size: int = 2048,
        min_characters_per_chunk: int = 24,
        rules: Optional[RecursiveRules] = None,
        tokenizer: Optional[Union[str, TokenizerProtocol]] = None
    ):
        """
        Initialize recursive chunker.
        
        Args:
            chunk_size: Maximum chunk size (in tokens if tokenizer provided, else characters)
            min_characters_per_chunk: Minimum characters per chunk
            rules: RecursiveRules object defining chunking hierarchy.
                If None, uses default: paragraphs → sentences → words
            tokenizer: Optional tokenizer for token-aware chunking.
                If None, uses character-based chunking.
        """
        super().__init__(tokenizer=tokenizer)
        
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if min_characters_per_chunk <= 0:
            raise ValueError("min_characters_per_chunk must be greater than 0")
        
        self.chunk_size = chunk_size
        self.min_characters_per_chunk = min_characters_per_chunk
        self.rules = rules if rules is not None else RecursiveRules.default()
    
    def _split_text(self, text: str, level: RecursiveLevel) -> List[str]:
        """
        Split text using the given recursive level.

        Args:
            text: Text to split
            level: RecursiveLevel defining how to split

        Returns:
            List of text segments
        """
        if level.whitespace:
            # Split on whitespace
            splits = text.split()
            # Estimate words per chunk based on token size
            # Average ~1.3 tokens per word, so divide chunk_size by 1.3
            words_per_chunk = max(1, int(self.chunk_size / 1.3))
            # Rejoin with spaces for proper reconstruction
            return [' '.join(splits[i:i+words_per_chunk]) for i in range(0, len(splits), words_per_chunk)]

        if level.delimiters:
            # Use improved sentence splitting for delimiters
            return split_sentences(
                text,
                delimiters=level.delimiters,
                include_delim=level.include_delim,
                min_characters_per_sentence=self.min_characters_per_chunk
            )
        
        # Fallback: split by tokenizer if available
        try:
            tokens = self.tokenizer.encode(text)
            token_splits = [
                tokens[i:i + self.chunk_size]
                for i in range(0, len(tokens), self.chunk_size)
            ]
            return [self.tokenizer.decode(split) for split in token_splits]
        except Exception:
            # Final fallback: character-based split
            return [text[i:i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]
    
    def _merge_splits(self, splits: List[str], token_counts: List[int]) -> List[str]:
        """
        Merge short splits into larger chunks respecting chunk_size.

        Args:
            splits: List of text splits
            token_counts: List of token counts for each split

        Returns:
            List of merged chunks
        """
        if not splits or not token_counts:
            return []

        if len(splits) != len(token_counts):
            raise ValueError(f"Number of splits {len(splits)} does not match token counts {len(token_counts)}")

        # If all splits are larger than chunk_size, return as-is
        if all(count > self.chunk_size for count in token_counts):
            return splits

        merged = []
        current_chunk = []
        current_token_count = 0

        for split, token_count in zip(splits, token_counts):
            if current_token_count + token_count <= self.chunk_size:
                # Add to current chunk
                current_chunk.append(split)
                current_token_count += token_count
            else:
                # Finalize current chunk
                if current_chunk:
                    # Join with empty string since delimiters are already included
                    # in the splits (from include_delim="prev" in split_sentences)
                    merged.append(''.join(current_chunk))

                # Start new chunk
                current_chunk = [split]
                current_token_count = token_count

        # Add remaining chunk
        if current_chunk:
            merged.append(''.join(current_chunk))

        return merged
    
    def _recursive_chunk(
        self,
        text: str,
        level: int = 0,
        start_offset: int = 0
    ) -> List[Chunk]:
        """
        Recursively chunk text.
        
        Args:
            text: Text to chunk
            level: Current recursion level
            start_offset: Starting offset in original text
            
        Returns:
            List of Chunk objects
        """
        if not text:
            return []
        
        # If we've exhausted all levels, return as single chunk
        if level >= len(self.rules):
            token_count = self.count_tokens(text)
            return [Chunk(
                chunk_id=f"chunk_{start_offset}",
                file_id="",  # Will be set by caller
                text=text,
                chunk_index=0,  # Will be set by caller
                metadata={
                    'level': level,
                    'token_count': token_count,
                    'strategy': 'recursive',
                }
            )]
        
        # Get current rule
        curr_rule = self.rules[level]
        
        # Split text at current level
        splits = self._split_text(text, curr_rule)
        
        if not splits:
            return []
        
        # Calculate token counts for splits
        token_counts = [self.count_tokens(split) for split in splits]
        
        # Merge splits that are too small
        if curr_rule.whitespace:
            merged = self._merge_splits(splits, token_counts)
        else:
            merged = self._merge_splits(splits, token_counts)
        
        # Chunk long merged splits recursively
        chunks = []
        current_offset = start_offset
        
        for merged_text in merged:
            token_count = self.count_tokens(merged_text)
            
            if token_count > self.chunk_size:
                # Recursively chunk this split
                recursive_chunks = self._recursive_chunk(
                    merged_text,
                    level + 1,
                    current_offset
                )
                chunks.extend(recursive_chunks)
            else:
                # Create chunk from merged text
                chunks.append(Chunk(
                    chunk_id=f"chunk_{current_offset}",
                    file_id="",  # Will be set by caller
                    text=merged_text,
                    chunk_index=0,  # Will be set by caller
                    metadata={
                        'level': level,
                        'token_count': token_count,
                        'strategy': 'recursive',
                    }
                ))
            
            # Update offset
            current_offset += len(merged_text)
        
        return chunks
    
    def chunk_text(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text using recursive strategy.
        
        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata
            
        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []
        
        logger.debug(f"Starting recursive chunking for text of length {len(text)}")
        
        # Recursively chunk text
        chunks = self._recursive_chunk(text, level=0, start_offset=0)
        
        # Update chunks with file_id and proper indices
        for i, chunk in enumerate(chunks):
            chunk.chunk_id = self._generate_chunk_id(file_id, i)
            chunk.file_id = file_id
            chunk.chunk_index = i
            chunk.metadata.update(metadata)
        
        logger.info(f"Created {len(chunks)} chunks using recursive chunking")
        return chunks

