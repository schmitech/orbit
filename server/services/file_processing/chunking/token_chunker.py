"""
Token Chunker

Token-based chunking that respects token limits accurately.
Better for LLM context windows than character-based chunking.
"""

import logging
from typing import Dict, Any, List, Optional, Union

from .base_chunker import TextChunker, Chunk
from .utils import TokenizerProtocol, get_tokenizer

logger = logging.getLogger(__name__)


class TokenChunker(TextChunker):
    """
    Token-based chunking strategy.
    
    Splits text into chunks based on token counts rather than characters.
    More accurate for LLM context windows than character-based chunking.
    """
    
    def __init__(
        self,
        chunk_size: int = 2048,
        overlap: int = 0,
        tokenizer: Optional[Union[str, TokenizerProtocol]] = "character"
    ):
        """
        Initialize token chunker.
        
        Args:
            chunk_size: Maximum number of tokens per chunk
            overlap: Number of tokens to overlap between chunks
            tokenizer: Tokenizer to use. Can be a string identifier or TokenizerProtocol instance.
                Defaults to "character" (character-based tokenization).
        """
        super().__init__(tokenizer=tokenizer)
        
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_text(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text into token-based pieces.
        
        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata
            
        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []
        
        try:
            # Encode text to tokens
            tokens = self.tokenizer.encode(text)
        except Exception as e:
            logger.warning(f"Token encoding failed: {e}. Falling back to character-based chunking.")
            # Fallback to character-based chunking
            from .fixed_chunker import FixedSizeChunker
            fallback = FixedSizeChunker(chunk_size=self.chunk_size, overlap=self.overlap)
            return fallback.chunk_text(text, file_id, metadata)
        
        if not tokens:
            return []
        
        # Generate token groups with overlap
        token_groups = []
        start_idx = 0
        
        while start_idx < len(tokens):
            end_idx = min(start_idx + self.chunk_size, len(tokens))
            token_slice = tokens[start_idx:end_idx]
            token_groups.append(token_slice)
            
            # Move to next chunk with overlap
            if end_idx >= len(tokens):
                break
            start_idx += self.chunk_size - self.overlap
        
        # Decode token groups to text
        chunks = []
        chunk_index = 0
        current_text_pos = 0
        
        for token_group in token_groups:
            try:
                # Decode tokens to text
                chunk_text = self.tokenizer.decode(token_group)
            except Exception as e:
                logger.warning(f"Token decoding failed: {e}")
                # Approximate text position using character estimation
                # Average ~4 characters per token (heuristic for English text)
                char_start = current_text_pos
                estimated_chars = len(token_group) * 4
                char_end = min(char_start + estimated_chars, len(text))
                chunk_text = text[char_start:char_end]
                current_text_pos = char_end
            else:
                # Update text position based on decoded text length
                current_text_pos += len(chunk_text)
            
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
                    'token_count': len(token_group),
                    'strategy': 'token',
                },
            )
            
            chunks.append(chunk)
            chunk_index += 1
        
        logger.debug(f"Chunked text into {len(chunks)} token-based chunks")
        return chunks

