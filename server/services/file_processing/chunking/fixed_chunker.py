"""
Fixed Size Chunker

Simple fixed-size chunking with configurable overlap.
Supports both character-based and token-based chunking.
"""

import logging
from typing import Dict, Any, List, Optional, Union

from .base_chunker import TextChunker, Chunk
from .utils import TokenizerProtocol

logger = logging.getLogger(__name__)


class FixedSizeChunker(TextChunker):
    """
    Fixed-size chunking strategy.
    
    Splits text into chunks of fixed size with configurable overlap.
    Supports both character-based (default) and token-based chunking.
    Simple and fast, but may split sentences/paragraphs.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 200,
        use_tokens: bool = False,
        tokenizer: Optional[Union[str, TokenizerProtocol]] = None
    ):
        """
        Initialize fixed-size chunker.
        
        Args:
            chunk_size: Target chunk size (characters or tokens depending on use_tokens)
            overlap: Number of characters/tokens to overlap between chunks
            use_tokens: If True, use token-based chunking; if False, use character-based (default)
            tokenizer: Optional tokenizer for token-based chunking.
                Only used if use_tokens=True. If None and use_tokens=True, uses character tokenizer.
        """
        super().__init__(tokenizer=tokenizer if use_tokens else None)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.use_tokens = use_tokens
    
    def chunk_text(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text into fixed-size pieces.
        
        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata
            
        Returns:
            List of Chunk objects
        """
        if not text:
            return []
        
        if self.use_tokens:
            return self._chunk_by_tokens(text, file_id, metadata)
        else:
            return self._chunk_by_characters(text, file_id, metadata)
    
    def _chunk_by_characters(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """Chunk text by characters (original implementation)."""
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size
            
            # Extract chunk
            chunk_text = text[start:end]
            
            # Generate chunk ID
            chunk_id = self._generate_chunk_id(file_id, chunk_index)
            
            # Create chunk
            chunk = Chunk(
                chunk_id=chunk_id,
                file_id=file_id,
                text=chunk_text,
                chunk_index=chunk_index,
                metadata={
                    **metadata,
                    'chunk_start': start,
                    'chunk_end': end,
                    'strategy': 'fixed_size',
                    'mode': 'character',
                },
            )
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start += self.chunk_size - self.overlap
            chunk_index += 1
        
        logger.debug(f"Chunked text into {len(chunks)} chunks (character-based)")
        return chunks
    
    def _chunk_by_tokens(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """Chunk text by tokens (token-aware implementation)."""
        # Encode text to tokens
        try:
            tokens = self.tokenizer.encode(text)
        except Exception as e:
            logger.warning(f"Token encoding failed, falling back to character-based: {e}")
            return self._chunk_by_characters(text, file_id, metadata)
        
        if not tokens:
            return []
        
        chunks = []
        start_idx = 0
        chunk_index = 0
        
        while start_idx < len(tokens):
            # Calculate end position
            end_idx = min(start_idx + self.chunk_size, len(tokens))
            
            # Extract token slice
            token_slice = tokens[start_idx:end_idx]
            
            # Decode tokens to text
            try:
                chunk_text = self.tokenizer.decode(token_slice)
            except Exception as e:
                logger.warning(f"Token decoding failed: {e}")
                # Fallback: use character-based estimation for this chunk
                # Average ~4 characters per token (heuristic for English text)
                char_start = start_idx * 4  # Approximate character position
                estimated_chars = len(token_slice) * 4
                char_end = min(char_start + estimated_chars, len(text))
                chunk_text = text[char_start:char_end]
            
            # Generate chunk ID
            chunk_id = self._generate_chunk_id(file_id, chunk_index)
            
            # Create chunk
            chunk = Chunk(
                chunk_id=chunk_id,
                file_id=file_id,
                text=chunk_text,
                chunk_index=chunk_index,
                metadata={
                    **metadata,
                    'token_start': start_idx,
                    'token_end': end_idx,
                    'token_count': len(token_slice),
                    'strategy': 'fixed_size',
                    'mode': 'token',
                },
            )
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start_idx += self.chunk_size - self.overlap
            chunk_index += 1
        
        logger.debug(f"Chunked text into {len(chunks)} chunks (token-based)")
        return chunks
