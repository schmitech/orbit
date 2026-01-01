"""
Quota Service
=============

This service manages API key quotas with Redis caching and database persistence.
Handles daily/monthly quota tracking, usage increments, and period resets.
"""

import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import threading
import hashlib

logger = logging.getLogger(__name__)


class QuotaService:
    """
    Service for managing API key quotas.

    Uses Redis for real-time usage tracking with periodic sync to database
    for durability. Handles:
    - Quota retrieval and caching
    - Usage increments and tracking
    - Period resets (daily/monthly)
    - Database synchronization
    """

    # Singleton pattern implementation
    _instances: Dict[str, 'QuotaService'] = {}
    _lock = threading.Lock()

    # Lua script for atomic quota increment with TTL
    # Returns [daily_count, monthly_count, daily_ttl_remaining, monthly_ttl_remaining]
    _QUOTA_INCREMENT_SCRIPT = """
    local daily_key = KEYS[1]
    local monthly_key = KEYS[2]
    local daily_ttl = tonumber(ARGV[1])
    local monthly_ttl = tonumber(ARGV[2])
    local timestamp = tonumber(ARGV[3])
    local last_request_key = KEYS[3]

    -- Increment daily counter
    local daily_count = redis.call('INCR', daily_key)
    if daily_count == 1 then
        redis.call('EXPIRE', daily_key, daily_ttl)
    end
    local daily_ttl_remaining = redis.call('TTL', daily_key)

    -- Increment monthly counter
    local monthly_count = redis.call('INCR', monthly_key)
    if monthly_count == 1 then
        redis.call('EXPIRE', monthly_key, monthly_ttl)
    end
    local monthly_ttl_remaining = redis.call('TTL', monthly_key)

    -- Update last request timestamp
    redis.call('SET', last_request_key, timestamp, 'EX', monthly_ttl)

    return {daily_count, monthly_count, daily_ttl_remaining, monthly_ttl_remaining}
    """

    # Lua script to get current usage without incrementing
    _QUOTA_GET_SCRIPT = """
    local daily_key = KEYS[1]
    local monthly_key = KEYS[2]
    local last_request_key = KEYS[3]

    local daily_count = redis.call('GET', daily_key)
    local monthly_count = redis.call('GET', monthly_key)
    local daily_ttl = redis.call('TTL', daily_key)
    local monthly_ttl = redis.call('TTL', monthly_key)
    local last_request = redis.call('GET', last_request_key)

    return {
        daily_count or 0,
        monthly_count or 0,
        daily_ttl,
        monthly_ttl,
        last_request or 0
    }
    """

    def __new__(cls, config: Dict[str, Any], database_service=None, redis_service=None):
        """Create or return existing QuotaService instance based on configuration"""
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new QuotaService instance for: {cache_key}")
            else:
                logger.debug(f"Reusing existing QuotaService instance for: {cache_key}")
            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        """Create a cache key based on configuration"""
        throttle_config = config.get('security', {}).get('throttling', {})
        redis_config = config.get('internal_services', {}).get('redis', {})

        key_parts = [
            redis_config.get('host', 'localhost'),
            str(redis_config.get('port', 6379)),
            str(redis_config.get('db', 0)),
            throttle_config.get('redis_key_prefix', 'quota:')
        ]

        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("Cleared QuotaService cache")

    def __init__(self, config: Dict[str, Any], database_service=None, redis_service=None):
        """
        Initialize the Quota Service.

        Args:
            config: Application configuration
            database_service: Database service for persistence
            redis_service: Redis service for caching
        """
        # Avoid re-initialization if this instance was already initialized
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config
        self.database_service = database_service
        self.redis_service = redis_service
        self.initialized = False

        # Extract throttling configuration
        security_config = config.get('security', {}) or {}
        self.throttle_config = security_config.get('throttling', {}) or {}

        self.enabled = self.throttle_config.get('enabled', False)

        # Default quotas
        default_quotas = self.throttle_config.get('default_quotas', {}) or {}
        self.default_daily_limit = default_quotas.get('daily_limit', 10000)
        self.default_monthly_limit = default_quotas.get('monthly_limit', 100000)

        # Redis key configuration
        self.redis_key_prefix = self.throttle_config.get('redis_key_prefix', 'quota:')

        # Sync configuration
        self.sync_interval = self.throttle_config.get('usage_sync_interval_seconds', 60)

        # Quota cache (in-memory cache for quota configs)
        self._quota_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes cache for quota configs
        self._cache_timestamps: Dict[str, float] = {}

        # Registered Lua scripts (initialized lazily when Redis is available)
        self._increment_script = None
        self._get_script = None

        # Mark as initialized
        self._singleton_initialized = True

        if self.enabled:
            logger.info(
                f"QuotaService initialized: prefix={self.redis_key_prefix}, "
                f"default_daily={self.default_daily_limit}, "
                f"default_monthly={self.default_monthly_limit}"
            )
        else:
            logger.info("QuotaService initialized but disabled")

    async def initialize(self) -> None:
        """Initialize the service (verify dependencies are available)"""
        if not self.enabled:
            logger.info("QuotaService is disabled")
            self.initialized = True
            return

        # Verify Redis is available
        if not self.redis_service or not self.redis_service.enabled:
            logger.warning("QuotaService requires Redis - service will be limited")
            self.enabled = False
            self.initialized = True
            return

        # Ensure Redis is initialized
        if not self.redis_service.initialized:
            await self.redis_service.initialize()

        self.initialized = True
        logger.info("QuotaService fully initialized")

    def _register_lua_scripts(self) -> None:
        """Register Lua scripts with Redis client for efficient execution."""
        if not self.redis_service or not self.redis_service.client:
            return

        try:
            self._increment_script = self.redis_service.client.register_script(
                self._QUOTA_INCREMENT_SCRIPT
            )
            self._get_script = self.redis_service.client.register_script(
                self._QUOTA_GET_SCRIPT
            )
            logger.debug("Registered quota Lua scripts with Redis")
        except Exception as e:
            logger.warning(f"Failed to register Lua scripts: {e}")
            self._increment_script = None
            self._get_script = None

    def _get_daily_key(self, api_key: str) -> str:
        """Get Redis key for daily usage counter"""
        today = datetime.now(timezone.utc).strftime('%Y%m%d')
        return f"{self.redis_key_prefix}{api_key}:daily:{today}"

    def _get_monthly_key(self, api_key: str) -> str:
        """Get Redis key for monthly usage counter"""
        month = datetime.now(timezone.utc).strftime('%Y%m')
        return f"{self.redis_key_prefix}{api_key}:monthly:{month}"

    def _get_last_request_key(self, api_key: str) -> str:
        """Get Redis key for last request timestamp"""
        return f"{self.redis_key_prefix}{api_key}:last_request"

    def _calculate_daily_ttl(self) -> int:
        """Calculate TTL for daily counter (seconds until end of day + buffer)"""
        now = datetime.now(timezone.utc)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        remaining = (end_of_day - now).total_seconds()
        # Add 1 day buffer for safety
        return int(remaining) + 86400

    def _calculate_monthly_ttl(self) -> int:
        """Calculate TTL for monthly counter (seconds until end of month + buffer)"""
        now = datetime.now(timezone.utc)
        # Go to next month
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        remaining = (next_month - now).total_seconds()
        # Add 5 days buffer for safety
        return int(remaining) + (5 * 86400)

    def _calculate_daily_reset_timestamp(self) -> float:
        """Calculate Unix timestamp for next daily reset (midnight UTC)"""
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if tomorrow <= now:
            # Already past midnight, go to next day
            from datetime import timedelta
            tomorrow = tomorrow + timedelta(days=1)
        return tomorrow.timestamp()

    def _calculate_monthly_reset_timestamp(self) -> float:
        """Calculate Unix timestamp for next monthly reset (1st of next month UTC)"""
        now = datetime.now(timezone.utc)
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return next_month.timestamp()

    async def get_quota_config(self, api_key: str) -> Dict[str, Any]:
        """
        Get quota configuration for an API key.

        Args:
            api_key: The API key to get quota for

        Returns:
            Dict with quota configuration (daily_limit, monthly_limit, throttle_enabled, throttle_priority)
        """
        # Check cache first
        cache_key = f"config:{api_key}"
        if cache_key in self._quota_cache:
            cache_time = self._cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self._cache_ttl:
                return self._quota_cache[cache_key]

        # Try to get from database
        quota_config = {
            'daily_limit': self.default_daily_limit,
            'monthly_limit': self.default_monthly_limit,
            'throttle_enabled': True,
            'throttle_priority': 5
        }

        if self.database_service:
            try:
                # Get API key document from database
                api_key_doc = await self.database_service.find_one('api_keys', {'api_key': api_key})
                if api_key_doc:
                    # Override defaults with stored values if present
                    if api_key_doc.get('quota_daily_limit') is not None:
                        quota_config['daily_limit'] = api_key_doc['quota_daily_limit']
                    if api_key_doc.get('quota_monthly_limit') is not None:
                        quota_config['monthly_limit'] = api_key_doc['quota_monthly_limit']
                    if api_key_doc.get('quota_throttle_enabled') is not None:
                        quota_config['throttle_enabled'] = api_key_doc['quota_throttle_enabled']
                    if api_key_doc.get('quota_throttle_priority') is not None:
                        quota_config['throttle_priority'] = api_key_doc['quota_throttle_priority']
            except Exception as e:
                logger.warning(f"Failed to get quota config from database: {e}")

        # Cache the result
        self._quota_cache[cache_key] = quota_config
        self._cache_timestamps[cache_key] = time.time()

        return quota_config

    async def increment_usage(self, api_key: str) -> Tuple[int, int, int, int]:
        """
        Atomically increment usage counters for an API key.

        Args:
            api_key: The API key to increment usage for

        Returns:
            Tuple of (daily_used, monthly_used, daily_reset_in_seconds, monthly_reset_in_seconds)
        """
        if not self.enabled or not self.redis_service or not self.redis_service.enabled:
            return (0, 0, 86400, 2592000)

        if not self.redis_service.client:
            logger.warning("Redis client not initialized, skipping quota increment")
            return (0, 0, 86400, 2592000)

        try:
            # Register scripts if not already done
            if self._increment_script is None:
                self._register_lua_scripts()

            if self._increment_script is None:
                logger.warning("Lua scripts not registered, skipping quota increment")
                return (0, 0, 86400, 2592000)

            daily_key = self._get_daily_key(api_key)
            monthly_key = self._get_monthly_key(api_key)
            last_request_key = self._get_last_request_key(api_key)

            daily_ttl = self._calculate_daily_ttl()
            monthly_ttl = self._calculate_monthly_ttl()
            timestamp = int(time.time())

            result = await self._increment_script(
                keys=[daily_key, monthly_key, last_request_key],
                args=[daily_ttl, monthly_ttl, timestamp]
            )

            daily_count = int(result[0])
            monthly_count = int(result[1])
            daily_ttl_remaining = int(result[2]) if result[2] > 0 else daily_ttl
            monthly_ttl_remaining = int(result[3]) if result[3] > 0 else monthly_ttl

            return (daily_count, monthly_count, daily_ttl_remaining, monthly_ttl_remaining)

        except Exception as e:
            logger.warning(f"Failed to increment quota usage: {e}")
            return (0, 0, 86400, 2592000)

    async def get_usage(self, api_key: str) -> Dict[str, Any]:
        """
        Get current usage statistics for an API key without incrementing.

        Args:
            api_key: The API key to get usage for

        Returns:
            Dict with usage statistics
        """
        if not self.enabled or not self.redis_service or not self.redis_service.enabled:
            return {
                'daily_used': 0,
                'monthly_used': 0,
                'daily_reset_at': self._calculate_daily_reset_timestamp(),
                'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
                'last_request_at': None
            }

        if not self.redis_service.client:
            logger.warning("Redis client not initialized, returning empty usage")
            return {
                'daily_used': 0,
                'monthly_used': 0,
                'daily_reset_at': self._calculate_daily_reset_timestamp(),
                'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
                'last_request_at': None
            }

        try:
            # Register scripts if not already done
            if self._get_script is None:
                self._register_lua_scripts()

            if self._get_script is None:
                logger.warning("Lua scripts not registered, returning empty usage")
                return {
                    'daily_used': 0,
                    'monthly_used': 0,
                    'daily_reset_at': self._calculate_daily_reset_timestamp(),
                    'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
                    'last_request_at': None
                }

            daily_key = self._get_daily_key(api_key)
            monthly_key = self._get_monthly_key(api_key)
            last_request_key = self._get_last_request_key(api_key)

            result = await self._get_script(
                keys=[daily_key, monthly_key, last_request_key],
                args=[]
            )

            daily_used = int(result[0]) if result[0] else 0
            monthly_used = int(result[1]) if result[1] else 0
            last_request = float(result[4]) if result[4] else None

            return {
                'daily_used': daily_used,
                'monthly_used': monthly_used,
                'daily_reset_at': self._calculate_daily_reset_timestamp(),
                'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
                'last_request_at': last_request
            }

        except Exception as e:
            logger.warning(f"Failed to get quota usage: {e}")
            return {
                'daily_used': 0,
                'monthly_used': 0,
                'daily_reset_at': self._calculate_daily_reset_timestamp(),
                'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
                'last_request_at': None
            }

    async def update_quota_config(
        self,
        api_key: str,
        daily_limit: Optional[int] = None,
        monthly_limit: Optional[int] = None,
        throttle_enabled: Optional[bool] = None,
        throttle_priority: Optional[int] = None
    ) -> bool:
        """
        Update quota configuration for an API key.

        Args:
            api_key: The API key to update
            daily_limit: New daily limit (None to keep current)
            monthly_limit: New monthly limit (None to keep current)
            throttle_enabled: Enable/disable throttling (None to keep current)
            throttle_priority: New priority 1-10 (None to keep current)

        Returns:
            True if updated successfully, False otherwise
        """
        if not self.database_service:
            logger.warning("Cannot update quota config without database service")
            return False

        try:
            update_fields = {}

            if daily_limit is not None:
                update_fields['quota_daily_limit'] = daily_limit
            if monthly_limit is not None:
                update_fields['quota_monthly_limit'] = monthly_limit
            if throttle_enabled is not None:
                update_fields['quota_throttle_enabled'] = throttle_enabled
            if throttle_priority is not None:
                update_fields['quota_throttle_priority'] = max(1, min(10, throttle_priority))

            if not update_fields:
                return True  # Nothing to update

            result = await self.database_service.update_one(
                'api_keys',
                {'api_key': api_key},
                {'$set': update_fields}
            )

            # Invalidate cache
            cache_key = f"config:{api_key}"
            if cache_key in self._quota_cache:
                del self._quota_cache[cache_key]
                del self._cache_timestamps[cache_key]

            return result.modified_count > 0 if hasattr(result, 'modified_count') else True

        except Exception as e:
            logger.error(f"Failed to update quota config: {e}")
            return False

    async def reset_usage(self, api_key: str, period: str = 'all') -> bool:
        """
        Reset usage counters for an API key.

        Args:
            api_key: The API key to reset
            period: 'daily', 'monthly', or 'all'

        Returns:
            True if reset successfully, False otherwise
        """
        if not self.redis_service or not self.redis_service.enabled:
            return False

        if not self.redis_service.client:
            logger.warning("Redis client not initialized, cannot reset usage")
            return False

        try:
            keys_to_delete = []

            if period in ('daily', 'all'):
                keys_to_delete.append(self._get_daily_key(api_key))

            if period in ('monthly', 'all'):
                keys_to_delete.append(self._get_monthly_key(api_key))

            if period == 'all':
                keys_to_delete.append(self._get_last_request_key(api_key))

            if keys_to_delete:
                await self.redis_service.client.delete(*keys_to_delete)

            logger.info(f"Reset {period} usage for API key: {api_key[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to reset usage: {e}")
            return False

    async def get_quota_and_usage(self, api_key: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Get both quota configuration and current usage for an API key.

        Args:
            api_key: The API key

        Returns:
            Tuple of (quota_config, usage_stats)
        """
        quota_config = await self.get_quota_config(api_key)
        usage_stats = await self.get_usage(api_key)
        return quota_config, usage_stats

    def calculate_remaining(
        self,
        quota_config: Dict[str, Any],
        usage_stats: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Calculate remaining quota.

        Args:
            quota_config: Quota configuration dict
            usage_stats: Usage statistics dict

        Returns:
            Tuple of (daily_remaining, monthly_remaining) - None if unlimited
        """
        daily_limit = quota_config.get('daily_limit')
        monthly_limit = quota_config.get('monthly_limit')
        daily_used = usage_stats.get('daily_used', 0)
        monthly_used = usage_stats.get('monthly_used', 0)

        daily_remaining = None if daily_limit is None else max(0, daily_limit - daily_used)
        monthly_remaining = None if monthly_limit is None else max(0, monthly_limit - monthly_used)

        return daily_remaining, monthly_remaining

    async def sync_usage_to_database(self) -> int:
        """
        Sync all Redis usage counters to database for persistence.

        Returns:
            Number of keys synced
        """
        # This is a placeholder for future implementation
        # Would scan Redis for quota keys and persist to database
        logger.debug("Usage sync to database called (not yet implemented)")
        return 0

    async def shutdown(self) -> None:
        """Cleanup resources on shutdown"""
        # Final sync before shutdown
        await self.sync_usage_to_database()
        logger.info("QuotaService shutdown complete")
