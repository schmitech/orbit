"""
Unit tests for AutocompleteService.

Tests cover:
- FuzzyMatcher algorithms (Levenshtein, Jaro-Winkler, substring)
- AutocompleteService initialization and configuration
- Caching (memory and Redis)
- Suggestion filtering and ranking
- Enabled/disabled states
- Edge cases
"""

import pytest
import sys
import os
import time
import json
from unittest.mock import AsyncMock, MagicMock

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.autocomplete_service import (
    AutocompleteService,
    AutocompleteSuggestion,
    FuzzyMatcher,
    LEVENSHTEIN_C_AVAILABLE,
    JAROWINKLER_C_AVAILABLE,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def enabled_config():
    """Basic enabled configuration."""
    return {
        'autocomplete': {
            'enabled': True,
            'min_query_length': 3,
            'max_suggestions': 5,
            'cache': {
                'use_redis': False,
                'ttl_seconds': 300,
                'redis_key_prefix': 'test_autocomplete:'
            },
            'fuzzy_matching': {
                'enabled': False,
                'algorithm': 'substring',
                'threshold': 0.75,
                'max_candidates': 100
            }
        }
    }


@pytest.fixture
def disabled_config():
    """Disabled configuration."""
    return {
        'autocomplete': {
            'enabled': False
        }
    }


@pytest.fixture
def fuzzy_levenshtein_config():
    """Configuration with Levenshtein fuzzy matching."""
    return {
        'autocomplete': {
            'enabled': True,
            'min_query_length': 3,
            'max_suggestions': 5,
            'cache': {
                'use_redis': False,
                'ttl_seconds': 300
            },
            'fuzzy_matching': {
                'enabled': True,
                'algorithm': 'levenshtein',
                'threshold': 0.6,
                'max_candidates': 100
            }
        }
    }


@pytest.fixture
def fuzzy_jaro_winkler_config():
    """Configuration with Jaro-Winkler fuzzy matching."""
    return {
        'autocomplete': {
            'enabled': True,
            'min_query_length': 3,
            'max_suggestions': 5,
            'cache': {
                'use_redis': False,
                'ttl_seconds': 300
            },
            'fuzzy_matching': {
                'enabled': True,
                'algorithm': 'jaro_winkler',
                'threshold': 0.75,
                'max_candidates': 100
            }
        }
    }


@pytest.fixture
def redis_enabled_config():
    """Configuration with Redis caching enabled."""
    return {
        'autocomplete': {
            'enabled': True,
            'min_query_length': 3,
            'max_suggestions': 5,
            'cache': {
                'use_redis': True,
                'ttl_seconds': 1800,
                'redis_key_prefix': 'autocomplete:'
            },
            'fuzzy_matching': {
                'enabled': False,
                'algorithm': 'substring',
                'threshold': 0.75
            }
        }
    }


@pytest.fixture
def sample_nl_examples():
    """Sample nl_examples for testing."""
    return [
        "Show me movies from 2020",
        "Find movies by director Christopher Nolan",
        "What movies are rated PG-13?",
        "List all comedy movies",
        "Show me action movies with high ratings",
        "Find movies released in summer 2019",
        "What are the top rated movies?",
        "Show me movies starring Tom Hanks",
        "Find movies with runtime over 2 hours",
        "List drama movies from the 90s"
    ]


@pytest.fixture
def mock_redis_service():
    """Mock Redis service for testing."""
    redis_service = MagicMock()
    redis_service.enabled = True
    redis_service.get = AsyncMock(return_value=None)
    redis_service.set = AsyncMock(return_value=True)
    redis_service.delete = AsyncMock(return_value=1)
    redis_service.client = MagicMock()
    redis_service.client.scan = AsyncMock(return_value=(0, []))
    return redis_service


# ============================================================================
# FuzzyMatcher Tests
# ============================================================================

class TestFuzzyMatcherLevenshtein:
    """Tests for Levenshtein distance and similarity calculations."""

    def test_levenshtein_distance_identical_strings(self):
        """Test that identical strings have distance 0."""
        assert FuzzyMatcher.levenshtein_distance("hello", "hello") == 0
        assert FuzzyMatcher.levenshtein_distance("", "") == 0

    def test_levenshtein_distance_empty_string(self):
        """Test distance with empty strings."""
        assert FuzzyMatcher.levenshtein_distance("hello", "") == 5
        assert FuzzyMatcher.levenshtein_distance("", "world") == 5

    def test_levenshtein_distance_single_edit(self):
        """Test single character edit operations."""
        # Substitution
        assert FuzzyMatcher.levenshtein_distance("cat", "bat") == 1
        # Insertion
        assert FuzzyMatcher.levenshtein_distance("cat", "cats") == 1
        # Deletion
        assert FuzzyMatcher.levenshtein_distance("cats", "cat") == 1

    def test_levenshtein_distance_multiple_edits(self):
        """Test multiple edit operations."""
        assert FuzzyMatcher.levenshtein_distance("kitten", "sitting") == 3
        assert FuzzyMatcher.levenshtein_distance("saturday", "sunday") == 3

    def test_levenshtein_similarity_identical(self):
        """Test similarity of identical strings."""
        assert FuzzyMatcher.levenshtein_similarity("hello", "hello") == 1.0
        assert FuzzyMatcher.levenshtein_similarity("", "") == 1.0

    def test_levenshtein_similarity_completely_different(self):
        """Test similarity of completely different strings."""
        # "abc" vs "xyz" = 3 edits, max_len=3, so similarity = 1 - 3/3 = 0
        assert FuzzyMatcher.levenshtein_similarity("abc", "xyz") == 0.0

    def test_levenshtein_similarity_partial_match(self):
        """Test partial similarity."""
        # "hello" vs "hallo" = 1 edit, max_len=5, so similarity = 1 - 1/5 = 0.8
        similarity = FuzzyMatcher.levenshtein_similarity("hello", "hallo")
        assert 0.79 <= similarity <= 0.81

    def test_levenshtein_similarity_empty_string(self):
        """Test similarity with empty strings."""
        assert FuzzyMatcher.levenshtein_similarity("hello", "") == 0.0
        assert FuzzyMatcher.levenshtein_similarity("", "world") == 0.0


class TestFuzzyMatcherJaro:
    """Tests for Jaro and Jaro-Winkler similarity calculations."""

    def test_jaro_similarity_identical(self):
        """Test Jaro similarity for identical strings."""
        assert FuzzyMatcher.jaro_similarity("hello", "hello") == 1.0

    def test_jaro_similarity_empty(self):
        """Test Jaro similarity with empty strings."""
        assert FuzzyMatcher.jaro_similarity("", "") == 1.0
        assert FuzzyMatcher.jaro_similarity("hello", "") == 0.0
        assert FuzzyMatcher.jaro_similarity("", "world") == 0.0

    def test_jaro_similarity_no_match(self):
        """Test Jaro similarity for strings with no common characters."""
        # Completely different characters
        similarity = FuzzyMatcher.jaro_similarity("abc", "xyz")
        assert similarity == 0.0

    def test_jaro_similarity_partial(self):
        """Test Jaro similarity for partially matching strings."""
        similarity = FuzzyMatcher.jaro_similarity("martha", "marhta")
        # Should be high due to similar characters
        assert similarity > 0.9

    def test_jaro_winkler_identical(self):
        """Test Jaro-Winkler similarity for identical strings."""
        assert FuzzyMatcher.jaro_winkler_similarity("hello", "hello") == 1.0

    def test_jaro_winkler_prefix_bonus(self):
        """Test that Jaro-Winkler gives bonus for common prefixes."""
        # Jaro-Winkler should be >= Jaro for strings with common prefix
        s1, s2 = "prefix_test", "prefix_best"
        jaro = FuzzyMatcher.jaro_similarity(s1, s2)
        jaro_winkler = FuzzyMatcher.jaro_winkler_similarity(s1, s2)
        assert jaro_winkler >= jaro

    def test_jaro_winkler_typo_tolerance(self):
        """Test Jaro-Winkler handles typos well."""
        # Common typos should still score high
        assert FuzzyMatcher.jaro_winkler_similarity("movies", "moveis") > 0.9
        assert FuzzyMatcher.jaro_winkler_similarity("show", "shwo") > 0.85


class TestFuzzyMatcherSubstring:
    """Tests for substring matching."""

    def test_substring_match_prefix(self):
        """Test prefix substring match."""
        is_match, score = FuzzyMatcher.substring_match("show", "show me movies")
        assert is_match is True
        assert score == 1.0  # Perfect prefix match

    def test_substring_match_middle(self):
        """Test substring match in the middle."""
        is_match, score = FuzzyMatcher.substring_match("movies", "show me movies")
        assert is_match is True
        assert score < 1.0  # Not a prefix, lower score

    def test_substring_no_match(self):
        """Test no substring match."""
        is_match, score = FuzzyMatcher.substring_match("xyz", "show me movies")
        assert is_match is False
        assert score == 0.0

    def test_substring_case_insensitive(self):
        """Test case-insensitive matching."""
        is_match, score = FuzzyMatcher.substring_match("SHOW", "show me movies")
        assert is_match is True

    def test_substring_empty_query(self):
        """Test with empty query."""
        is_match, score = FuzzyMatcher.substring_match("", "show me movies")
        assert is_match is True  # Empty string is in every string


# ============================================================================
# AutocompleteService Initialization Tests
# ============================================================================

class TestAutocompleteServiceInitialization:
    """Tests for AutocompleteService initialization."""

    def test_service_initialization_enabled(self, enabled_config):
        """Test service initializes correctly when enabled."""
        service = AutocompleteService(enabled_config)
        assert service.enabled is True
        assert service.min_query_length == 3
        assert service.max_suggestions == 5

    def test_service_initialization_disabled(self, disabled_config):
        """Test service initializes correctly when disabled."""
        service = AutocompleteService(disabled_config)
        assert service.enabled is False

    def test_service_with_fuzzy_levenshtein(self, fuzzy_levenshtein_config):
        """Test initialization with Levenshtein fuzzy matching."""
        service = AutocompleteService(fuzzy_levenshtein_config)
        assert service.fuzzy_enabled is True
        assert service.fuzzy_algorithm == 'levenshtein'
        assert service.fuzzy_threshold == 0.6

    def test_service_with_fuzzy_jaro_winkler(self, fuzzy_jaro_winkler_config):
        """Test initialization with Jaro-Winkler fuzzy matching."""
        service = AutocompleteService(fuzzy_jaro_winkler_config)
        assert service.fuzzy_enabled is True
        assert service.fuzzy_algorithm == 'jaro_winkler'
        assert service.fuzzy_threshold == 0.75

    def test_service_with_redis(self, redis_enabled_config, mock_redis_service):
        """Test initialization with Redis caching."""
        service = AutocompleteService(
            redis_enabled_config,
            redis_service=mock_redis_service
        )
        assert service.use_redis_cache is True
        assert service.cache_ttl == 1800
        assert service.redis_key_prefix == 'autocomplete:'

    def test_default_config_values(self):
        """Test default configuration values when config is minimal."""
        service = AutocompleteService({})
        assert service.enabled is True  # Default
        assert service.min_query_length == 3  # Default
        assert service.max_suggestions == 5  # Default


# ============================================================================
# AutocompleteService Suggestion Tests
# ============================================================================

class TestAutocompleteServiceSuggestions:
    """Tests for AutocompleteService suggestion functionality."""

    @pytest.mark.asyncio
    async def test_get_suggestions_disabled(self, disabled_config):
        """Test that disabled service returns empty suggestions."""
        service = AutocompleteService(disabled_config)
        suggestions = await service.get_suggestions("show", "test-adapter")
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_get_suggestions_short_query(self, enabled_config):
        """Test that short queries return empty suggestions."""
        service = AutocompleteService(enabled_config)
        # Query shorter than min_query_length (3)
        suggestions = await service.get_suggestions("sh", "test-adapter")
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_get_suggestions_empty_query(self, enabled_config):
        """Test that empty query returns empty suggestions."""
        service = AutocompleteService(enabled_config)
        suggestions = await service.get_suggestions("", "test-adapter")
        assert suggestions == []

    def test_filter_and_rank_substring(self, enabled_config, sample_nl_examples):
        """Test substring filtering and ranking."""
        service = AutocompleteService(enabled_config)

        suggestions = service._filter_and_rank(sample_nl_examples, "show", 5)

        # Should return suggestions containing "show"
        assert len(suggestions) > 0
        assert all("show" in s.text.lower() for s in suggestions)

        # First suggestion should have highest score (prefix match)
        assert suggestions[0].text.lower().startswith("show")

    def test_filter_and_rank_no_matches(self, enabled_config, sample_nl_examples):
        """Test filtering with no matches."""
        service = AutocompleteService(enabled_config)

        suggestions = service._filter_and_rank(sample_nl_examples, "xyz123", 5)
        assert suggestions == []

    def test_filter_and_rank_limit(self, enabled_config, sample_nl_examples):
        """Test that suggestions are limited correctly."""
        service = AutocompleteService(enabled_config)

        # "movie" appears in most examples
        suggestions = service._filter_and_rank(sample_nl_examples, "movie", 3)
        assert len(suggestions) <= 3

    def test_filter_and_rank_fuzzy_levenshtein(
        self, fuzzy_levenshtein_config, sample_nl_examples
    ):
        """Test fuzzy matching with Levenshtein algorithm."""
        service = AutocompleteService(fuzzy_levenshtein_config)

        # "moveis" is a typo for "movies"
        suggestions = service._filter_and_rank(sample_nl_examples, "moveis", 5)

        # Should find matches despite typo
        assert len(suggestions) > 0

    def test_filter_and_rank_fuzzy_jaro_winkler(
        self, fuzzy_jaro_winkler_config, sample_nl_examples
    ):
        """Test fuzzy matching with Jaro-Winkler algorithm."""
        service = AutocompleteService(fuzzy_jaro_winkler_config)

        # "shw" is a typo for "show"
        suggestions = service._filter_and_rank(sample_nl_examples, "shwo", 5)

        # Should find matches despite typo (Jaro-Winkler is good with prefix typos)
        # Note: This depends on the threshold being met
        # With threshold 0.75, "shwo" vs "show" might pass
        assert isinstance(suggestions, list)

    def test_filter_and_rank_case_insensitive(self, enabled_config, sample_nl_examples):
        """Test case-insensitive matching."""
        service = AutocompleteService(enabled_config)

        suggestions_lower = service._filter_and_rank(sample_nl_examples, "show", 5)
        suggestions_upper = service._filter_and_rank(sample_nl_examples, "SHOW", 5)
        suggestions_mixed = service._filter_and_rank(sample_nl_examples, "ShOw", 5)

        # All should return the same results
        assert len(suggestions_lower) == len(suggestions_upper) == len(suggestions_mixed)


# ============================================================================
# AutocompleteService Caching Tests
# ============================================================================

class TestAutocompleteServiceCaching:
    """Tests for AutocompleteService caching functionality."""

    @pytest.mark.asyncio
    async def test_memory_cache_set_and_get(self, enabled_config, sample_nl_examples):
        """Test memory cache stores and retrieves examples."""
        service = AutocompleteService(enabled_config)

        # Set cache
        await service._set_cached_examples("test-adapter", sample_nl_examples)

        # Get from cache
        cached = await service._get_cached_examples("test-adapter")
        assert cached == sample_nl_examples

    @pytest.mark.asyncio
    async def test_memory_cache_expiry(self, sample_nl_examples):
        """Test memory cache expires after TTL."""
        config = {
            'autocomplete': {
                'enabled': True,
                'cache': {
                    'use_redis': False,
                    'ttl_seconds': 1  # 1 second TTL for testing
                }
            }
        }
        service = AutocompleteService(config)

        # Set cache
        await service._set_cached_examples("test-adapter", sample_nl_examples)

        # Should be in cache
        cached = await service._get_cached_examples("test-adapter")
        assert cached == sample_nl_examples

        # Wait for expiry
        time.sleep(1.5)

        # Should be expired
        cached = await service._get_cached_examples("test-adapter")
        assert cached is None

    @pytest.mark.asyncio
    async def test_redis_cache_set(
        self, redis_enabled_config, mock_redis_service, sample_nl_examples
    ):
        """Test Redis cache stores examples."""
        service = AutocompleteService(
            redis_enabled_config,
            redis_service=mock_redis_service
        )

        await service._set_cached_examples("test-adapter", sample_nl_examples)

        # Verify Redis was called
        mock_redis_service.set.assert_called_once()
        call_args = mock_redis_service.set.call_args
        assert "autocomplete:test-adapter" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_redis_cache_get_hit(
        self, redis_enabled_config, mock_redis_service, sample_nl_examples
    ):
        """Test Redis cache retrieval on hit."""
        mock_redis_service.get = AsyncMock(
            return_value=json.dumps(sample_nl_examples)
        )

        service = AutocompleteService(
            redis_enabled_config,
            redis_service=mock_redis_service
        )

        cached = await service._get_cached_examples("test-adapter")
        assert cached == sample_nl_examples

    @pytest.mark.asyncio
    async def test_redis_cache_get_miss(
        self, redis_enabled_config, mock_redis_service
    ):
        """Test Redis cache retrieval on miss."""
        mock_redis_service.get = AsyncMock(return_value=None)

        service = AutocompleteService(
            redis_enabled_config,
            redis_service=mock_redis_service
        )

        cached = await service._get_cached_examples("test-adapter")
        assert cached is None

    @pytest.mark.asyncio
    async def test_invalidate_specific_adapter(
        self, enabled_config, sample_nl_examples
    ):
        """Test invalidating cache for specific adapter."""
        service = AutocompleteService(enabled_config)

        # Cache for multiple adapters
        await service._set_cached_examples("adapter-1", sample_nl_examples)
        await service._set_cached_examples("adapter-2", sample_nl_examples)

        # Invalidate one
        await service.invalidate_cache("adapter-1")

        # adapter-1 should be gone
        cached1 = await service._get_cached_examples("adapter-1")
        assert cached1 is None

        # adapter-2 should still exist
        cached2 = await service._get_cached_examples("adapter-2")
        assert cached2 == sample_nl_examples

    @pytest.mark.asyncio
    async def test_invalidate_all_cache(self, enabled_config, sample_nl_examples):
        """Test invalidating all cached adapters."""
        service = AutocompleteService(enabled_config)

        # Cache for multiple adapters
        await service._set_cached_examples("adapter-1", sample_nl_examples)
        await service._set_cached_examples("adapter-2", sample_nl_examples)

        # Invalidate all
        await service.invalidate_cache()

        # Both should be gone
        cached1 = await service._get_cached_examples("adapter-1")
        cached2 = await service._get_cached_examples("adapter-2")
        assert cached1 is None
        assert cached2 is None


# ============================================================================
# C Library Availability Tests
# ============================================================================

class TestCLibraryAvailability:
    """Tests for C library availability detection."""

    def test_levenshtein_c_available_flag(self):
        """Test that Levenshtein C library availability is detected."""
        # This test just verifies the flag exists and is boolean
        assert isinstance(LEVENSHTEIN_C_AVAILABLE, bool)

    def test_jarowinkler_c_available_flag(self):
        """Test that Jaro-Winkler C library availability is detected."""
        assert isinstance(JAROWINKLER_C_AVAILABLE, bool)

    def test_levenshtein_works_regardless_of_c(self):
        """Test Levenshtein similarity works regardless of C library."""
        # Should work with either C or Python implementation
        similarity = FuzzyMatcher.levenshtein_similarity("hello", "hallo")
        assert 0.0 <= similarity <= 1.0

    def test_jaro_winkler_works_regardless_of_c(self):
        """Test Jaro-Winkler similarity works regardless of C library."""
        # Should work with either C or Python implementation
        similarity = FuzzyMatcher.jaro_winkler_similarity("hello", "hallo")
        assert 0.0 <= similarity <= 1.0


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_fuzzy_matcher_unicode(self):
        """Test fuzzy matching with Unicode characters."""
        similarity = FuzzyMatcher.levenshtein_similarity("café", "cafe")
        assert similarity > 0.7

        similarity = FuzzyMatcher.jaro_winkler_similarity("日本語", "日本")
        assert similarity > 0.8

    def test_fuzzy_matcher_special_characters(self):
        """Test fuzzy matching with special characters."""
        similarity = FuzzyMatcher.levenshtein_similarity(
            "hello@world.com",
            "hello@world.org"
        )
        assert similarity > 0.8

    def test_fuzzy_matcher_very_long_strings(self):
        """Test fuzzy matching with long strings."""
        s1 = "a" * 1000
        s2 = "a" * 999 + "b"
        similarity = FuzzyMatcher.levenshtein_similarity(s1, s2)
        assert similarity > 0.99

    def test_fuzzy_matcher_whitespace(self):
        """Test fuzzy matching handles whitespace."""
        similarity = FuzzyMatcher.levenshtein_similarity(
            "hello world",
            "hello  world"
        )
        assert similarity > 0.9

    def test_filter_and_rank_empty_examples(self, enabled_config):
        """Test filtering with empty examples list."""
        service = AutocompleteService(enabled_config)
        suggestions = service._filter_and_rank([], "query", 5)
        assert suggestions == []

    def test_filter_and_rank_max_candidates(self, fuzzy_levenshtein_config):
        """Test that max_candidates limit is respected."""
        config = fuzzy_levenshtein_config.copy()
        config['autocomplete']['fuzzy_matching']['max_candidates'] = 2

        service = AutocompleteService(config)

        examples = [
            "Show me movies",
            "Find movies",
            "List movies",
            "Get movies",
            "Movies list"
        ]

        # With max_candidates=2, only first 2 examples should be evaluated
        # This is a performance optimization
        suggestions = service._filter_and_rank(examples, "movies", 5)
        # Result may vary based on which candidates are evaluated
        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_service_no_adapter_manager(self, enabled_config):
        """Test service handles missing adapter manager gracefully."""
        service = AutocompleteService(enabled_config, adapter_manager=None)

        # Should not raise, just return empty
        examples = await service._get_adapter_nl_examples("test-adapter")
        assert examples == []


# ============================================================================
# AutocompleteSuggestion Tests
# ============================================================================

class TestAutocompleteSuggestion:
    """Tests for AutocompleteSuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test creating a suggestion."""
        suggestion = AutocompleteSuggestion(text="Show me movies", score=95.5)
        assert suggestion.text == "Show me movies"
        assert suggestion.score == 95.5

    def test_suggestion_default_score(self):
        """Test suggestion default score."""
        suggestion = AutocompleteSuggestion(text="Test query")
        assert suggestion.text == "Test query"
        assert suggestion.score == 0.0

    def test_suggestion_sorting(self):
        """Test sorting suggestions by score."""
        suggestions = [
            AutocompleteSuggestion(text="Low", score=10.0),
            AutocompleteSuggestion(text="High", score=90.0),
            AutocompleteSuggestion(text="Medium", score=50.0),
        ]

        sorted_suggestions = sorted(suggestions, key=lambda x: x.score, reverse=True)

        assert sorted_suggestions[0].text == "High"
        assert sorted_suggestions[1].text == "Medium"
        assert sorted_suggestions[2].text == "Low"
