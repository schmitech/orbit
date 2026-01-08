"""
Autocomplete Service
====================

This service provides query autocomplete suggestions based on nl_examples
from intent adapter templates.

Features:
- Redis caching for distributed deployments (with in-memory fallback)
- Fuzzy matching algorithms: substring, Levenshtein, Jaro-Winkler
- Uses fast C libraries (Levenshtein, jarowinkler) when available
- Falls back to pure Python implementations if C libraries not installed
- Configurable via config.yaml
"""

import logging
import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import fast C-based libraries, fall back to pure Python if not available
try:
    from Levenshtein import ratio as levenshtein_ratio
    LEVENSHTEIN_C_AVAILABLE = True
    logger.debug("Using C-based Levenshtein library for autocomplete")
except ImportError:
    LEVENSHTEIN_C_AVAILABLE = False
    logger.debug("C-based Levenshtein not available, using pure Python fallback")

try:
    from jarowinkler import jarowinkler_similarity as jw_similarity
    JAROWINKLER_C_AVAILABLE = True
    logger.debug("Using C-based jarowinkler library for autocomplete")
except ImportError:
    JAROWINKLER_C_AVAILABLE = False
    logger.debug("C-based jarowinkler not available, using pure Python fallback")


@dataclass
class AutocompleteSuggestion:
    """Represents an autocomplete suggestion."""
    text: str
    score: float = 0.0


class FuzzyMatcher:
    """
    Provides fuzzy string matching algorithms for autocomplete.

    Supported algorithms:
    - substring: Exact substring matching (fastest)
    - levenshtein: Edit distance based matching (handles typos)
    - jaro_winkler: Optimized for short strings and prefixes
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
            return FuzzyMatcher.levenshtein_distance(s2, s1)

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
        distance = FuzzyMatcher.levenshtein_distance(s1, s2)
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
        making it ideal for autocomplete where users type prefixes.

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
        jaro = FuzzyMatcher.jaro_similarity(s1, s2)

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
    def substring_match(query: str, text: str) -> tuple:
        """
        Check if query is a substring of text and calculate position-based score.

        Args:
            query: The search query
            text: The text to search in

        Returns:
            Tuple of (is_match, score) where score considers position
        """
        query_lower = query.lower()
        text_lower = text.lower()

        if query_lower not in text_lower:
            return (False, 0.0)

        position = text_lower.find(query_lower)

        # Score: higher for prefix matches, lower for later positions
        score = 1.0
        if position == 0:
            score = 1.0  # Perfect prefix match
        else:
            # Penalize based on position
            score = max(0.5, 1.0 - (position * 0.05))

        return (True, score)


class AutocompleteService:
    """
    Service for providing autocomplete suggestions based on template nl_examples.

    This service extracts nl_examples from intent adapter templates and provides
    filtered, ranked suggestions based on user query prefixes.

    Configuration (config.yaml):
        autocomplete:
          enabled: true
          min_query_length: 3
          max_suggestions: 5
          cache:
            use_redis: true
            ttl_seconds: 1800
            redis_key_prefix: "autocomplete:"
          fuzzy_matching:
            enabled: true
            algorithm: "jaro_winkler"
            threshold: 0.75
            max_candidates: 100
    """

    def __init__(
        self,
        config: Dict[str, Any],
        adapter_manager=None,
        redis_service=None
    ):
        """
        Initialize the autocomplete service.

        Args:
            config: Application configuration
            adapter_manager: Reference to DynamicAdapterManager for adapter access
            redis_service: Optional RedisService for distributed caching
        """
        self.config = config
        self.adapter_manager = adapter_manager
        self.redis_service = redis_service

        # Autocomplete configuration
        autocomplete_config = config.get('autocomplete', {})
        self.enabled = autocomplete_config.get('enabled', True)
        self.max_suggestions = autocomplete_config.get('max_suggestions', 5)
        self.min_query_length = autocomplete_config.get('min_query_length', 3)

        # Cache configuration
        cache_config = autocomplete_config.get('cache', {})
        self.use_redis_cache = cache_config.get('use_redis', True)
        self.cache_ttl = cache_config.get('ttl_seconds', 1800)  # 30 minutes
        self.redis_key_prefix = cache_config.get('redis_key_prefix', 'autocomplete:')

        # Fuzzy matching configuration
        fuzzy_config = autocomplete_config.get('fuzzy_matching', {})
        self.fuzzy_enabled = fuzzy_config.get('enabled', False)
        self.fuzzy_algorithm = fuzzy_config.get('algorithm', 'substring')
        self.fuzzy_threshold = fuzzy_config.get('threshold', 0.75)
        self.max_candidates = fuzzy_config.get('max_candidates', 100)

        # In-memory cache fallback: adapter_name -> (timestamp, nl_examples)
        self._memory_cache: Dict[str, tuple] = {}

        # Check if Redis is available when Redis caching is requested
        redis_available = redis_service is not None and getattr(redis_service, 'enabled', False)
        if self.enabled and self.use_redis_cache and not redis_available:
            logger.warning(
                "Autocomplete service is configured to use Redis caching but Redis is disabled. "
                "Falling back to in-memory cache (not suitable for distributed deployments)."
            )

        # Log initialization with library status
        lib_status = []
        if self.fuzzy_enabled:
            if self.fuzzy_algorithm == 'levenshtein':
                lib_status.append(f"levenshtein={'C' if LEVENSHTEIN_C_AVAILABLE else 'Python'}")
            elif self.fuzzy_algorithm == 'jaro_winkler':
                lib_status.append(f"jaro_winkler={'C' if JAROWINKLER_C_AVAILABLE else 'Python'}")

        logger.debug(
            f"AutocompleteService initialized: enabled={self.enabled}, "
            f"redis_cache={self.use_redis_cache}, fuzzy={self.fuzzy_enabled} "
            f"({self.fuzzy_algorithm}, threshold={self.fuzzy_threshold})"
            + (f", libs=[{', '.join(lib_status)}]" if lib_status else "")
        )

    def _get_redis_key(self, adapter_name: str) -> str:
        """Generate Redis cache key for an adapter's nl_examples."""
        return f"{self.redis_key_prefix}{adapter_name}"

    async def _get_cached_examples(self, adapter_name: str) -> Optional[List[str]]:
        """
        Get cached nl_examples from Redis or memory cache.

        Args:
            adapter_name: Name of the adapter

        Returns:
            Cached examples list or None if not cached/expired
        """
        # Try Redis first if enabled and available
        if self.use_redis_cache and self.redis_service and self.redis_service.enabled:
            try:
                redis_key = self._get_redis_key(adapter_name)
                cached_json = await self.redis_service.get(redis_key)
                if cached_json:
                    examples = json.loads(cached_json)
                    logger.debug(f"Redis cache hit for autocomplete: {adapter_name}")
                    return examples
            except Exception as e:
                logger.warning(f"Redis cache read error for {adapter_name}: {e}")

        # Fallback to memory cache
        if adapter_name in self._memory_cache:
            cached_time, cached_examples = self._memory_cache[adapter_name]
            if time.time() - cached_time < self.cache_ttl:
                logger.debug(f"Memory cache hit for autocomplete: {adapter_name}")
                return cached_examples
            else:
                # Expired, remove from memory cache
                del self._memory_cache[adapter_name]

        return None

    async def _set_cached_examples(self, adapter_name: str, examples: List[str]) -> None:
        """
        Cache nl_examples in Redis and/or memory cache.

        Args:
            adapter_name: Name of the adapter
            examples: List of nl_example strings to cache
        """
        # Store in Redis if enabled and available
        if self.use_redis_cache and self.redis_service and self.redis_service.enabled:
            try:
                redis_key = self._get_redis_key(adapter_name)
                await self.redis_service.set(
                    redis_key,
                    json.dumps(examples),
                    ttl=self.cache_ttl
                )
                logger.debug(f"Cached {len(examples)} examples in Redis for {adapter_name}")
            except Exception as e:
                logger.warning(f"Redis cache write error for {adapter_name}: {e}")

        # Always update memory cache as fallback
        self._memory_cache[adapter_name] = (time.time(), examples)

    async def get_suggestions(
        self,
        query: str,
        adapter_name: str,
        limit: int = 5
    ) -> List[AutocompleteSuggestion]:
        """
        Get autocomplete suggestions for a query prefix.

        Args:
            query: The query prefix to match against
            adapter_name: Name of the adapter to get suggestions for
            limit: Maximum number of suggestions to return

        Returns:
            List of AutocompleteSuggestion objects
        """
        start_time = time.time()
        logger.debug(
            f"[Autocomplete] get_suggestions called: query='{query}', "
            f"adapter={adapter_name}, limit={limit}"
        )

        if not self.enabled:
            logger.debug("[Autocomplete] Service disabled, returning empty")
            return []

        if not query or len(query) < self.min_query_length:
            logger.debug(
                f"[Autocomplete] Query too short ({len(query) if query else 0} < "
                f"{self.min_query_length}), returning empty"
            )
            return []

        try:
            # Get nl_examples for the adapter (from cache or fresh)
            examples = await self._get_adapter_nl_examples(adapter_name)

            if not examples:
                logger.debug(f"[Autocomplete] No examples found for adapter {adapter_name}")
                return []

            logger.debug(
                f"[Autocomplete] Found {len(examples)} nl_examples for {adapter_name}"
            )

            # Filter and rank suggestions
            suggestions = self._filter_and_rank(examples, query, limit)

            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(
                f"[Autocomplete] Returning {len(suggestions)} suggestions "
                f"for '{query}' in {elapsed_ms:.2f}ms"
            )

            return suggestions

        except Exception as e:
            logger.warning(f"[Autocomplete] Error getting suggestions: {e}")
            return []

    async def _get_adapter_nl_examples(self, adapter_name: str) -> List[str]:
        """
        Fetch and cache nl_examples from an adapter's templates.

        Args:
            adapter_name: Name of the adapter

        Returns:
            List of nl_example strings
        """
        logger.debug(f"[Autocomplete] Fetching nl_examples for adapter: {adapter_name}")

        # Check cache first
        cached = await self._get_cached_examples(adapter_name)
        if cached is not None:
            logger.debug(f"[Autocomplete] Cache hit: {len(cached)} examples for {adapter_name}")
            return cached

        logger.debug(f"[Autocomplete] Cache miss for {adapter_name}, fetching from adapter")
        examples = []

        try:
            if not self.adapter_manager:
                logger.warning("[Autocomplete] No adapter manager available")
                return []

            # Get adapter config to check capability
            adapter_config = self.adapter_manager.config_manager.get(adapter_name)
            if not adapter_config:
                logger.debug(f"[Autocomplete] Adapter config not found: {adapter_name}")
                return []

            # Check if adapter supports autocomplete
            from adapters.capabilities import AdapterCapabilities
            capabilities = AdapterCapabilities.from_config(adapter_config)

            if not capabilities.supports_autocomplete:
                logger.debug(
                    f"[Autocomplete] Adapter {adapter_name} does not support autocomplete "
                    "(supports_autocomplete=false)"
                )
                return []

            logger.debug(f"[Autocomplete] Adapter {adapter_name} supports autocomplete")

            # Get the adapter
            adapter = await self.adapter_manager.get_adapter(adapter_name)
            if not adapter:
                logger.debug(f"[Autocomplete] Could not get adapter instance: {adapter_name}")
                return []

            # Check if this is a composite adapter
            if hasattr(adapter, 'child_adapter_names') and adapter.child_adapter_names:
                logger.debug(
                    f"[Autocomplete] {adapter_name} is composite with "
                    f"{len(adapter.child_adapter_names)} children"
                )
                # Aggregate from child adapters
                examples = await self._get_composite_examples(adapter)
            else:
                # Get examples from single adapter
                examples = self._extract_examples_from_adapter(adapter)

            # Cache the examples
            await self._set_cached_examples(adapter_name, examples)

            logger.debug(
                f"[Autocomplete] Fetched and cached {len(examples)} nl_examples "
                f"for {adapter_name}"
            )

        except Exception as e:
            logger.warning(f"[Autocomplete] Error fetching nl_examples for {adapter_name}: {e}")

        return examples

    def _extract_examples_from_adapter(self, adapter) -> List[str]:
        """
        Extract nl_examples from a single adapter's templates.

        Args:
            adapter: The adapter instance

        Returns:
            List of nl_example strings
        """
        examples = []

        # Try to get domain_adapter (for intent retrievers)
        domain_adapter = getattr(adapter, 'domain_adapter', None)

        if domain_adapter and hasattr(domain_adapter, 'get_all_templates'):
            templates = domain_adapter.get_all_templates()
            template_count = len(templates) if templates else 0
            logger.debug(
                f"[Autocomplete] Extracting from {template_count} templates "
                f"via domain_adapter"
            )
            for template in templates:
                nl_examples = template.get('nl_examples', [])
                if isinstance(nl_examples, list):
                    examples.extend(nl_examples)
            logger.debug(f"[Autocomplete] Extracted {len(examples)} nl_examples from templates")
        else:
            logger.debug("[Autocomplete] No domain_adapter or get_all_templates method found")

        return examples

    async def _get_composite_examples(self, adapter) -> List[str]:
        """
        Aggregate nl_examples from a composite adapter's children.

        Args:
            adapter: The composite adapter instance

        Returns:
            Deduplicated list of nl_example strings
        """
        all_examples = []

        child_adapter_names = getattr(adapter, 'child_adapter_names', [])

        for child_name in child_adapter_names:
            try:
                # Check if child supports autocomplete
                child_config = self.adapter_manager.config_manager.get(child_name)
                if not child_config:
                    continue

                from adapters.capabilities import AdapterCapabilities
                child_capabilities = AdapterCapabilities.from_config(child_config)

                if not child_capabilities.supports_autocomplete:
                    continue

                # Get child adapter
                child_adapter = await self.adapter_manager.get_adapter(child_name)
                if child_adapter:
                    child_examples = self._extract_examples_from_adapter(child_adapter)
                    all_examples.extend(child_examples)

            except Exception as e:
                logger.warning(f"Error getting examples from child adapter {child_name}: {e}")

        # Deduplicate while preserving order
        seen = set()
        unique_examples = []
        for ex in all_examples:
            if ex not in seen:
                seen.add(ex)
                unique_examples.append(ex)

        return unique_examples

    def _filter_and_rank(
        self,
        examples: List[str],
        query: str,
        limit: int
    ) -> List[AutocompleteSuggestion]:
        """
        Filter examples by query match and rank by relevance.

        Uses configured matching algorithm (substring, levenshtein, or jaro_winkler).

        Args:
            examples: List of nl_example strings
            query: The query prefix to match
            limit: Maximum number of suggestions

        Returns:
            Sorted list of AutocompleteSuggestion objects
        """
        algorithm = self.fuzzy_algorithm if self.fuzzy_enabled else 'substring'
        logger.debug(
            f"[Autocomplete] Filtering {len(examples)} examples with "
            f"algorithm={algorithm}, query='{query}', limit={limit}"
        )

        query_lower = query.lower().strip()
        scored_examples = []

        # Limit candidates for fuzzy matching (performance guard)
        candidates = examples[:self.max_candidates] if self.fuzzy_enabled else examples
        if len(candidates) < len(examples):
            logger.debug(
                f"[Autocomplete] Limited candidates to {len(candidates)} "
                f"(max_candidates={self.max_candidates})"
            )

        for example in candidates:
            example_lower = example.lower()
            score = 0.0
            is_match = False

            if self.fuzzy_enabled:
                # Use configured fuzzy matching algorithm
                if self.fuzzy_algorithm == 'levenshtein':
                    # For Levenshtein, we match query against each word or the whole string
                    similarity = FuzzyMatcher.levenshtein_similarity(query_lower, example_lower)

                    # Also check if query is a fuzzy prefix of any word
                    words = example_lower.split()
                    for word in words:
                        word_sim = FuzzyMatcher.levenshtein_similarity(query_lower, word[:len(query_lower)])
                        similarity = max(similarity, word_sim * 0.9)  # Slight penalty for word match

                    if similarity >= self.fuzzy_threshold:
                        is_match = True
                        score = similarity * 100
                    # Also include exact substring matches
                    elif query_lower in example_lower:
                        is_match = True
                        position = example_lower.find(query_lower)
                        score = 80 if position == 0 else 60 - position * 0.5

                elif self.fuzzy_algorithm == 'jaro_winkler':
                    # Jaro-Winkler is great for prefix matching
                    similarity = FuzzyMatcher.jaro_winkler_similarity(query_lower, example_lower)

                    # Also check against words for partial matching
                    words = example_lower.split()
                    for word in words:
                        word_sim = FuzzyMatcher.jaro_winkler_similarity(query_lower, word)
                        similarity = max(similarity, word_sim * 0.9)

                    if similarity >= self.fuzzy_threshold:
                        is_match = True
                        score = similarity * 100
                    # Also include exact substring matches
                    elif query_lower in example_lower:
                        is_match = True
                        position = example_lower.find(query_lower)
                        score = 80 if position == 0 else 60 - position * 0.5

                else:  # Default to substring
                    is_match, score = FuzzyMatcher.substring_match(query_lower, example_lower)
                    score = score * 100

            else:
                # Simple substring matching (original behavior)
                if query_lower in example_lower:
                    is_match = True

                    # Strong bonus for prefix match
                    if example_lower.startswith(query_lower):
                        score = 100.0
                    else:
                        position = example_lower.find(query_lower)
                        score = 50.0 - position * 0.5

            if is_match:
                # Slight preference for shorter suggestions (more concise)
                score -= len(example) * 0.05

                scored_examples.append(AutocompleteSuggestion(
                    text=example,
                    score=score
                ))

        # Sort by score descending
        scored_examples.sort(key=lambda x: x.score, reverse=True)

        result = scored_examples[:limit]
        logger.debug(
            f"[Autocomplete] Found {len(scored_examples)} matches, "
            f"returning top {len(result)}"
        )
        if result:
            top_scores = [f"{s.score:.1f}" for s in result[:3]]
            logger.debug(f"[Autocomplete] Top scores: [{', '.join(top_scores)}]")

        return result

    async def invalidate_cache(self, adapter_name: Optional[str] = None) -> None:
        """
        Invalidate cached nl_examples.

        Args:
            adapter_name: Specific adapter to invalidate, or None for all
        """
        if adapter_name:
            # Invalidate specific adapter
            if adapter_name in self._memory_cache:
                del self._memory_cache[adapter_name]

            # Also invalidate in Redis
            if self.use_redis_cache and self.redis_service and self.redis_service.enabled:
                try:
                    redis_key = self._get_redis_key(adapter_name)
                    await self.redis_service.delete(redis_key)
                except Exception as e:
                    logger.warning(f"Failed to invalidate Redis cache for {adapter_name}: {e}")

            logger.debug(f"Invalidated autocomplete cache for {adapter_name}")
        else:
            # Invalidate all
            self._memory_cache.clear()

            # Clear Redis cache (scan for keys with prefix)
            if self.use_redis_cache and self.redis_service and self.redis_service.enabled:
                try:
                    # Use the redis client directly for pattern deletion
                    if self.redis_service.client:
                        cursor = 0
                        keys_deleted = 0
                        while True:
                            cursor, keys = await self.redis_service.client.scan(
                                cursor,
                                match=f"{self.redis_key_prefix}*",
                                count=100
                            )
                            if keys:
                                await self.redis_service.delete(*keys)
                                keys_deleted += len(keys)
                            if cursor == 0:
                                break
                        if keys_deleted > 0:
                            logger.debug(f"Deleted {keys_deleted} autocomplete cache keys from Redis")
                except Exception as e:
                    logger.warning(f"Failed to clear Redis autocomplete cache: {e}")

            logger.debug("Invalidated all autocomplete caches")
