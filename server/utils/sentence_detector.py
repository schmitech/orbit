"""
Sentence detection utility for streaming text-to-speech.

This module provides utilities to detect sentence boundaries in streaming text,
enabling incremental TTS generation for better latency.
"""

import re
from typing import List


class SentenceDetector:
    """
    Detects sentence boundaries in streaming text.
    
    This class tracks accumulated text and identifies when complete sentences
    are available for TTS generation.
    """
    
    # Sentence ending patterns
    SENTENCE_ENDINGS = re.compile(r'([.!?]+)\s+')
    
    # Abbreviations that shouldn't trigger sentence breaks
    ABBREVIATIONS = {
        'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.',
        'vs.', 'etc.', 'e.g.', 'i.e.', 'a.m.', 'p.m.',
        'inc.', 'ltd.', 'corp.', 'co.', 'st.', 'ave.',
        'no.', 'vol.', 'pp.', 'ed.', 'etc.'
    }
    
    def __init__(self):
        """Initialize the sentence detector."""
        self.accumulated_text = ""
        self.processed_text = ""
        self.pending_sentences: List[str] = []
    
    def add_text(self, new_text: str) -> List[str]:
        """
        Add new text and return any completed sentences.
        
        Args:
            new_text: New text chunk to add
            
        Returns:
            List of completed sentences ready for TTS
        """
        if not new_text:
            return []
        
        self.accumulated_text += new_text
        completed_sentences = []
        
        # Find all sentence boundaries
        matches = list(self.SENTENCE_ENDINGS.finditer(self.accumulated_text))
        
        if not matches:
            # No complete sentences yet
            return []
        
        # Process matches to extract sentences
        last_end = 0
        for match in matches:
            start = last_end
            end = match.end()

            # Extract potential sentence (including the punctuation)
            potential_sentence = self.accumulated_text[start:end].strip()

            # Get character after the match for context (helps detect numbered lists)
            next_char = self.accumulated_text[end:end+1] if end < len(self.accumulated_text) else ""

            # Check if it's a false positive (abbreviation)
            if not self._is_false_positive(potential_sentence, next_char):
                # This is a real sentence - include the punctuation but not trailing whitespace
                sentence = self.accumulated_text[start:match.start() + len(match.group(1))].strip()
                if sentence:
                    completed_sentences.append(sentence)
                last_end = end
        
        # Update processed text
        if last_end > 0:
            self.processed_text += self.accumulated_text[:last_end]
            self.accumulated_text = self.accumulated_text[last_end:]
        
        return completed_sentences
    
    def _is_false_positive(self, text: str, next_char: str = "") -> bool:
        """
        Check if a potential sentence ending is a false positive.

        Args:
            text: Text ending with punctuation
            next_char: Character(s) following the sentence boundary

        Returns:
            True if it's likely a false positive (abbreviation)
        """
        # Check for common abbreviations (only periods, not ! or ?)
        if text and text[-1] == '.':
            text_lower = text.lower()
            for abbrev in self.ABBREVIATIONS:
                if text_lower.endswith(abbrev):
                    return True

        # Check for numbers followed by periods (e.g., "1. Introduction")
        # Look at what comes after the potential sentence boundary
        if text and text[-1] == '.' and next_char and next_char[0].isupper():
            # Check if it ends with a number before the period
            if re.search(r'\d\.$', text):
                return True

        return False
    
    def get_remaining_text(self) -> str:
        """
        Get any remaining text that hasn't formed a complete sentence.
        
        Returns:
            Remaining text buffer
        """
        return self.accumulated_text
    
    def reset(self):
        """Reset the detector state."""
        self.accumulated_text = ""
        self.processed_text = ""
        self.pending_sentences = []
    
    def has_pending_text(self) -> bool:
        """Check if there's pending text waiting for completion."""
        return bool(self.accumulated_text.strip())


def extract_sentences(text: str) -> List[str]:
    """
    Extract all sentences from a block of text.
    
    Args:
        text: Text to extract sentences from
        
    Returns:
        List of sentences
    """
    detector = SentenceDetector()
    sentences = []
    
    # Process in chunks to simulate streaming
    chunk_size = 100
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        new_sentences = detector.add_text(chunk)
        sentences.extend(new_sentences)
    
    # Get any remaining text
    remaining = detector.get_remaining_text()
    if remaining.strip():
        sentences.append(remaining.strip())
    
    return sentences

