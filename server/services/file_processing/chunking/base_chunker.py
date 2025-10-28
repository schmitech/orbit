"""
Base Chunker

Abstract base class for text chunking strategies.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """
    Represents a chunk of text from a file.
    
    Attributes:
        chunk_id: Unique identifier for the chunk
        file_id: ID of the source file
        text: Chunk text content
        chunk_index: Position of chunk in file
        metadata: Additional chunk metadata
        embedding: Optional pre-computed embedding
    """
    chunk_id: str
    file_id: str
    text: str
    chunk_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: List[float] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"Chunk(chunk_id={self.chunk_id[:8]}..., chunk_index={self.chunk_index}, len={len(self.text)})"


class TextChunker(ABC):
    """
    Abstract base class for text chunking strategies.
    
    Different chunking strategies can be implemented:
    - Fixed size chunking
    - Semantic chunking (sentence-aware)
    - Paragraph-based chunking
    - Structure-aware chunking
    """
    
    def __init__(self):
        """Initialize chunker."""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def chunk_text(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text into smaller pieces.
        
        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata
            
        Returns:
            List of Chunk objects
        """
        pass
    
    def _generate_chunk_id(self, file_id: str, chunk_index: int) -> str:
        """Generate unique chunk ID."""
        return f"{file_id}_chunk_{chunk_index}"
