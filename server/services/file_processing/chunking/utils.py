"""
Chunking Utilities

Shared utilities for sentence splitting and tokenization.
"""

import logging
import re
from typing import List, Optional, Union

# Protocol is available in typing from Python 3.8+, but use typing_extensions for compatibility
try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol

logger = logging.getLogger(__name__)


class TokenizerProtocol(Protocol):
    """Protocol for tokenizer interface."""
    
    def encode(self, text: str) -> List[int]:
        """Encode text to token IDs."""
        ...
    
    def decode(self, token_ids: List[int]) -> str:
        """Decode token IDs to text."""
        ...
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        ...


class SimpleTokenizer:
    """Simple character-based tokenizer as fallback."""
    
    def encode(self, text: str) -> List[int]:
        """Encode text as character codes."""
        return [ord(c) for c in text]
    
    def decode(self, token_ids: List[int]) -> str:
        """Decode character codes to text."""
        return ''.join(chr(t) for t in token_ids)
    
    def count_tokens(self, text: str) -> int:
        """Count characters as tokens."""
        return len(text)
    
    def count_tokens_batch(self, texts: List[str]) -> List[int]:
        """Count tokens for multiple texts."""
        return [self.count_tokens(text) for text in texts]


def get_tokenizer(tokenizer: Optional[Union[str, TokenizerProtocol]] = None) -> TokenizerProtocol:
    """
    Get a tokenizer instance.
    
    Args:
        tokenizer: Tokenizer identifier or tokenizer instance.
            - If None, returns SimpleTokenizer (character-based)
            - If string, tries to load from chonkie if available, else SimpleTokenizer
            - If TokenizerProtocol instance, returns as-is
    
    Returns:
        TokenizerProtocol instance
    """
    if tokenizer is None:
        return SimpleTokenizer()
    
    if isinstance(tokenizer, str):
        if tokenizer == "character":
            return SimpleTokenizer()
        # Try to use chonkie's AutoTokenizer if available
        try:
            from chonkie.tokenizer import AutoTokenizer
            return AutoTokenizer(tokenizer)
        except ImportError:
            logger.warning(
                f"Tokenizer '{tokenizer}' requested but chonkie is not installed. "
                "Falling back to character-based tokenization - chunk_size will be "
                "measured in characters, not tokens. Install chonkie to fix this: "
                "pip install chonkie"
            )
            return SimpleTokenizer()
    
    # Assume it's already a tokenizer instance
    return tokenizer


def split_sentences(
    text: str,
    delimiters: Optional[List[str]] = None,
    include_delim: Optional[str] = "prev",
    min_characters_per_sentence: int = 12
) -> List[str]:
    """
    Split text into sentences.
    
    Uses optimized Cython implementation from chonkie if available,
    otherwise falls back to Python regex-based splitting.
    
    Args:
        text: Text to split
        delimiters: List of sentence delimiters (default: [". ", "! ", "? ", "\\n"])
        include_delim: Whether to include delimiter in sentence ("prev", "next", or None)
        min_characters_per_sentence: Minimum characters per sentence
    
    Returns:
        List of sentences
    """
    if not text:
        return []
    
    if delimiters is None:
        delimiters = [". ", "! ", "? ", "\n"]
    
    # Try to use chonkie's optimized split function if available
    try:
        from chonkie.chunker.c_extensions.split import split_text
        return list(split_text(
            text=text,
            delim=delimiters,
            include_delim=include_delim,
            min_characters_per_segment=min_characters_per_sentence,
            whitespace_mode=False,
            character_fallback=True,
        ))
    except ImportError:
        # Fallback to Python implementation
        return _split_sentences_python(text, delimiters, include_delim, min_characters_per_sentence)


def _split_sentences_python(
    text: str,
    delimiters: List[str],
    include_delim: Optional[str],
    min_characters_per_sentence: int
) -> List[str]:
    """Python fallback for sentence splitting."""
    sep = "✄"
    t = text

    # Replace delimiters with separator
    for delim in delimiters:
        if include_delim == "prev":
            t = t.replace(delim, delim + sep)
        elif include_delim == "next":
            t = t.replace(delim, sep + delim)
        else:
            t = t.replace(delim, sep)

    # Initial split
    splits = [s for s in t.split(sep) if s]

    # Combine short splits with next or previous sentence
    sentences = []
    current = ""

    for s in splits:
        current += s

        # If current is long enough, finalize it
        if len(current) >= min_characters_per_sentence:
            sentences.append(current)
            current = ""

    # Add any remaining content
    if current:
        # If we have sentences, append to last one; otherwise add as new sentence
        if sentences:
            sentences[-1] += current
        else:
            sentences.append(current)

    return sentences


def split_by_regex(
    text: str,
    pattern: str,
    include_delim: Optional[str] = "next",
    min_characters_per_segment: int = 1
) -> List[str]:
    """
    Split text at every regex match, unlike split_sentences which only matches
    literal delimiter strings.

    Args:
        text: Text to split
        pattern: Regex pattern identifying the split boundary (e.g. a markdown
            header line)
        include_delim: "next" keeps the matched text at the start of the
            following segment (default; correct for headers, which should
            begin their section), "prev" appends it to the end of the
            preceding segment, None drops the matched text entirely
        min_characters_per_segment: Segments shorter than this are merged into
            the following segment

    Returns:
        List of text segments
    """
    if not text:
        return []

    matches = list(re.finditer(pattern, text))
    if not matches:
        return [text]

    pieces = []
    prev_end = 0
    for m in matches:
        start, end = m.start(), m.end()
        if include_delim == "prev":
            pieces.append(text[prev_end:end])
            prev_end = end
        elif include_delim == "next":
            if start > prev_end:
                pieces.append(text[prev_end:start])
            prev_end = start
        else:
            if start > prev_end:
                pieces.append(text[prev_end:start])
            prev_end = end
    pieces.append(text[prev_end:])
    pieces = [p for p in pieces if p]

    # Merge segments shorter than the minimum into the following segment
    merged = []
    carry = ""
    for p in pieces:
        candidate = carry + p
        if len(candidate) < min_characters_per_segment:
            carry = candidate
        else:
            merged.append(candidate)
            carry = ""
    if carry:
        if merged:
            merged[-1] += carry
        else:
            merged.append(carry)

    return merged
