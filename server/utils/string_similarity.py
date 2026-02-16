"""
String Similarity Utilities
===========================

This module provides string similarity algorithms for fuzzy matching and scoring.

Supported algorithms:
- Jaro-Winkler: Optimized for short strings and prefix matching (recommended)
- Levenshtein: Edit distance based matching (handles typos)
- Ratio: Simple character ratio matching (fastest)

Features:
- Uses fast C libraries (Levenshtein, jarowinkler) when available
- Falls back to pure Python implementations if C libraries not installed
- Provides both distance and similarity functions
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import fast C-based libraries, fall back to pure Python if not available
try:
    from Levenshtein import ratio as levenshtein_ratio
    LEVENSHTEIN_C_AVAILABLE = True
    logger.debug("Using C-based Levenshtein library")
except ImportError:
    LEVENSHTEIN_C_AVAILABLE = False
    logger.debug("C-based Levenshtein not available, using pure Python fallback")

try:
    from jarowinkler import jarowinkler_similarity as jw_similarity
    JAROWINKLER_C_AVAILABLE = True
    logger.debug("Using C-based jarowinkler library")
except ImportError:
    JAROWINKLER_C_AVAILABLE = False
    logger.debug("C-based jarowinkler not available, using pure Python fallback")


@dataclass
class SimilarityResult:
    """Result of a similarity comparison."""
    score: float          # Similarity score (0.0 to 1.0)
    algorithm: str        # Algorithm used
    matched_text: str     # The text that was matched
    query: str            # The original query


class StringSimilarity:
    """
    Provides string similarity algorithms for fuzzy matching.

    Supported algorithms:
    - jaro_winkler: Optimized for short strings and prefixes (recommended)
    - levenshtein: Edit distance based matching (handles typos)
    - ratio: Simple character-based ratio (fastest)

    Usage:
        from utils.string_similarity import StringSimilarity

        # Single comparison
        score = StringSimilarity.jaro_winkler_similarity("hello", "hallo")

        # Best match from list
        best = StringSimilarity.find_best_match("query", candidates, algorithm="jaro_winkler")
    """

    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """
        Calculate the Levenshtein (edit) distance between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Number of single-character edits needed to transform s1 into s2
        """
        if len(s1) < len(s2):
            return StringSimilarity.levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost is 0 if characters match, 1 otherwise
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    @staticmethod
    def levenshtein_similarity(s1: str, s2: str) -> float:
        """
        Calculate normalized Levenshtein similarity (0.0 to 1.0).

        Uses fast C library if available, falls back to pure Python.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity score between 0.0 (completely different) and 1.0 (identical)
        """
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        # Use C library if available (10-100x faster)
        if LEVENSHTEIN_C_AVAILABLE:
            return levenshtein_ratio(s1, s2)

        # Fall back to pure Python
        distance = StringSimilarity.levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        return 1.0 - (distance / max_len)

    @staticmethod
    def jaro_similarity(s1: str, s2: str) -> float:
        """
        Calculate Jaro similarity between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if s1 == s2:
            return 1.0

        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0

        # Calculate match window
        match_distance = max(len1, len2) // 2 - 1
        if match_distance < 0:
            match_distance = 0

        s1_matches = [False] * len1
        s2_matches = [False] * len2

        matches = 0
        transpositions = 0

        # Find matches
        for i in range(len1):
            start = max(0, i - match_distance)
            end = min(i + match_distance + 1, len2)

            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

        # Count transpositions
        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1

        jaro = (
            matches / len1 +
            matches / len2 +
            (matches - transpositions / 2) / matches
        ) / 3.0

        return jaro

    @staticmethod
    def jaro_winkler_similarity(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
        """
        Calculate Jaro-Winkler similarity between two strings.

        Jaro-Winkler gives higher scores to strings that match from the beginning,
        making it ideal for matching where prefixes matter.

        Uses fast C library if available, falls back to pure Python.

        Args:
            s1: First string
            s2: Second string
            prefix_weight: Weight for common prefix bonus (default 0.1)

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Use C library if available (50-100x faster)
        if JAROWINKLER_C_AVAILABLE:
            return jw_similarity(s1, s2, prefix_weight=prefix_weight)

        # Fall back to pure Python implementation
        jaro = StringSimilarity.jaro_similarity(s1, s2)

        # Find common prefix length (up to 4 characters)
        prefix_len = 0
        for i in range(min(len(s1), len(s2), 4)):
            if s1[i] == s2[i]:
                prefix_len += 1
            else:
                break

        # Apply Winkler modification
        return jaro + prefix_len * prefix_weight * (1 - jaro)

    @staticmethod
    def ratio_similarity(s1: str, s2: str) -> float:
        """
        Calculate simple character-based ratio similarity.

        This is the fastest algorithm but least sophisticated.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        # Count matching characters
        matches = 0
        s2_chars = list(s2)
        for c in s1:
            if c in s2_chars:
                matches += 1
                s2_chars.remove(c)

        return (2.0 * matches) / (len(s1) + len(s2))

    @staticmethod
    def calculate_similarity(
        s1: str,
        s2: str,
        algorithm: str = "jaro_winkler",
        case_sensitive: bool = False
    ) -> float:
        """
        Calculate similarity using the specified algorithm.

        Args:
            s1: First string
            s2: Second string
            algorithm: One of "jaro_winkler", "levenshtein", "ratio"
            case_sensitive: Whether comparison should be case-sensitive

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not case_sensitive:
            s1 = s1.lower()
            s2 = s2.lower()

        if algorithm == "jaro_winkler":
            return StringSimilarity.jaro_winkler_similarity(s1, s2)
        elif algorithm == "levenshtein":
            return StringSimilarity.levenshtein_similarity(s1, s2)
        elif algorithm == "ratio":
            return StringSimilarity.ratio_similarity(s1, s2)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}. Use 'jaro_winkler', 'levenshtein', or 'ratio'")

    @staticmethod
    def calculate_best_text_similarity(
        query: str,
        text: str,
        algorithm: str = "jaro_winkler",
        case_sensitive: bool = False,
        check_words: bool = True
    ) -> float:
        """
        Calculate the best similarity score between query and text.

        This compares the query against:
        1. The full text
        2. Individual words in the text (if check_words=True)
        3. Word combinations that start with matching words

        Returns the maximum score found.

        Args:
            query: Query string to match
            text: Text to search in
            algorithm: Similarity algorithm to use
            case_sensitive: Whether comparison should be case-sensitive
            check_words: Whether to also check individual words

        Returns:
            Maximum similarity score found (0.0 to 1.0)
        """
        if not case_sensitive:
            query = query.lower()
            text = text.lower()

        best_score = StringSimilarity.calculate_similarity(
            query, text, algorithm, case_sensitive=True  # Already lowercased
        )

        if check_words:
            words = text.split()

            # Check individual words
            for word in words:
                word_score = StringSimilarity.calculate_similarity(
                    query, word, algorithm, case_sensitive=True
                )
                best_score = max(best_score, word_score * 0.95)  # Slight penalty for word match

            # Check word sequences starting at each position
            query_word_count = len(query.split())
            if query_word_count > 1:
                for i in range(len(words)):
                    end = min(i + query_word_count + 1, len(words) + 1)
                    for j in range(i + 1, end):
                        sequence = " ".join(words[i:j])
                        seq_score = StringSimilarity.calculate_similarity(
                            query, sequence, algorithm, case_sensitive=True
                        )
                        best_score = max(best_score, seq_score)

        return best_score

    @staticmethod
    def find_best_match(
        query: str,
        candidates: List[str],
        algorithm: str = "jaro_winkler",
        min_threshold: float = 0.0,
        case_sensitive: bool = False
    ) -> Optional[SimilarityResult]:
        """
        Find the best matching candidate for a query.

        Args:
            query: Query string to match
            candidates: List of candidate strings
            algorithm: Similarity algorithm to use
            min_threshold: Minimum similarity score to consider a match
            case_sensitive: Whether comparison should be case-sensitive

        Returns:
            SimilarityResult for best match, or None if no matches above threshold
        """
        best_result = None
        best_score = min_threshold

        for candidate in candidates:
            score = StringSimilarity.calculate_best_text_similarity(
                query, candidate, algorithm, case_sensitive
            )

            if score > best_score:
                best_score = score
                best_result = SimilarityResult(
                    score=score,
                    algorithm=algorithm,
                    matched_text=candidate,
                    query=query
                )

        return best_result

    @staticmethod
    def find_all_matches(
        query: str,
        candidates: List[str],
        algorithm: str = "jaro_winkler",
        min_threshold: float = 0.3,
        case_sensitive: bool = False,
        limit: Optional[int] = None
    ) -> List[SimilarityResult]:
        """
        Find all matching candidates above a threshold, sorted by score.

        Args:
            query: Query string to match
            candidates: List of candidate strings
            algorithm: Similarity algorithm to use
            min_threshold: Minimum similarity score to consider a match
            case_sensitive: Whether comparison should be case-sensitive
            limit: Maximum number of results to return

        Returns:
            List of SimilarityResult objects, sorted by score descending
        """
        results = []

        for candidate in candidates:
            score = StringSimilarity.calculate_best_text_similarity(
                query, candidate, algorithm, case_sensitive
            )

            if score >= min_threshold:
                results.append(SimilarityResult(
                    score=score,
                    algorithm=algorithm,
                    matched_text=candidate,
                    query=query
                ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)

        if limit is not None:
            results = results[:limit]

        return results


# Convenience aliases for common operations
def jaro_winkler(s1: str, s2: str) -> float:
    """Calculate Jaro-Winkler similarity (case-insensitive)."""
    return StringSimilarity.jaro_winkler_similarity(s1.lower(), s2.lower())


def levenshtein(s1: str, s2: str) -> float:
    """Calculate Levenshtein similarity (case-insensitive)."""
    return StringSimilarity.levenshtein_similarity(s1.lower(), s2.lower())


def best_match(query: str, candidates: List[str], threshold: float = 0.5) -> Optional[str]:
    """Find the best matching candidate for a query."""
    result = StringSimilarity.find_best_match(query, candidates, min_threshold=threshold)
    return result.matched_text if result else None
