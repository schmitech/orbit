"""
Token Chunker

Token-based chunking that respects token limits accurately.
Better for LLM context windows than character-based chunking.
"""

import logging
from typing import Any, Optional, Union

from .base_chunker import TextChunker, Chunk
from .utils import SimpleTokenizer, TokenInt, TokenizerProtocol
from utils.embedding_budget import (
    EmbeddingBudget,
    resolve_embedding_budget,
    split_text_to_budget,
)

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
        tokenizer: Optional[Union[str, TokenizerProtocol]] = "character",
        budget: Optional[EmbeddingBudget] = None,
    ):
        """
        Initialize token chunker.
        
        Args:
            chunk_size: Maximum number of tokens per chunk
            overlap: Number of tokens to overlap between chunks
            tokenizer: Tokenizer to use. Can be a string identifier or TokenizerProtocol instance.
                Defaults to "character" (character-based tokenization).
            budget: Optional explicit EmbeddingBudget. If omitted, resolved from chunk_size.
        """
        super().__init__(tokenizer=tokenizer)
        
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("chunk_overlap must be nonnegative")
        if overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        
        self.chunk_size = chunk_size
        self.overlap = overlap

        self._is_character_mode = (
            tokenizer is None
            or tokenizer == "character"
            or isinstance(self._tokenizer, SimpleTokenizer)
        )

        if not self._is_character_mode:
            # Must implement full TokenizerProtocol with callable encode and decode
            if not (callable(getattr(self._tokenizer, "encode", None)) and callable(getattr(self._tokenizer, "decode", None))):
                raise TypeError(
                    f"Tokenizer must implement full TokenizerProtocol with callable 'encode' and 'decode' methods, "
                    f"got {type(self._tokenizer).__name__}"
                )

        if budget is not None:
            self.budget = budget
        else:
            self.budget = resolve_embedding_budget(
                max_embedding_tokens=self.chunk_size,
                chunk_target_tokens=self.chunk_size,
                overlap_tokens=self.overlap,
                safety_margin=1.0,
            )

    def count_tokens(self, text: str) -> int:
        if self._is_character_mode or isinstance(self.tokenizer, SimpleTokenizer):
            cnt = self.budget.count(text)
            return TokenInt(cnt.count, estimated=cnt.estimated)
        return super().count_tokens(text)

    def chunk_text(self, text: str, file_id: str, metadata: dict[str, Any]) -> list[Chunk]:
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

        # Check if running in character default mode
        is_character = self._is_character_mode and isinstance(self.tokenizer, SimpleTokenizer)

        if is_character:
            pieces = split_text_to_budget(text, self.budget)
            chunks = []
            for chunk_index, piece in enumerate(pieces):
                cnt = self.budget.count(piece)
                count_val = max(1, cnt.count) if piece.strip() else 0
                token_int = TokenInt(count_val, estimated=True)
                chunk_id = self._generate_chunk_id(file_id, chunk_index)
                chunk = Chunk(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    text=piece,
                    chunk_index=chunk_index,
                    metadata={
                        **metadata,
                        'token_count': token_int,
                        'token_count_estimated': True,
                        'estimated': True,
                        'strategy': 'token',
                    },
                )
                chunks.append(chunk)
            logger.debug(f"Chunked text into {len(chunks)} token-based chunks (budget-split mode)")
            return chunks

        # Non-character tokenizer: require callable encode and decode
        if not (callable(getattr(self.tokenizer, "encode", None)) and callable(getattr(self.tokenizer, "decode", None))):
            raise TypeError(
                f"Tokenizer must implement callable 'encode' and 'decode' methods, "
                f"got {type(self.tokenizer).__name__}"
            )

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
            decode_failed = False
            try:
                # Decode tokens to text
                chunk_text = self.tokenizer.decode(token_group)
            except Exception as e:
                logger.warning(f"Token decoding failed: {e}")
                decode_failed = True
                # Approximate text position using shared estimation convention (1 token ~= 3 chars)
                char_start = current_text_pos
                estimated_chars = len(token_group) * 3
                char_end = min(char_start + estimated_chars, len(text))
                chunk_text = text[char_start:char_end]
                current_text_pos = char_end
            else:
                # Update text position based on decoded text length
                current_text_pos += len(chunk_text)

            # Generate chunk ID
            chunk_id = self._generate_chunk_id(file_id, chunk_index)

            is_estimated = decode_failed or getattr(self.tokenizer, "estimated", False)
            token_int = TokenInt(len(token_group), estimated=is_estimated)

            # Create chunk
            chunk = Chunk(
                chunk_id=chunk_id,
                file_id=file_id,
                text=chunk_text,
                chunk_index=chunk_index,
                metadata={
                    **metadata,
                    'token_count': token_int,
                    'token_count_estimated': is_estimated,
                    'estimated': is_estimated,
                    'strategy': 'token',
                },
            )

            chunks.append(chunk)
            chunk_index += 1

        logger.debug(f"Chunked text into {len(chunks)} token-based chunks")
        return chunks

