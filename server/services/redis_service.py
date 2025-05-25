"""
Redis Service
============

This service provides a shared Redis client for caching and other Redis-related functionality.
It can be used by multiple services to avoid duplicating Redis connection logic.
"""

import logging
from typing import Dict, Any, Optional, Union, List, Tuple
import json

# Optional Redis imports - service will gracefully handle missing dependency
try:
    import redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class RedisService:
    """Service for Redis operations with graceful fallback if Redis is unavailable"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Redis service with configuration
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Redis configuration
        self.redis_config = config.get('internal_services', {}).get('redis', {})
        self.enabled = self.redis_config.get('enabled', False) and REDIS_AVAILABLE
        self.redis_client = None
        
        # Default TTL (7 days)
        self.default_ttl = 60 * 60 * 24 * 7
        
        # Initialize Redis client if enabled
        if self.enabled:
            try:
                self._initialize_redis()
            except Exception as e:
                logger.error(f"Failed to initialize Redis: {str(e)}")
                self.enabled = False
    
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
        
        # Create Redis client
        try:
            self.redis_client = Redis(**connection_kwargs)
            
            if self.verbose:
                logger.info(f"Redis client initialized: {host}:{port}/db{db}, SSL: {'enabled' if use_ssl else 'disabled'}, Username: {'set' if username else 'not set'}")
        except Exception as e:
            logger.error(f"Error initializing Redis client: {str(e)}")
            self.enabled = False
            raise
    
    async def initialize(self) -> bool:
        """
        Initialize the service and verify Redis connection
        
        Returns:
            True if Redis is available and connected, False otherwise
        """
        if not self.enabled or not self.redis_client:
            logger.info("Redis service is disabled or client not available")
            return False
            
        try:
            # Test Redis connection with ping
            await self.redis_client.ping()
            logger.info("Redis connection successful")
            return True
        except Exception as e:
            logger.error(f"Redis connection failed: {str(e)}")
            self.enabled = False
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get a value from Redis
        
        Args:
            key: The key to retrieve
            
        Returns:
            The value or None if not found or Redis is disabled
        """
        if not self.enabled or not self.redis_client:
            return None
            
        try:
            return await self.redis_client.get(key)
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
        if not self.enabled or not self.redis_client:
            return False
            
        try:
            ttl_to_use = ttl if ttl is not None else self.default_ttl
            await self.redis_client.set(key, value, ex=ttl_to_use)
            return True
        except Exception as e:
            logger.error(f"Error setting key {key} in Redis: {str(e)}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys from Redis
        
        Args:
            *keys: Keys to delete
            
        Returns:
            Number of keys deleted, or 0 if Redis is disabled
        """
        if not self.enabled or not self.redis_client or not keys:
            return 0
            
        try:
            return await self.redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Error deleting keys from Redis: {str(e)}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis
        
        Args:
            key: The key to check
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False
            
        try:
            return bool(await self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Error checking if key {key} exists in Redis: {str(e)}")
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration time on a key
        
        Args:
            key: The key to set expiration on
            ttl: Time-to-live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False
            
        try:
            return bool(await self.redis_client.expire(key, ttl))
        except Exception as e:
            logger.error(f"Error setting expiration on key {key} in Redis: {str(e)}")
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
        if not self.enabled or not self.redis_client:
            return 0
            
        try:
            return await self.redis_client.lpush(key, *values)
        except Exception as e:
            logger.error(f"Error pushing values to list {key} in Redis: {str(e)}")
            return 0
    
    async def rpush(self, key: str, *values: str) -> int:
        """
        Push values onto the tail of a list
        
        Args:
            key: The list key
            *values: Values to push
            
        Returns:
            Length of the list after push, or 0 if Redis is disabled
        """
        if not self.enabled or not self.redis_client:
            return 0
            
        try:
            return await self.redis_client.rpush(key, *values)
        except Exception as e:
            logger.error(f"Error pushing values to list {key} in Redis: {str(e)}")
            return 0
    
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
        if not self.enabled or not self.redis_client:
            return []
            
        try:
            return await self.redis_client.lrange(key, start, end)
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
        if not self.enabled or not self.redis_client:
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
        if not self.enabled or not self.redis_client:
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
        if not self.enabled or not self.redis_client:
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
                if ttl is not None:
                    await self.expire(key, ttl)
                else:
                    await self.expire(key, self.default_ttl)
                    
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
        if not self.enabled or not self.redis_client:
            return []
            
        try:
            json_strings = await self.lrange(key, start, end)
            return [json.loads(item) for item in json_strings if item]
        except Exception as e:
            logger.error(f"Error getting list of JSON from Redis: {str(e)}")
            return []
            
    async def close(self) -> None:
        """Close the Redis connection"""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the Redis connection (async version)"""
        if self.redis_client:
            try:
                await self.redis_client.aclose()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {str(e)}")
