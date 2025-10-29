"""
Redis Service
============

This service provides a shared Redis client for caching and other Redis-related functionality.
It can be used by multiple services to avoid duplicating Redis connection logic.
"""

import logging
from typing import Dict, Any, Optional, Union, List, Tuple
import json
import redis.asyncio as redis
import threading
import hashlib

# Optional Redis imports - service will gracefully handle missing dependency
try:
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

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
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Redis configuration
        self.redis_config = config.get('internal_services', {}).get('redis', {})
        self.enabled = self.redis_config.get('enabled', False) and REDIS_AVAILABLE
        self.client: Optional[redis.Redis] = None
        self.initialized = False
        
        # Default TTL (7 days)
        self.default_ttl = 60 * 60 * 24 * 7
        
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
        Initialize Redis client from configuration
        
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
        
        # Create Redis client
        connection_kwargs = {
            'host': host,
            'port': port,
            'db': db,
            'decode_responses': True
        }
        
        # Add username if provided
        if username and username != "null" and username.strip():
            connection_kwargs['username'] = username
            
        # Add password if provided
        if password and password != "null" and password.strip():
            connection_kwargs['password'] = password
            
        if use_ssl:
            connection_kwargs['ssl'] = True
            connection_kwargs['ssl_cert_reqs'] = None
            connection_kwargs['ssl_ca_certs'] = None  # Don't verify SSL cert for Redis Cloud
        
        # Add timeout parameters for better connection handling
        connection_kwargs['socket_connect_timeout'] = 10
        connection_kwargs['socket_timeout'] = 10
        
        # Create Redis client
        try:
            self.client = redis.Redis(**connection_kwargs)
            
            if self.verbose:
                logger.info(f"Redis client initialized: {host}:{port}/db{db}, SSL: {'enabled' if use_ssl else 'disabled'}, Username: {'set' if username else 'not set'}")
        except Exception as e:
            logger.error(f"Error initializing Redis client: {str(e)}")
            self.enabled = False
            raise
    
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

            # Clear prompt cache on startup to ensure fresh data
            await self._clear_prompt_cache_on_startup()

            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Redis: {str(e)}")
            self.enabled = False
            self.client = None
            self.initialized = False
            return False

    async def _clear_prompt_cache_on_startup(self) -> None:
        """Clear all prompt cache keys on server startup"""
        try:
            verbose = self.config.get('general', {}).get('verbose', False)

            if verbose:
                logger.info("Clearing prompt cache on server startup...")

            # Get all keys matching the prompt pattern
            prompt_keys = []
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(cursor, match="prompt:*", count=100)
                prompt_keys.extend(keys)
                if cursor == 0:
                    break

            if prompt_keys:
                deleted_count = await self.client.delete(*prompt_keys)
                if verbose:
                    logger.info(f"✓ Cleared {deleted_count} prompt cache entries from Redis")
            elif verbose:
                logger.info("No prompt cache entries found to clear")

        except Exception as e:
            logger.warning(f"Failed to clear prompt cache on startup: {str(e)}")
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get a value from Redis
        
        Args:
            key: The key to retrieve
            
        Returns:
            The value or None if not found or Redis is disabled
        """
        if not self.enabled or not self.client:
            return None
            
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Error getting key {key} from Redis: {str(e)}")
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
        if not self.enabled or not self.client:
            return False
            
        try:
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            await self.client.set(key, value, ex=ttl_to_use)
            return True
        except Exception as e:
            logger.error(f"Error setting key {key} in Redis: {str(e)}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        if not self.enabled or not self.client:
            return 0
            
        try:
            return await self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Error deleting keys {keys} from Redis: {str(e)}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis
        
        Args:
            key: The key to check
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.enabled or not self.client:
            return False
            
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            logger.error(f"Error checking if key {key} exists in Redis: {str(e)}")
            return False
    
    async def ttl(self, key: str) -> int:
        """Get remaining TTL for a key"""
        if not self.enabled or not self.client:
            return -2
            
        try:
            return await self.client.ttl(key)
        except Exception as e:
            logger.error(f"Error getting TTL for key {key} in Redis: {str(e)}")
            return -2
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration time for a key"""
        if not self.enabled or not self.client:
            return False
            
        try:
            return await self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Error setting expiration for key {key} in Redis: {str(e)}")
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
        if not self.enabled or not self.client:
            return 0
            
        try:
            return await self.client.lpush(key, *values)
        except Exception as e:
            logger.error(f"Error pushing values to list {key} in Redis: {str(e)}")
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
        if not self.enabled or not self.client:
            return False
            
        try:
            await self.client.rpush(key, *values)
            return True
        except Exception as e:
            logger.error(f"Error pushing values to list {key} in Redis: {str(e)}")
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
        if not self.enabled or not self.client:
            return []
            
        try:
            return await self.client.lrange(key, start, end)
        except Exception as e:
            logger.error(f"Error getting range from list {key} in Redis: {str(e)}")
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
        if not self.enabled or not self.client:
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
        if not self.enabled or not self.client:
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
        Store a list of JSON objects in Redis as a list
        
        Args:
            key: The key to store the list under
            data_list: List of dictionaries to store
            ttl: Time-to-live in seconds, or None to use default TTL
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False
            
        try:
            # Convert each dictionary to JSON string
            json_strings = [json.dumps(item) for item in data_list]
            
            # Delete existing key if it exists
            await self.delete(key)
            
            # Push all JSON strings to the list
            if json_strings:
                await self.rpush(key, *json_strings)
                
                # Set expiration if needed
                ttl_to_use = ttl if ttl is not None else self.default_ttl
                await self.expire(key, ttl_to_use)
                    
            return True
        except Exception as e:
            logger.error(f"Error storing list of JSON in Redis: {str(e)}")
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
        if not self.enabled or not self.client:
            return []
            
        try:
            json_strings = await self.lrange(key, start, end)
            return [json.loads(item) for item in json_strings if item]
        except Exception as e:
            logger.error(f"Error getting list of JSON from Redis: {str(e)}")
            return []
            
    async def close(self) -> None:
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            self.client = None
            self.initialized = False
    
    async def aclose(self) -> None:
        """Alias for close() to maintain compatibility"""
        await self.close()
