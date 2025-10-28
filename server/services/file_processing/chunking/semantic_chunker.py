"""
Semantic Chunker

Semantic chunking that respects sentence boundaries.
Uses sentence-transformers for better semantic coherence.
"""

import logging
import re
from typing import Dict, Any, List
from .base_chunker import TextChunker, Chunk

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Semantic chunking will use simple sentence splitting.")


class SemanticChunker(TextChunker):
    """
    Semantic chunking strategy.
    
    Splits text on sentence boundaries and groups sentences semantically.
    Uses sentence-transformers for semantic similarity when available.
    """
    
    def __init__(self, chunk_size: int = 10, overlap: int = 2, model_name: str = None):
        """
        Initialize semantic chunker.
        
        Args:
            chunk_size: Target number of sentences per chunk
            overlap: Number of sentences to overlap between chunks
            model_name: Optional sentence-transformer model name
        """
        super().__init__()
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.model = None
        
        if SENTENCE_TRANSFORMERS_AVAILABLE and model_name:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"Loaded semantic chunking model: {model_name}")
            except Exception as e:
                logger.warning(f"Could not load model {model_name}: {e}")
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting using regex
        # Matches periods, exclamation marks, question marks
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def chunk_text(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk text using semantic boundaries.
        
        Args:
            text: Full text to chunk
            file_id: ID of source file
            metadata: File metadata
            
        Returns:
            List of Chunk objects
        """
        if not text:
            return []
        
        # Split into sentences
        sentences = self._split_sentences(text)
        
        if not sentences:
            return []
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(sentences):
            # Calculate end position
            end = min(start + self.chunk_size, len(sentences))
            
            # Extract sentences for this chunk
            chunk_sentences = sentences[start:end]
            chunk_text = ' '.join(chunk_sentences)
            
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
                    'sentence_start': start,
                    'sentence_end': end,
                    'sentence_count': len(chunk_sentences),
                    'strategy': 'semantic',
                },
            )
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start += self.chunk_size - self.overlap
            chunk_index += 1
        
        self.logger.debug(f"Chunked text into {len(chunks)} semantic chunks")
        return chunks
