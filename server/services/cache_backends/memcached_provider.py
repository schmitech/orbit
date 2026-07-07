"""
Memcached Cache Provider
========================

Memcached-backed implementation of CacheProvider, using aiomcache. A lighter-weight
alternative to Redis for deployments without access to a Redis cluster.

Known limitations vs. Redis (inherent to the Memcached protocol, not this client):
- No key enumeration/pattern matching: clear_by_pattern() always flushes the entire
  cache (flush_all), regardless of the requested pattern.
- No TTL introspection: ttl() always returns -1 (unknown) rather than remaining seconds.
- No atomic multi-key transactions: increment_with_ttl() uses incr, falling back to
  add() when the counter doesn't exist yet. This has a small race window on first
  creation under concurrent callers - acceptable for rate limiting/quota bookkeeping,
  which self-corrects on the next window.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

try:
    import aiomcache
    AIOMCACHE_AVAILABLE = True
except ImportError:
    AIOMCACHE_AVAILABLE = False

from .base import CacheProvider, CircuitBreaker, is_cache_master_enabled

logger = logging.getLogger(__name__)


def _encode(value: str) -> bytes:
    return value.encode("utf-8")


def _decode(value: Optional[bytes]) -> Optional[str]:
    return value.decode("utf-8") if value is not None else None


class MemcachedCacheProvider(CacheProvider):
    """Cache provider backed by Memcached, with graceful fallback if unavailable."""

    _instances: Dict[str, 'MemcachedCacheProvider'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any]):
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new Memcached cache provider instance for: {cache_key}")
            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        memcached_config = config.get('internal_services', {}).get('memcached', {})
        return f"{memcached_config.get('host', 'localhost')}:{memcached_config.get('port', 11211)}"

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached Memcached provider instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()

    def __init__(self, config: Dict[str, Any]):
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config
        self.memcached_config = config.get('internal_services', {}).get('memcached', {})
        self.enabled = (
            is_cache_master_enabled(config) and self.memcached_config.get('enabled', False) and AIOMCACHE_AVAILABLE
        )
        self.client: Optional["aiomcache.Client"] = None
        self.initialized = False
        self.default_ttl = int(self.memcached_config.get('ttl', 3600))

        max_failures = self.memcached_config.get('max_consecutive_failures', 5)
        recovery_timeout = self.memcached_config.get('circuit_recovery_timeout', 30)
        self._circuit_breaker = CircuitBreaker(
            max_failures=max_failures,
            recovery_timeout=recovery_timeout
        )

        self._singleton_initialized = True

    def _is_available(self) -> bool:
        return self.enabled and self.client is not None and not self._circuit_breaker.is_open

    def _handle_error(self, operation: str, error: Exception) -> None:
        self._circuit_breaker.record_failure()
        if self._circuit_breaker.is_open:
            logger.warning(f"Memcached circuit breaker open after {operation} error: {error}")
        else:
            logger.debug(f"Memcached error during {operation}: {error}")

    async def initialize(self) -> bool:
        if self.initialized:
            return True

        if not self.enabled:
            if not AIOMCACHE_AVAILABLE:
                logger.warning("Memcached provider selected but aiomcache is not installed")
            else:
                logger.warning("Memcached is not enabled in configuration")
            return False

        try:
            host = self.memcached_config.get('host', 'localhost')
            port = int(self.memcached_config.get('port', 11211))
            pool_size = int(self.memcached_config.get('pool_size', 20))

            self.client = aiomcache.Client(host, port, pool_size=pool_size)
            await self.client.version()
            logger.info(f"Successfully connected to Memcached at {host}:{port}")

            cache_config = self.config.get("internal_services", {}).get("cache", {})
            if cache_config.get("clear_cache_on_startup", True):
                await self.clear_all_application_cache()
            else:
                logger.debug("Cache clearing on startup is disabled")

            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Memcached: {str(e)}")
            self.enabled = False
            self.client = None
            self.initialized = False
            return False

    async def get(self, key: str) -> Optional[str]:
        if not self._is_available():
            return None
        try:
            result = _decode(await self.client.get(_encode(key)))
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error getting key {key} from Memcached: {str(e)}")
            self._handle_error("get", e)
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        if not self._is_available():
            return False
        try:
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            result = await self.client.set(_encode(key), _encode(value), exptime=ttl_to_use)
            self._circuit_breaker.record_success()
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting key {key} in Memcached: {str(e)}")
            self._handle_error("set", e)
            return False

    async def delete(self, *keys: str) -> int:
        if not self._is_available():
            return 0
        try:
            deleted = 0
            for key in keys:
                if await self.client.delete(_encode(key)):
                    deleted += 1
            self._circuit_breaker.record_success()
            return deleted
        except Exception as e:
            logger.error(f"Error deleting keys {keys} from Memcached: {str(e)}")
            self._handle_error("delete", e)
            return 0

    async def exists(self, key: str) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self.client.get(_encode(key))
            self._circuit_breaker.record_success()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking if key {key} exists in Memcached: {str(e)}")
            self._handle_error("exists", e)
            return False

    async def ttl(self, key: str) -> int:
        """Memcached has no TTL introspection command; -1 means 'unknown', -2 means 'missing'."""
        if not self._is_available():
            return -2
        try:
            exists = await self.exists(key)
            return -1 if exists else -2
        except Exception as e:
            self._handle_error("ttl", e)
            return -2

    async def expire(self, key: str, seconds: int) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self.client.touch(_encode(key), seconds)
            self._circuit_breaker.record_success()
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting expiration for key {key} in Memcached: {str(e)}")
            self._handle_error("expire", e)
            return False

    async def mget(self, *keys: str) -> List[Optional[str]]:
        if not self._is_available() or not keys:
            return [None] * len(keys)
        try:
            results = await self.client.multi_get(*[_encode(k) for k in keys])
            self._circuit_breaker.record_success()
            return [_decode(r) for r in results]
        except Exception as e:
            logger.error(f"Error in mget for {len(keys)} keys: {str(e)}")
            self._handle_error("mget", e)
            return [None] * len(keys)

    async def mset(self, mapping: Dict[str, str]) -> bool:
        if not self._is_available() or not mapping:
            return False
        try:
            for key, value in mapping.items():
                await self.client.set(_encode(key), _encode(value), exptime=self.default_ttl)
            self._circuit_breaker.record_success()
            return True
        except Exception as e:
            logger.error(f"Error in mset for {len(mapping)} keys: {str(e)}")
            self._handle_error("mset", e)
            return False

    async def set_if_not_exists(self, key: str, value: str, ttl: int) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self.client.add(_encode(key), _encode(value), exptime=ttl)
            self._circuit_breaker.record_success()
            return bool(result)
        except Exception as e:
            logger.error(f"Error in set_if_not_exists for key {key} in Memcached: {str(e)}")
            self._handle_error("set_if_not_exists", e)
            return False

    async def increment_with_ttl(self, key: str, ttl: int, amount: int = 1) -> int:
        if not self._is_available():
            return 0
        try:
            key_bytes = _encode(key)

            # aiomcache's incr() raises ClientException (not None) on NOT_FOUND,
            # despite what its docstring says - treat that as "key missing".
            try:
                count = await self.client.incr(key_bytes, amount)
                if count is not None:
                    self._circuit_breaker.record_success()
                    return count
            except aiomcache.exceptions.ClientException:
                pass

            # Key doesn't exist yet - create it. Small race window if another caller
            # creates it concurrently; retry incr once in that case.
            created = await self.client.add(key_bytes, _encode(str(amount)), exptime=ttl)
            if created:
                self._circuit_breaker.record_success()
                return amount

            try:
                count = await self.client.incr(key_bytes, amount)
            except aiomcache.exceptions.ClientException:
                count = None
            self._circuit_breaker.record_success()
            return count if count is not None else amount
        except Exception as e:
            logger.error(f"Error in increment_with_ttl for key {key} in Memcached: {str(e)}")
            self._handle_error("increment_with_ttl", e)
            return 0

    async def clear_by_pattern(self, pattern: str, description: str = "") -> int:
        """Memcached has no key enumeration - flushes the entire cache instead."""
        if not self._is_available():
            return 0
        try:
            logger.warning(
                f"Memcached provider cannot selectively clear pattern '{pattern}' "
                f"({description or 'unspecified'}) - flushing entire cache instead"
            )
            await self.client.flush_all()
            self._circuit_breaker.record_success()
            return -1  # unknown count; entire cache was flushed
        except Exception as e:
            logger.error(f"Error flushing Memcached: {str(e)}")
            self._handle_error("clear_by_pattern", e)
            return 0

    async def clear_all_application_cache(self) -> Dict[str, int]:
        """Single flush_all instead of looping per-pattern (Memcached has no pattern matching)."""
        if not self._is_available():
            logger.debug("Memcached not available, skipping cache clearing")
            return {}
        try:
            await self.client.flush_all()
            self._circuit_breaker.record_success()
            logger.info("Flushed entire Memcached cache on startup")
            return {"flushed_all": -1}
        except Exception as e:
            logger.warning(f"Failed to flush Memcached on startup: {str(e)}")
            return {"flushed_all": 0}

    def get_health_stats(self) -> Dict[str, Any]:
        return {
            "provider": "memcached",
            "enabled": self.enabled,
            "initialized": self.initialized,
            "circuit_breaker": {
                "state": self._circuit_breaker.state,
                "failure_count": self._circuit_breaker.failure_count,
                "max_failures": self._circuit_breaker.max_failures,
            },
            "pool": {
                "max_connections": int(self.memcached_config.get('pool_size', 20)),
            },
        }

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
            self.initialized = False
