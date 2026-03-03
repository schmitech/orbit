"""
Redis Service
============

This service provides a shared Redis client for caching and other Redis-related functionality.
It can be used by multiple services to avoid duplicating Redis connection logic.

Features connection pooling, circuit breaker pattern for resilience, and pipeline support.
"""

import logging
import time
from typing import Dict, Any, Optional, List
import json
import redis.asyncio as redis
import threading
import hashlib

# Optional Redis imports - service will gracefully handle missing dependency
try:
    from redis.asyncio import Redis  # noqa: F401
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker to avoid permanently disabling Redis on transient failures."""

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
                # Check if recovery timeout has elapsed
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = "half_open"
                    logger.info("Circuit breaker entering half-open state, will attempt recovery")
                    return False
                return True
            return False

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


class RedisService:
    """Service for Redis operations with graceful fallback if Redis is unavailable"""

    # Singleton pattern implementation
    _instances: Dict[str, 'RedisService'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any]):
        """Create or return existing Redis service instance based on configuration"""
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new Redis service instance for: {cache_key}")
            else:
                logger.debug(f"Reusing existing Redis service instance for: {cache_key}")
            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        """Create a cache key based on Redis configuration"""
        redis_config = config.get('internal_services', {}).get('redis', {})

        # Create key from connection parameters
        key_parts = [
            redis_config.get('host', 'localhost'),
            str(redis_config.get('port', 6379)),
            str(redis_config.get('db', 0)),
            redis_config.get('username', ''),
            str(redis_config.get('use_ssl', False))
        ]

        # Create hash of the key parts for consistency
        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached Redis service instances"""
        with cls._lock:
            return {
                'total_cached_instances': len(cls._instances),
                'cached_configurations': list(cls._instances.keys()),
                'memory_info': f"{len(cls._instances)} Redis service instances cached"
            }

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached Redis service instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("Cleared Redis service cache")

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Redis service with configuration

        Args:
            config: Application configuration
        """
        # Avoid re-initialization if this instance was already initialized
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config

        # Redis configuration
        self.redis_config = config.get('internal_services', {}).get('redis', {})
        self.enabled = self.redis_config.get('enabled', False) and REDIS_AVAILABLE
        self.client: Optional[redis.Redis] = None
        self.initialized = False

        # Default TTL (7 days)
        self.default_ttl = 60 * 60 * 24 * 7

        # Circuit breaker for resilience (replaces permanent self.enabled = False)
        max_failures = self.redis_config.get('max_consecutive_failures', 5)
        recovery_timeout = self.redis_config.get('circuit_recovery_timeout', 30)
        self._circuit_breaker = CircuitBreaker(
            max_failures=max_failures,
            recovery_timeout=recovery_timeout
        )

        # Initialize Redis client if enabled
        if self.enabled:
            try:
                self._initialize_redis()
            except Exception as e:
                logger.error(f"Failed to initialize Redis: {str(e)}")
                self.enabled = False

        # Mark as initialized to prevent re-initialization
        self._singleton_initialized = True

    def _initialize_redis(self) -> None:
        """
        Initialize Redis client with connection pool.

        Raises:
            Exception: If Redis client initialization fails
        """
        # Extract configuration values
        host = self.redis_config.get('host', 'localhost')
        # Clean host if it includes port
        if host and ':' in host:
            host = host.split(':')[0]

        port = int(self.redis_config.get('port', 6379))
        db = int(self.redis_config.get('db', 0))
        password = self.redis_config.get('password')
        username = self.redis_config.get('username')

        # Handle boolean config values
        use_ssl_value = self.redis_config.get('use_ssl', False)
        if isinstance(use_ssl_value, str):
            use_ssl = use_ssl_value.lower() in ('true', 'yes', '1')
        else:
            use_ssl = bool(use_ssl_value)

        # Update default TTL from config if provided
        if 'ttl' in self.redis_config:
            self.default_ttl = int(self.redis_config['ttl'])

        # Connection pool parameters
        max_connections = int(self.redis_config.get('max_connections', 20))
        socket_connect_timeout = int(self.redis_config.get('socket_connect_timeout', 5))
        socket_timeout = int(self.redis_config.get('socket_timeout', 5))
        retry_on_timeout = self.redis_config.get('retry_on_timeout', True)
        health_check_interval = int(self.redis_config.get('health_check_interval', 30))

        # Build connection pool kwargs
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

        # Add username if provided
        if username and username != "null" and username.strip():
            pool_kwargs['username'] = username

        # Add password if provided
        if password and password != "null" and password.strip():
            pool_kwargs['password'] = password

        if use_ssl:
            pool_kwargs['ssl'] = True
            pool_kwargs['ssl_cert_reqs'] = None
            pool_kwargs['ssl_ca_certs'] = None  # Don't verify SSL cert for Redis Cloud

        # Create connection pool and Redis client
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
            if not redis_config.get("enabled", False):
                logger.warning("Redis is not enabled in configuration")
                self.enabled = False
                self.client = None
                return False

            # Test connection
            if not self.client:
                self._initialize_redis()

            await self.client.ping()
            logger.info("Successfully connected to Redis")

            # Clear application cache on startup to prevent orphaned/stale data
            # This is configurable via clear_cache_on_startup (defaults to True)
            if redis_config.get("clear_cache_on_startup", True):
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

    async def _clear_prompt_cache_on_startup(self) -> None:
        """Clear all prompt cache keys on server startup (deprecated, use clear_all_application_cache)"""
        await self._clear_keys_by_pattern("prompt:*", "prompt cache")

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

    async def clear_all_application_cache(self) -> Dict[str, int]:
        """
        Clear all application-related cache keys on startup to prevent orphaned data.

        Returns:
            Dictionary mapping cache type to number of keys deleted
        """
        if not self._is_available():
            logger.debug("Redis not available, skipping cache clearing")
            return {}

        # Define all application cache patterns that should be cleared on startup
        cache_patterns = [
            ("prompt:*", "prompt cache"),
            ("session:*", "session data"),
            ("thread:*", "thread data"),
            ("thread_dataset:*", "thread dataset data"),
            ("rate_limit:*", "rate limit data"),
            ("cache:*", "general cache"),
            ("temp:*", "temporary data"),
        ]

        results = {}
        total_cleared = 0

        for pattern, description in cache_patterns:
            try:
                deleted = await self._clear_keys_by_pattern(pattern, description)
                results[description] = deleted
                total_cleared += deleted
            except Exception as e:
                logger.warning(f"Error clearing {description}: {str(e)}")
                results[description] = 0

        if total_cleared > 0:
            logger.info(f"Cleared {total_cleared} total cache entries from Redis on startup")
        else:
            logger.debug("No cache entries found to clear on startup")

        return results

    async def get(self, key: str) -> Optional[str]:
        """
        Get a value from Redis

        Args:
            key: The key to retrieve

        Returns:
            The value or None if not found or Redis is disabled
        """
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
        """
        Set a value in Redis

        Args:
            key: The key to set
            value: The value to store
            ttl: Time-to-live in seconds, or None to use default TTL

        Returns:
            True if successful, False otherwise
        """
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
        """Delete one or more keys"""
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
        """
        Check if a key exists in Redis

        Args:
            key: The key to check

        Returns:
            True if key exists, False otherwise
        """
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
        """Get remaining TTL for a key"""
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
        """Set expiration time for a key"""
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

    async def lpush(self, key: str, *values: str) -> int:
        """
        Push values onto the head of a list

        Args:
            key: The list key
            *values: Values to push

        Returns:
            Length of the list after push, or 0 if Redis is disabled
        """
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
        """
        Push values onto the tail of a list

        Args:
            key: The list key
            *values: Values to push

        Returns:
            True if successful, False otherwise
        """
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
        """
        Get a range of elements from a list

        Args:
            key: The list key
            start: Start index
            end: End index

        Returns:
            List of elements, or empty list if Redis is disabled
        """
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

    async def store_json(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Store JSON data in Redis

        Args:
            key: The key to store data under
            data: The data to store
            ttl: Time-to-live in seconds, or None to use default TTL

        Returns:
            True if successful, False otherwise
        """
        if not self._is_available():
            return False

        try:
            json_data = json.dumps(data)
            return await self.set(key, json_data, ttl)
        except Exception as e:
            logger.error(f"Error storing JSON data in Redis: {str(e)}")
            return False

    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get JSON data from Redis

        Args:
            key: The key to retrieve

        Returns:
            The parsed JSON data, or None if not found or Redis is disabled
        """
        if not self._is_available():
            return None

        try:
            data = await self.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error getting JSON data from Redis: {str(e)}")
            return None

    async def store_list_json(self, key: str, data_list: List[Dict[str, Any]], ttl: Optional[int] = None) -> bool:
        """
        Store a list of JSON objects in Redis as a list, using a pipeline for atomicity.

        Args:
            key: The key to store the list under
            data_list: List of dictionaries to store
            ttl: Time-to-live in seconds, or None to use default TTL

        Returns:
            True if successful, False otherwise
        """
        if not self._is_available():
            return False

        try:
            # Convert each dictionary to JSON string
            json_strings = [json.dumps(item) for item in data_list]
            ttl_to_use = ttl if ttl is not None else self.default_ttl

            if json_strings:
                # Use pipeline for atomic delete + rpush + expire
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
        """
        Get a list of JSON objects from Redis

        Args:
            key: The key to retrieve
            start: Start index
            end: End index (-1 for all elements)

        Returns:
            List of parsed JSON data, or empty list if not found or Redis is disabled
        """
        if not self._is_available():
            return []

        try:
            json_strings = await self.lrange(key, start, end)
            return [json.loads(item) for item in json_strings if item]
        except Exception as e:
            logger.error(f"Error getting list of JSON from Redis: {str(e)}")
            return []

    async def mget(self, *keys: str) -> List[Optional[str]]:
        """
        Get multiple keys in a single round-trip.

        Args:
            *keys: Keys to retrieve

        Returns:
            List of values (None for missing keys)
        """
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
        """
        Set multiple keys in a single round-trip.

        Args:
            mapping: Dictionary of key-value pairs to set

        Returns:
            True if successful, False otherwise
        """
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

    async def close(self) -> None:
        """Close Redis connection pool"""
        if self.client:
            await self.client.aclose()
            self.client = None
            self.initialized = False

    async def aclose(self) -> None:
        """Alias for close() to maintain compatibility"""
        await self.close()
