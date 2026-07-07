"""
Cache Provider Base
====================

Defines the CacheProvider interface that every cache backend (Redis, Memcached, ...)
must implement, so callers depend on generic caching semantics instead of a specific
vendor's client API.

To add a new backend:
1. Implement a CacheProvider subclass in its own module (see redis_provider.py /
   memcached_provider.py for reference).
2. Register it in factory.py's provider map.
3. Add its connection settings under internal_services.<name> in config.yaml.
"""

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache key patterns cleared on startup / full flush, shared by all providers.
APPLICATION_CACHE_PATTERNS = [
    ("prompt:*", "prompt cache"),
    ("session:*", "session data"),
    ("thread:*", "thread data"),
    ("thread_dataset:*", "thread dataset data"),
    ("rate_limit:*", "rate limit data"),
    ("cache:*", "general cache"),
    ("qcache:*", "query burst cache"),
    ("temp:*", "temporary data"),
]


class CircuitBreaker:
    """Simple circuit breaker to avoid permanently disabling a cache backend on transient failures."""

    def __init__(self, max_failures: int = 5, recovery_timeout: int = 30):
        self._max_failures = max_failures
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._state = "closed"  # closed = healthy, open = tripped
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._state == "open":
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = "half_open"
                    logger.info("Circuit breaker entering half-open state, will attempt recovery")
                    return False
                return True
            return False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def max_failures(self) -> int:
        return self._max_failures

    def record_success(self) -> None:
        with self._lock:
            if self._state == "half_open":
                logger.info("Circuit breaker recovered, closing circuit")
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._max_failures:
                if self._state != "open":
                    logger.warning(
                        f"Circuit breaker opened after {self._failure_count} consecutive failures. "
                        f"Will retry after {self._recovery_timeout}s"
                    )
                self._state = "open"


class CacheProvider(ABC):
    """Common interface for all cache backends."""

    enabled: bool
    initialized: bool
    default_ttl: int

    @abstractmethod
    async def initialize(self) -> bool:
        """Establish the connection to the backend. Returns True on success."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the connection to the backend."""
        ...

    async def aclose(self) -> None:
        """Alias for close() to maintain compatibility with generic shutdown helpers."""
        await self.close()

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        ...

    @abstractmethod
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        ...

    @abstractmethod
    async def delete(self, *keys: str) -> int:
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    async def ttl(self, key: str) -> int:
        ...

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> bool:
        ...

    @abstractmethod
    async def mget(self, *keys: str) -> List[Optional[str]]:
        ...

    @abstractmethod
    async def mset(self, mapping: Dict[str, str]) -> bool:
        ...

    @abstractmethod
    async def set_if_not_exists(self, key: str, value: str, ttl: int) -> bool:
        """Atomically set key only if it doesn't already exist (used for distributed locks)."""
        ...

    @abstractmethod
    async def increment_with_ttl(self, key: str, ttl: int, amount: int = 1) -> int:
        """Atomically increment a counter, setting its TTL when first created. Returns the new value."""
        ...

    async def check_and_increment(
        self,
        checks: List[Tuple[str, str, int, Optional[int]]],
        amount: int = 1,
    ) -> Tuple[Dict[str, int], Optional[str]]:
        """
        Check multiple counters against per-counter limits and increment ALL of them
        only if none would exceed its limit (a check with limit=None never blocks).

        Args:
            checks: list of (name, key, ttl, limit) tuples. `name` is an arbitrary
                label used as the key in the returned counts dict.
            amount: amount to increment each counter by.

        Returns:
            (counts_by_name, exceeded_name) - counts_by_name always has an entry
            for every check, whether or not one was exceeded. If exceeded_name is
            not None, no counters were incremented and counts_by_name holds the
            *current* (pre-increment) values observed for all of them.

        This default implementation is best-effort, NOT atomic across counters:
        it reads all counters, then increments all of them, so a concurrent caller
        can interleave between the check and the increments and a hard limit can be
        exceeded by a small margin under contention. Override this in providers
        that support real multi-key transactions (see RedisCacheProvider,
        SqliteCacheProvider) for strict atomic enforcement.
        """
        current_counts: Dict[str, int] = {}
        exceeded_name: Optional[str] = None
        for name, key, _ttl, limit in checks:
            current_str = await self.get(key)
            current = int(current_str) if current_str else 0
            current_counts[name] = current
            if exceeded_name is None and limit is not None and current + amount > limit:
                exceeded_name = name

        if exceeded_name is not None:
            return current_counts, exceeded_name

        new_counts: Dict[str, int] = {}
        for name, key, ttl, _limit in checks:
            new_counts[name] = await self.increment_with_ttl(key, ttl, amount)
        return new_counts, None

    @abstractmethod
    async def clear_by_pattern(self, pattern: str, description: str = "") -> int:
        """
        Clear all keys matching a pattern. Backends without key enumeration (e.g. Memcached)
        may degrade this to a full flush - see that provider's docstring for the exact behavior.
        """
        ...

    @abstractmethod
    def get_health_stats(self) -> Dict[str, Any]:
        """Provider-specific health/connection stats for monitoring endpoints."""
        ...

    async def clear_all_application_cache(self) -> Dict[str, int]:
        """Clear all application-related cache keys, e.g. on startup to avoid orphaned data."""
        results = {}
        total_cleared = 0

        for pattern, description in APPLICATION_CACHE_PATTERNS:
            try:
                deleted = await self.clear_by_pattern(pattern, description)
                results[description] = deleted
                total_cleared += deleted
            except Exception as e:
                logger.warning(f"Error clearing {description}: {str(e)}")
                results[description] = 0

        if total_cleared > 0:
            logger.info(f"Cleared {total_cleared} total cache entries on startup")
        else:
            logger.debug("No cache entries found to clear on startup")

        return results

    async def store_json(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Store JSON-serializable data under a key."""
        try:
            json_data = json.dumps(data)
            return await self.set(key, json_data, ttl)
        except Exception as e:
            logger.error(f"Error storing JSON data: {str(e)}")
            return False

    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve and parse JSON data stored under a key."""
        try:
            data = await self.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error getting JSON data: {str(e)}")
            return None
