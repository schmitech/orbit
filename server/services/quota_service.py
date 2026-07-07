"""
Quota Service
=============

This service manages API key quotas with cache-backed counters and database
persistence. Handles daily/monthly quota tracking, usage increments, and period
resets.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import threading
import hashlib

from utils.text_utils import mask_api_key

logger = logging.getLogger(__name__)


class QuotaService:
    """
    Service for managing API key quotas.

    Uses the configured cache service for real-time usage tracking with periodic
    sync to database for durability. Handles:
    - Quota retrieval and caching
    - Usage increments and tracking
    - Period resets (daily/monthly)
    - Database synchronization

    Usage tracking and hard-limit enforcement both go through the cache
    provider's check_and_increment(), which is atomic across the daily and
    monthly counters on backends with multi-key transactions (Redis, SQLite).
    Memcached has no such primitive and falls back to a best-effort
    check-then-increment with a small race window on concurrent requests near
    the limit - see CacheProvider.check_and_increment.
    """

    # Singleton pattern implementation
    _instances: Dict[str, 'QuotaService'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any], database_service=None, cache_service=None):
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
        from services.cache_backends import get_provider_config
        _, provider_config = get_provider_config(config)

        key_parts = [
            provider_config.get('host', provider_config.get('database_path', 'localhost')),
            str(provider_config.get('port', '')),
            str(provider_config.get('db', 0)),
            throttle_config.get('cache_key_prefix', 'quota:')
        ]

        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("Cleared QuotaService cache")

    def __init__(self, config: Dict[str, Any], database_service=None, cache_service=None):
        """
        Initialize the Quota Service.

        Args:
            config: Application configuration
            database_service: Database service for persistence
            cache_service: Cache provider (Redis, Memcached, ...) for usage counters
        """
        # Avoid re-initialization if this instance was already initialized
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config
        self.database_service = database_service
        self.cache_service = cache_service
        self.initialized = False

        # Extract throttling configuration
        security_config = config.get('security', {}) or {}
        self.throttle_config = security_config.get('throttling', {}) or {}

        self.enabled = self.throttle_config.get('enabled', False)

        # Default quotas
        default_quotas = self.throttle_config.get('default_quotas', {}) or {}
        self.default_daily_limit = default_quotas.get('daily_limit', 10000)
        self.default_monthly_limit = default_quotas.get('monthly_limit', 100000)

        # Cache key configuration
        self.cache_key_prefix = self.throttle_config.get('cache_key_prefix', 'quota:')

        # Sync configuration
        self.sync_interval = self.throttle_config.get('usage_sync_interval_seconds', 60)

        # Quota cache (in-memory cache for quota configs)
        self._quota_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes cache for quota configs
        self._cache_timestamps: Dict[str, float] = {}

        # Mark as initialized
        self._singleton_initialized = True

        if self.enabled:
            logger.info(
                f"QuotaService initialized: prefix={self.cache_key_prefix}, "
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

        # Verify a cache service is available
        if not self.cache_service or not self.cache_service.enabled:
            logger.warning("QuotaService requires a cache service - service will be limited")
            self.enabled = False
            self.initialized = True
            return

        # Ensure the cache service is initialized
        if not self.cache_service.initialized:
            await self.cache_service.initialize()

        self.initialized = True
        logger.info("QuotaService fully initialized")

    def _get_daily_key(self, api_key: str) -> str:
        """Get cache key for daily usage counter"""
        today = datetime.now(timezone.utc).strftime('%Y%m%d')
        return f"{self.cache_key_prefix}{api_key}:daily:{today}"

    def _get_monthly_key(self, api_key: str) -> str:
        """Get cache key for monthly usage counter"""
        month = datetime.now(timezone.utc).strftime('%Y%m')
        return f"{self.cache_key_prefix}{api_key}:monthly:{month}"

    def _get_last_request_key(self, api_key: str) -> str:
        """Get cache key for last request timestamp"""
        return f"{self.cache_key_prefix}{api_key}:last_request"

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
        if not self.enabled or not self.cache_service or not self.cache_service.enabled:
            return (0, 0, 86400, 2592000)

        try:
            daily_key = self._get_daily_key(api_key)
            monthly_key = self._get_monthly_key(api_key)
            last_request_key = self._get_last_request_key(api_key)

            daily_ttl = self._calculate_daily_ttl()
            monthly_ttl = self._calculate_monthly_ttl()
            timestamp = int(time.time())

            # Both counters increment together atomically on backends that support
            # multi-key transactions (Redis, SQLite); no limits here so nothing
            # can be rejected - see CacheProvider.check_and_increment.
            counts, _ = await self.cache_service.check_and_increment([
                ("daily", daily_key, daily_ttl, None),
                ("monthly", monthly_key, monthly_ttl, None),
            ])
            # Best-effort metadata write, intentionally outside the atomic
            # counter transaction - losing it under a rare partial failure
            # doesn't affect quota correctness.
            await self.cache_service.set(last_request_key, str(timestamp), monthly_ttl)

            daily_ttl_remaining = await self.cache_service.ttl(daily_key)
            monthly_ttl_remaining = await self.cache_service.ttl(monthly_key)

            return (
                counts.get("daily", 0),
                counts.get("monthly", 0),
                daily_ttl_remaining if daily_ttl_remaining > 0 else daily_ttl,
                monthly_ttl_remaining if monthly_ttl_remaining > 0 else monthly_ttl,
            )

        except Exception as e:
            logger.warning(f"Failed to increment quota usage: {e}")
            return (0, 0, 86400, 2592000)

    async def check_and_increment_usage(
        self,
        api_key: str,
        daily_limit: Optional[int],
        monthly_limit: Optional[int]
    ) -> Tuple[int, int, int, int, Optional[str]]:
        """
        Atomically reject over-limit requests or increment usage for accepted ones.

        Args:
            api_key: The API key to check and increment
            daily_limit: Daily hard limit, or None for unlimited
            monthly_limit: Monthly hard limit, or None for unlimited

        Returns:
            Tuple of (
                daily_used,
                monthly_used,
                daily_reset_in_seconds,
                monthly_reset_in_seconds,
                exceeded_type
            ) where exceeded_type is "daily", "monthly", or None.
        """
        if not self.enabled or not self.cache_service or not self.cache_service.enabled:
            return (0, 0, 86400, 2592000, None)

        try:
            daily_key = self._get_daily_key(api_key)
            monthly_key = self._get_monthly_key(api_key)
            last_request_key = self._get_last_request_key(api_key)

            daily_ttl = self._calculate_daily_ttl()
            monthly_ttl = self._calculate_monthly_ttl()
            timestamp = int(time.time())

            # Atomic on backends with multi-key transactions (Redis, SQLite):
            # both limits are checked and both counters incremented as a single
            # transaction, so no request can be double-counted or slip through
            # right at the limit boundary. Memcached lacks that primitive and
            # falls back to a best-effort check-then-increment - see
            # CacheProvider.check_and_increment for the documented tradeoff.
            counts, exceeded = await self.cache_service.check_and_increment([
                ("daily", daily_key, daily_ttl, daily_limit),
                ("monthly", monthly_key, monthly_ttl, monthly_limit),
            ])

            daily_ttl_remaining = await self.cache_service.ttl(daily_key)
            monthly_ttl_remaining = await self.cache_service.ttl(monthly_key)

            if exceeded is None:
                # Best-effort metadata write, intentionally outside the atomic
                # counter transaction - losing it under a rare partial failure
                # doesn't affect quota correctness.
                await self.cache_service.set(last_request_key, str(timestamp), monthly_ttl)

            return (
                counts.get("daily", 0),
                counts.get("monthly", 0),
                daily_ttl_remaining if daily_ttl_remaining > 0 else daily_ttl,
                monthly_ttl_remaining if monthly_ttl_remaining > 0 else monthly_ttl,
                exceeded,
            )

        except Exception as e:
            logger.warning(f"Failed to check quota usage: {e}")
            return (0, 0, 86400, 2592000, None)

    async def get_usage(self, api_key: str) -> Dict[str, Any]:
        """
        Get current usage statistics for an API key without incrementing.

        Args:
            api_key: The API key to get usage for

        Returns:
            Dict with usage statistics
        """
        empty_usage = {
            'daily_used': 0,
            'monthly_used': 0,
            'daily_reset_at': self._calculate_daily_reset_timestamp(),
            'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
            'last_request_at': None
        }

        if not self.enabled or not self.cache_service or not self.cache_service.enabled:
            return empty_usage

        try:
            daily_key = self._get_daily_key(api_key)
            monthly_key = self._get_monthly_key(api_key)
            last_request_key = self._get_last_request_key(api_key)

            daily_str, monthly_str, last_request_str = await self.cache_service.mget(
                daily_key, monthly_key, last_request_key
            )

            return {
                'daily_used': int(daily_str) if daily_str else 0,
                'monthly_used': int(monthly_str) if monthly_str else 0,
                'daily_reset_at': self._calculate_daily_reset_timestamp(),
                'monthly_reset_at': self._calculate_monthly_reset_timestamp(),
                'last_request_at': float(last_request_str) if last_request_str else None
            }

        except Exception as e:
            logger.warning(f"Failed to get quota usage: {e}")
            return empty_usage

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
        if not self.cache_service or not self.cache_service.enabled:
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
                await self.cache_service.delete(*keys_to_delete)

            logger.info(
                f"Reset {period} usage for API key: "
                f"{mask_api_key(api_key, show_last=True, num_chars=6)}"
            )
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
        Sync all cached usage counters to database for persistence.

        Returns:
            Number of keys synced
        """
        # This is a placeholder for future implementation
        # Would scan cache for quota keys and persist to database
        logger.debug("Usage sync to database called (not yet implemented)")
        return 0

    async def shutdown(self) -> None:
        """Cleanup resources on shutdown"""
        # Final sync before shutdown
        await self.sync_usage_to_database()
        logger.info("QuotaService shutdown complete")
