"""
Semantic Chunker

Semantic chunking that respects sentence boundaries.
Uses sentence-transformers for better semantic coherence.
Enhanced with advanced techniques from chonkie.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Literal

from .base_chunker import TextChunker, Chunk
from .utils import split_sentences, TokenizerProtocol

logger = logging.getLogger(__name__)

# Check for sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.debug("sentence-transformers not available. Semantic chunking will use simple sentence splitting.")

# Check for numpy (for Savitzky-Golay filtering)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.debug("numpy not available. Savitzky-Golay filtering will be disabled.")


class SemanticChunker(TextChunker):
    """
    Semantic chunking strategy.
    
    Splits text on sentence boundaries and groups sentences semantically.
    Uses sentence-transformers for semantic similarity when available.
    Enhanced with advanced techniques:
    - Improved sentence splitting (Cython-optimized if available)
    - Savitzky-Golay filtering for boundary detection (optional)
    - Window-based similarity calculations
    - Skip-and-merge functionality
    """
    
    def __init__(
        self,
        chunk_size: int = 10,
        overlap: int = 2,
        model_name: Optional[str] = None,
        use_advanced: bool = False,
        threshold: float = 0.8,
        similarity_window: int = 3,
        min_sentences_per_chunk: int = 1,
        min_characters_per_sentence: int = 24,
        skip_window: int = 0,
        filter_window: int = 5,
        filter_polyorder: int = 3,
        filter_tolerance: float = 0.2,
        tokenizer: Optional[Union[str, TokenizerProtocol]] = None,
        chunk_size_tokens: Optional[int] = None
    ):
        """
        Initialize semantic chunker.
        
        Args:
            chunk_size: Target number of sentences per chunk (used if chunk_size_tokens is None)
            overlap: Number of sentences to overlap between chunks
            model_name: Optional sentence-transformer model name
            use_advanced: If True, use advanced semantic chunking with similarity calculations
            threshold: Threshold for semantic similarity (0-1) when use_advanced=True
            similarity_window: Number of sentences to consider for similarity threshold
            min_sentences_per_chunk: Minimum number of sentences per chunk
            min_characters_per_sentence: Minimum characters per sentence
            skip_window: Number of groups to skip when merging (0=disabled)
            filter_window: Window length for Savitzky-Golay filter (if numpy available)
            filter_polyorder: Polynomial order for Savitzky-Golay filter
            filter_tolerance: Tolerance for Savitzky-Golay filter
            tokenizer: Optional tokenizer for token-aware chunking
            chunk_size_tokens: Optional token-based chunk size (overrides chunk_size if set)
        """
        super().__init__(tokenizer=tokenizer)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.model = None
        self.use_advanced = use_advanced and SENTENCE_TRANSFORMERS_AVAILABLE
        self.threshold = threshold
        self.similarity_window = similarity_window
        self.min_sentences_per_chunk = min_sentences_per_chunk
        self.min_characters_per_sentence = min_characters_per_sentence
        self.skip_window = skip_window
        self.filter_window = filter_window
        self.filter_polyorder = filter_polyorder
        self.filter_tolerance = filter_tolerance
        self.chunk_size_tokens = chunk_size_tokens
        
        if SENTENCE_TRANSFORMERS_AVAILABLE and model_name:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"Loaded semantic chunking model: {model_name}")
            except Exception as e:
                logger.warning(f"Could not load model {model_name}: {e}")
                self.use_advanced = False
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using improved splitting."""
        return split_sentences(
            text,
            delimiters=[". ", "! ", "? ", "\n"],
            include_delim="prev",
            min_characters_per_sentence=self.min_characters_per_sentence
        )
    
    def _get_similarity(self, sentences: List[str]) -> List[float]:
        """
        Get semantic similarity between window and sentence embeddings.
        
        Args:
            sentences: List of sentence texts
            
        Returns:
            List of similarity scores
        """
        if not self.model or len(sentences) <= self.similarity_window:
            return []
        
        try:
            # Get embeddings for sentences (skip first similarity_window)
            sentence_embeddings = self.model.encode(
                sentences[self.similarity_window:],
                show_progress_bar=False
            )
            
            # Get window embeddings (groups of similarity_window sentences)
            window_texts = []
            for i in range(len(sentences) - self.similarity_window):
                window_texts.append(' '.join(sentences[i:i + self.similarity_window]))
            
            window_embeddings = self.model.encode(
                window_texts,
                show_progress_bar=False
            )
            
            # Calculate similarities
            similarities = []
            if not NUMPY_AVAILABLE:
                # Fallback: simple dot product without numpy
                for w_emb, s_emb in zip(window_embeddings, sentence_embeddings):
                    # Simple cosine similarity calculation
                    dot_product = sum(a * b for a, b in zip(w_emb, s_emb))
                    norm_w = sum(a * a for a in w_emb) ** 0.5
                    norm_s = sum(a * a for a in s_emb) ** 0.5
                    similarity = float(dot_product / (norm_w * norm_s)) if (norm_w * norm_s) > 0 else 0.0
                    similarities.append(similarity)
            else:
                for w_emb, s_emb in zip(window_embeddings, sentence_embeddings):
                    # Cosine similarity using numpy
                    similarity = float(np.dot(w_emb, s_emb) / (np.linalg.norm(w_emb) * np.linalg.norm(s_emb)))
                    similarities.append(similarity)
            
            return similarities
        except Exception as e:
            logger.warning(f"Error calculating similarities: {e}")
            return []
    
    def _get_split_indices(self, similarities: List[float]) -> List[int]:
        """
        Get split indices using Savitzky-Golay filtering if available.
        
        Args:
            similarities: List of similarity scores
            
        Returns:
            List of sentence indices where splits should occur
        """
        if not similarities:
            return []
        
        if not NUMPY_AVAILABLE or len(similarities) < self.filter_window:
            # Simple threshold-based splitting
            split_indices = []
            for i, sim in enumerate(similarities):
                if sim < self.threshold:
                    split_indices.append(i + self.similarity_window)
            return split_indices
        
        try:
            # Use Savitzky-Golay filter for smoother boundary detection
            from scipy.signal import savgol_filter
            
            # Apply filter
            filtered = savgol_filter(
                similarities,
                self.filter_window,
                self.filter_polyorder
            )
            
            # Find local minima
            split_indices = []
            for i in range(1, len(filtered) - 1):
                if (filtered[i] < filtered[i-1] and 
                    filtered[i] < filtered[i+1] and 
                    filtered[i] < self.threshold):
                    split_indices.append(i + self.similarity_window)
            
            return split_indices
        except ImportError:
            # scipy not available, use simple threshold
            split_indices = []
            for i, sim in enumerate(similarities):
                if sim < self.threshold:
                    split_indices.append(i + self.similarity_window)
            return split_indices
    
    def _skip_and_merge(self, sentence_groups: List[List[str]]) -> List[List[str]]:
        """
        Merge similar groups considering skip window.
        
        Args:
            sentence_groups: List of sentence groups
            
        Returns:
            List of merged groups
        """
        if len(sentence_groups) <= 1 or self.skip_window == 0 or not self.model:
            return sentence_groups
        
        try:
            # Get embeddings for all groups
            group_texts = [' '.join(group) for group in sentence_groups]
            embeddings = self.model.encode(group_texts, show_progress_bar=False)
            
            merged_groups = []
            i = 0
            
            while i < len(sentence_groups):
                if i == len(sentence_groups) - 1:
                    merged_groups.append(sentence_groups[i])
                    break
                
                skip_index = min(i + self.skip_window + 1, len(sentence_groups) - 1)
                best_similarity = -1.0
                best_idx = -1
                
                # Find best merge candidate within skip window
                for j in range(i + 1, min(skip_index + 1, len(sentence_groups))):
                    if NUMPY_AVAILABLE:
                        similarity = float(np.dot(embeddings[i], embeddings[j]) / 
                                         (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])))
                    else:
                        # Fallback: simple cosine similarity
                        dot_product = sum(a * b for a, b in zip(embeddings[i], embeddings[j]))
                        norm_i = sum(a * a for a in embeddings[i]) ** 0.5
                        norm_j = sum(a * a for a in embeddings[j]) ** 0.5
                        similarity = float(dot_product / (norm_i * norm_j)) if (norm_i * norm_j) > 0 else 0.0
                    
                    if similarity >= self.threshold and similarity > best_similarity:
                        best_similarity = similarity
                        best_idx = j
                
                if best_idx != -1:
                    # Merge groups
                    merged = []
                    for k in range(i, best_idx + 1):
                        merged.extend(sentence_groups[k])
                    merged_groups.append(merged)
                    i = best_idx + 1
                else:
                    merged_groups.append(sentence_groups[i])
                    i += 1
            
            return merged_groups
        except Exception as e:
            logger.warning(f"Error in skip-and-merge: {e}")
            return sentence_groups
    
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
        
        # Use advanced semantic chunking if enabled
        if self.use_advanced and self.model and len(sentences) > self.similarity_window:
            return self._chunk_advanced(sentences, text, file_id, metadata)
        else:
            return self._chunk_simple(sentences, file_id, metadata)
    
    def _chunk_simple(self, sentences: List[str], file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """Simple sentence-based chunking (original implementation)."""
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
                    'mode': 'simple',
                },
            )
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start += self.chunk_size - self.overlap
            chunk_index += 1
        
        logger.debug(f"Chunked text into {len(chunks)} semantic chunks (simple mode)")
        return chunks
    
    def _chunk_advanced(self, sentences: List[str], text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """Advanced semantic chunking with similarity calculations."""
        # Get similarities
        similarities = self._get_similarity(sentences)
        
        if not similarities:
            # Fallback to simple chunking
            return self._chunk_simple(sentences, file_id, metadata)
        
        # Get split indices
        split_indices = self._get_split_indices(similarities)
        
        # Group sentences based on split indices
        sentence_groups = []
        if not split_indices:
            sentence_groups.append(sentences)
        else:
            # Add boundary at start
            split_indices = [0] + split_indices + [len(sentences)]
            
            for i in range(len(split_indices) - 1):
                group = sentences[split_indices[i]:split_indices[i+1]]
                if group:
                    sentence_groups.append(group)
        
        # Apply skip-and-merge if enabled
        if self.skip_window > 0:
            sentence_groups = self._skip_and_merge(sentence_groups)
        
        # Respect token limits if chunk_size_tokens is set
        if self.chunk_size_tokens:
            sentence_groups = self._split_by_tokens(sentence_groups)
        
        # Create chunks
        chunks = []
        chunk_index = 0
        
        for group in sentence_groups:
            chunk_text = ' '.join(group)
            
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
                    'sentence_count': len(group),
                    'strategy': 'semantic',
                    'mode': 'advanced',
                },
            )
            
            chunks.append(chunk)
            chunk_index += 1
        
        logger.debug(f"Chunked text into {len(chunks)} semantic chunks (advanced mode)")
        return chunks
    
    def _split_by_tokens(self, sentence_groups: List[List[str]]) -> List[List[str]]:
        """Split groups that exceed token limit."""
        if not self.chunk_size_tokens:
            return sentence_groups
        
        final_groups = []
        
        for group in sentence_groups:
            group_text = ' '.join(group)
            token_count = self.count_tokens(group_text)
            
            if token_count <= self.chunk_size_tokens:
                final_groups.append(group)
            else:
                # Split group into smaller chunks
                current_group = []
                current_token_count = 0
                
                for sentence in group:
                    sent_text = sentence if isinstance(sentence, str) else ' '.join(sentence)
                    sent_tokens = self.count_tokens(sent_text)
                    
                    if current_token_count + sent_tokens <= self.chunk_size_tokens:
                        current_group.append(sentence)
                        current_token_count += sent_tokens
                    else:
                        if current_group:
                            final_groups.append(current_group)
                        current_group = [sentence]
                        current_token_count = sent_tokens
                
                if current_group:
                    final_groups.append(current_group)
        
        return final_groups
