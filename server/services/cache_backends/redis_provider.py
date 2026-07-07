"""
Redis Cache Provider
====================

Redis-backed implementation of CacheProvider. Features connection pooling,
circuit breaker pattern for resilience, and pipeline support.
"""

import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as redis

from .base import CacheProvider, CircuitBreaker, is_cache_master_enabled

# Optional Redis imports - service will gracefully handle missing dependency
try:
    from redis.asyncio import Redis  # noqa: F401
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Lua script used for atomic single-counter increment-with-ttl-on-create.
_INCREMENT_WITH_TTL_SCRIPT = """
local amount = tonumber(ARGV[2])
local count = redis.call('INCRBY', KEYS[1], amount)
if count == amount then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

# Lua script for atomic multi-counter check-and-increment: KEYS[1..n] are the
# counters; ARGV holds (ttl, limit) pairs per counter (limit=-1 means unlimited)
# followed by a trailing amount. Reads every counter first (so the response
# always has a count for all of them, even when one is rejected), checks
# current+amount against each limit, and only increments any of them if none
# would exceed their limit. Returns {exceeded_index, count1, count2, ...}
# where exceeded_index is 0 if none exceeded (counts are the post-increment
# values) or the 1-based index of the first exceeded counter (counts are the
# pre-increment values observed for ALL counters, not just the failed one).
_CHECK_AND_INCREMENT_SCRIPT = """
local n = #KEYS
local amount = tonumber(ARGV[2 * n + 1])
local counts = {}
local exceeded = 0
for i = 1, n do
    local limit = tonumber(ARGV[(i - 1) * 2 + 2])
    local current = tonumber(redis.call('GET', KEYS[i]) or '0')
    counts[i] = current
    if exceeded == 0 and limit >= 0 and current + amount > limit then
        exceeded = i
    end
end
if exceeded > 0 then
    return {exceeded, unpack(counts)}
end
local newcounts = {}
for i = 1, n do
    local ttl = tonumber(ARGV[(i - 1) * 2 + 1])
    local newcount = redis.call('INCRBY', KEYS[i], amount)
    if newcount == amount then
        redis.call('EXPIRE', KEYS[i], ttl)
    end
    newcounts[i] = newcount
end
return {0, unpack(newcounts)}
"""


class RedisCacheProvider(CacheProvider):
    """Cache provider backed by Redis, with graceful fallback if Redis is unavailable."""

    # Singleton pattern implementation
    _instances: Dict[str, 'RedisCacheProvider'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any]):
        """Create or return existing Redis provider instance based on configuration"""
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new Redis cache provider instance for: {cache_key}")
            else:
                logger.debug(f"Reusing existing Redis cache provider instance for: {cache_key}")
            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        """Create a cache key based on Redis configuration"""
        redis_config = config.get('internal_services', {}).get('redis', {})

        key_parts = [
            redis_config.get('host', 'localhost'),
            str(redis_config.get('port', 6379)),
            str(redis_config.get('db', 0)),
            redis_config.get('username', ''),
            str(redis_config.get('use_ssl', False))
        ]

        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached Redis provider instances"""
        with cls._lock:
            return {
                'total_cached_instances': len(cls._instances),
                'cached_configurations': list(cls._instances.keys()),
                'memory_info': f"{len(cls._instances)} Redis provider instances cached"
            }

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached Redis provider instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("Cleared Redis cache provider cache")

    def __init__(self, config: Dict[str, Any]):
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config

        self.redis_config = config.get('internal_services', {}).get('redis', {})
        self.enabled = (
            is_cache_master_enabled(config) and self.redis_config.get('enabled', False) and REDIS_AVAILABLE
        )
        self.client: Optional[redis.Redis] = None
        self.initialized = False

        self.default_ttl = 60 * 60 * 24 * 7  # 7 days

        self._increment_script = None
        self._increment_script_client = None
        self._check_and_increment_script = None
        self._check_and_increment_script_client = None

        max_failures = self.redis_config.get('max_consecutive_failures', 5)
        recovery_timeout = self.redis_config.get('circuit_recovery_timeout', 30)
        self._circuit_breaker = CircuitBreaker(
            max_failures=max_failures,
            recovery_timeout=recovery_timeout
        )

        if self.enabled:
            try:
                self._initialize_redis()
            except Exception as e:
                logger.error(f"Failed to initialize Redis: {str(e)}")
                self.enabled = False

        self._singleton_initialized = True

    def _initialize_redis(self) -> None:
        """
        Initialize Redis client with connection pool.

        Raises:
            Exception: If Redis client initialization fails
        """
        host = self.redis_config.get('host', 'localhost')
        if host and ':' in host:
            host = host.split(':')[0]

        port = int(self.redis_config.get('port', 6379))
        db = int(self.redis_config.get('db', 0))
        password = self.redis_config.get('password')
        username = self.redis_config.get('username')

        use_ssl_value = self.redis_config.get('use_ssl', False)
        if isinstance(use_ssl_value, str):
            use_ssl = use_ssl_value.lower() in ('true', 'yes', '1')
        else:
            use_ssl = bool(use_ssl_value)

        if 'ttl' in self.redis_config:
            self.default_ttl = int(self.redis_config['ttl'])

        max_connections = int(self.redis_config.get('max_connections', 20))
        socket_connect_timeout = int(self.redis_config.get('socket_connect_timeout', 5))
        socket_timeout = int(self.redis_config.get('socket_timeout', 5))
        retry_on_timeout = self.redis_config.get('retry_on_timeout', True)
        health_check_interval = int(self.redis_config.get('health_check_interval', 30))

        pool_kwargs = {
            'host': host,
            'port': port,
            'db': db,
            'decode_responses': True,
            'max_connections': max_connections,
            'socket_connect_timeout': socket_connect_timeout,
            'socket_timeout': socket_timeout,
            'retry_on_timeout': retry_on_timeout,
            'health_check_interval': health_check_interval,
        }

        if username and username != "null" and username.strip():
            pool_kwargs['username'] = username

        if password and password != "null" and password.strip():
            pool_kwargs['password'] = password

        if use_ssl:
            pool_kwargs['ssl'] = True
            pool_kwargs['ssl_cert_reqs'] = None
            pool_kwargs['ssl_ca_certs'] = None  # Don't verify SSL cert for Redis Cloud

        try:
            connection_pool = redis.ConnectionPool(**pool_kwargs)
            self.client = redis.Redis(connection_pool=connection_pool)
            logger.debug(
                f"Redis client initialized with connection pool: {host}:{port}/db{db}, "
                f"max_connections={max_connections}, SSL: {'enabled' if use_ssl else 'disabled'}"
            )
        except Exception as e:
            logger.error(f"Error initializing Redis client: {str(e)}")
            self.enabled = False
            raise

    def _is_available(self) -> bool:
        """Check if Redis is available (enabled, has client, circuit not open)."""
        return self.enabled and self.client is not None and not self._circuit_breaker.is_open

    def _handle_redis_error(self, operation: str, error: Exception) -> None:
        """Record a failure in the circuit breaker instead of permanently disabling."""
        self._circuit_breaker.record_failure()
        if self._circuit_breaker.is_open:
            logger.warning(f"Redis circuit breaker open after {operation} error: {error}")
        else:
            logger.debug(f"Redis error during {operation}: {error}")

    async def initialize(self) -> bool:
        """Initialize Redis connection"""
        if self.initialized:
            return True

        try:
            redis_config = self.config.get("internal_services", {}).get("redis", {})
            if not is_cache_master_enabled(self.config) or not redis_config.get("enabled", False):
                logger.warning("Redis is not enabled in configuration")
                self.enabled = False
                self.client = None
                return False

            if not self.client:
                self._initialize_redis()

            await self.client.ping()
            logger.info("Successfully connected to Redis")

            cache_config = self.config.get("internal_services", {}).get("cache", {})
            clear_on_startup = cache_config.get(
                "clear_cache_on_startup", redis_config.get("clear_cache_on_startup", True)
            )
            if clear_on_startup:
                await self.clear_all_application_cache()
            else:
                logger.debug("Cache clearing on startup is disabled")

            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Redis: {str(e)}")
            self.enabled = False
            self.client = None
            self.initialized = False
            return False

    def _ensure_increment_script(self):
        """Register the increment-with-ttl Lua script once for the current client."""
        if self._increment_script is not None and self._increment_script_client is self.client:
            return self._increment_script

        if not self.client:
            return None

        try:
            self._increment_script = self.client.register_script(_INCREMENT_WITH_TTL_SCRIPT)
            self._increment_script_client = self.client
        except Exception as e:
            logger.warning(f"Failed to register increment-with-ttl Lua script: {e}")
            self._increment_script = None
            self._increment_script_client = None

        return self._increment_script

    def _ensure_check_and_increment_script(self):
        """Register the check-and-increment Lua script once for the current client."""
        if (
            self._check_and_increment_script is not None
            and self._check_and_increment_script_client is self.client
        ):
            return self._check_and_increment_script

        if not self.client:
            return None

        try:
            self._check_and_increment_script = self.client.register_script(_CHECK_AND_INCREMENT_SCRIPT)
            self._check_and_increment_script_client = self.client
        except Exception as e:
            logger.warning(f"Failed to register check-and-increment Lua script: {e}")
            self._check_and_increment_script = None
            self._check_and_increment_script_client = None

        return self._check_and_increment_script

    async def check_and_increment(
        self,
        checks: List[Tuple[str, str, int, Optional[int]]],
        amount: int = 1,
    ) -> Tuple[Dict[str, int], Optional[str]]:
        if not checks:
            return {}, None

        if not self._is_available():
            return await super().check_and_increment(checks, amount)

        try:
            script = self._ensure_check_and_increment_script()
            if script is None:
                return await super().check_and_increment(checks, amount)

            names = [name for name, _key, _ttl, _limit in checks]
            keys = [key for _name, key, _ttl, _limit in checks]
            args: List[int] = []
            for _name, _key, ttl, limit in checks:
                args.append(ttl)
                args.append(-1 if limit is None else limit)
            args.append(amount)

            result = await script(keys=keys, args=args)
            exceeded_index = int(result[0])
            counts = {name: int(count) for name, count in zip(names, result[1:])}
            self._circuit_breaker.record_success()

            if exceeded_index == 0:
                return counts, None
            return counts, names[exceeded_index - 1]

        except Exception as e:
            logger.error(f"Error in check_and_increment in Redis: {str(e)}")
            self._check_and_increment_script = None
            self._check_and_increment_script_client = None
            self._handle_redis_error("check_and_increment", e)
            return await super().check_and_increment(checks, amount)

    async def _clear_keys_by_pattern(self, pattern: str, description: str) -> int:
        """
        Clear all keys matching a pattern using SCAN for efficiency.

        Args:
            pattern: Redis key pattern to match (e.g., "prompt:*")
            description: Human-readable description for logging

        Returns:
            Number of keys deleted
        """
        if not self.client:
            return 0

        try:
            keys_to_delete = []
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(cursor, match=pattern, count=100)
                keys_to_delete.extend(keys)
                if cursor == 0:
                    break

            if keys_to_delete:
                deleted_count = await self.client.delete(*keys_to_delete)
                logger.debug(f"Cleared {deleted_count} {description} entries from Redis")
                return deleted_count
            else:
                logger.debug(f"No {description} entries found to clear")
                return 0

        except Exception as e:
            logger.warning(f"Failed to clear {description} on startup: {str(e)}")
            return 0

    async def clear_by_pattern(self, pattern: str, description: str = "") -> int:
        if not self._is_available():
            return 0
        return await self._clear_keys_by_pattern(pattern, description or pattern)

    async def get(self, key: str) -> Optional[str]:
        if not self._is_available():
            return None

        try:
            if not self.client:
                return None
            result = await self.client.get(key)
            self._circuit_breaker.record_success()
            return result
        except (AttributeError, TypeError) as e:
            logger.debug(f"Redis client unavailable for key {key}: {str(e)}")
            self._handle_redis_error("get", e)
            return None
        except Exception as e:
            logger.error(f"Error getting key {key} from Redis: {str(e)}")
            self._handle_redis_error("get", e)
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        if not self._is_available():
            return False

        try:
            if not self.client:
                return False
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            await self.client.set(key, value, ex=ttl_to_use)
            self._circuit_breaker.record_success()
            return True
        except (AttributeError, TypeError) as e:
            logger.debug(f"Redis client unavailable for key {key}: {str(e)}")
            self._handle_redis_error("set", e)
            return False
        except Exception as e:
            logger.error(f"Error setting key {key} in Redis: {str(e)}")
            self._handle_redis_error("set", e)
            return False

    async def delete(self, *keys: str) -> int:
        if not self._is_available():
            return 0

        try:
            if not self.client:
                return 0
            result = await self.client.delete(*keys)
            self._circuit_breaker.record_success()
            return result
        except (AttributeError, TypeError) as e:
            logger.debug(f"Redis client unavailable for delete operation: {str(e)}")
            self._handle_redis_error("delete", e)
            return 0
        except Exception as e:
            logger.error(f"Error deleting keys {keys} from Redis: {str(e)}")
            self._handle_redis_error("delete", e)
            return 0

    async def exists(self, key: str) -> bool:
        if not self._is_available():
            return False

        try:
            result = bool(await self.client.exists(key))
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error checking if key {key} exists in Redis: {str(e)}")
            self._handle_redis_error("exists", e)
            return False

    async def ttl(self, key: str) -> int:
        if not self._is_available():
            return -2

        try:
            result = await self.client.ttl(key)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error getting TTL for key {key} in Redis: {str(e)}")
            self._handle_redis_error("ttl", e)
            return -2

    async def expire(self, key: str, seconds: int) -> bool:
        if not self._is_available():
            return False

        try:
            result = await self.client.expire(key, seconds)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error setting expiration for key {key} in Redis: {str(e)}")
            self._handle_redis_error("expire", e)
            return False

    async def mget(self, *keys: str) -> List[Optional[str]]:
        if not self._is_available() or not keys:
            return [None] * len(keys)

        try:
            result = await self.client.mget(*keys)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error in mget for {len(keys)} keys: {str(e)}")
            self._handle_redis_error("mget", e)
            return [None] * len(keys)

    async def mset(self, mapping: Dict[str, str]) -> bool:
        if not self._is_available() or not mapping:
            return False

        try:
            await self.client.mset(mapping)
            self._circuit_breaker.record_success()
            return True
        except Exception as e:
            logger.error(f"Error in mset for {len(mapping)} keys: {str(e)}")
            self._handle_redis_error("mset", e)
            return False

    async def set_if_not_exists(self, key: str, value: str, ttl: int) -> bool:
        if not self._is_available():
            return False

        try:
            result = await self.client.set(key, value, nx=True, ex=ttl)
            self._circuit_breaker.record_success()
            return bool(result)
        except Exception as e:
            logger.error(f"Error in set_if_not_exists for key {key} in Redis: {str(e)}")
            self._handle_redis_error("set_if_not_exists", e)
            return False

    async def increment_with_ttl(self, key: str, ttl: int, amount: int = 1) -> int:
        if not self._is_available():
            return 0

        try:
            script = self._ensure_increment_script()
            if script is None:
                # Fallback without Lua: not perfectly atomic across INCR+EXPIRE, but
                # only reached if script registration itself failed.
                count = await self.client.incrby(key, amount)
                if count == amount:
                    await self.client.expire(key, ttl)
                self._circuit_breaker.record_success()
                return count

            count = await script(keys=[key], args=[ttl, amount])
            self._circuit_breaker.record_success()
            return int(count)
        except Exception as e:
            logger.error(f"Error in increment_with_ttl for key {key} in Redis: {str(e)}")
            self._increment_script = None
            self._increment_script_client = None
            self._handle_redis_error("increment_with_ttl", e)
            return 0

    def get_health_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "provider": "redis",
            "enabled": self.enabled,
            "initialized": self.initialized,
            "circuit_breaker": {
                "state": self._circuit_breaker.state,
                "failure_count": self._circuit_breaker.failure_count,
                "max_failures": self._circuit_breaker.max_failures,
            },
        }
        if self.client is not None:
            try:
                pool = self.client.connection_pool
                stats["pool"] = {
                    "max_connections": pool.max_connections,
                    "created_connections": getattr(pool, "_created_connections", 0),
                    "available_connections": len(getattr(pool, "_available_connections", [])),
                    "in_use_connections": len(getattr(pool, "_in_use_connections", [])),
                }
            except Exception:
                pass
        return stats

    # Redis-specific extras (list operations). Not part of the CacheProvider interface -
    # no current production caller needs these across other backends.

    async def lpush(self, key: str, *values: str) -> int:
        if not self._is_available():
            return 0
        try:
            result = await self.client.lpush(key, *values)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error pushing values to list {key} in Redis: {str(e)}")
            self._handle_redis_error("lpush", e)
            return 0

    async def rpush(self, key: str, *values: str) -> bool:
        if not self._is_available():
            return False
        try:
            await self.client.rpush(key, *values)
            self._circuit_breaker.record_success()
            return True
        except Exception as e:
            logger.error(f"Error pushing values to list {key} in Redis: {str(e)}")
            self._handle_redis_error("rpush", e)
            return False

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        if not self._is_available():
            return []
        try:
            result = await self.client.lrange(key, start, end)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error getting range from list {key} in Redis: {str(e)}")
            self._handle_redis_error("lrange", e)
            return []

    async def store_list_json(self, key: str, data_list: List[Dict[str, Any]], ttl: Optional[int] = None) -> bool:
        """Store a list of JSON objects in Redis as a list, using a pipeline for atomicity."""
        if not self._is_available():
            return False

        try:
            json_strings = [json.dumps(item) for item in data_list]
            ttl_to_use = ttl if ttl is not None else self.default_ttl

            if json_strings:
                async with self.client.pipeline(transaction=True) as pipe:
                    pipe.delete(key)
                    pipe.rpush(key, *json_strings)
                    pipe.expire(key, ttl_to_use)
                    await pipe.execute()
            else:
                await self.client.delete(key)

            self._circuit_breaker.record_success()
            return True
        except Exception as e:
            logger.error(f"Error storing list of JSON in Redis: {str(e)}")
            self._handle_redis_error("store_list_json", e)
            return False

    async def get_list_json(self, key: str, start: int = 0, end: int = -1) -> List[Dict[str, Any]]:
        if not self._is_available():
            return []

        try:
            json_strings = await self.lrange(key, start, end)
            return [json.loads(item) for item in json_strings if item]
        except Exception as e:
            logger.error(f"Error getting list of JSON from Redis: {str(e)}")
            return []

    async def close(self) -> None:
        """Close Redis connection pool"""
        if self.client:
            await self.client.aclose()
            self.client = None
            self.initialized = False
