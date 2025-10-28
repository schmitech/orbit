"""
Fixed Size Chunker

Simple fixed-size chunking with configurable overlap.
"""

import logging
from typing import Dict, Any, List
from .base_chunker import TextChunker, Chunk

logger = logging.getLogger(__name__)


class FixedSizeChunker(TextChunker):
    """
    Fixed-size chunking strategy.
    
    Splits text into chunks of fixed size with configurable overlap.
    Simple and fast, but may split sentences/paragraphs.
    """
    
    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        """
        Initialize fixed-size chunker.
        
        Args:
            chunk_size: Target chunk size in characters
            overlap: Number of characters to overlap between chunks
        """
        super().__init__()
        self.chunk_size = chunk_size
        self.overlap = overlap
    
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
                },
            )
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start += self.chunk_size - self.overlap
            chunk_index += 1
        
        self.logger.debug(f"Chunked text into {len(chunks)} chunks")
        return chunks
