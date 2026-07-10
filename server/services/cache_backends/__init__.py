"""
Pluggable cache backends (Redis, Memcached, ...) behind a common CacheProvider interface.

Not to be confused with server/services/cache/, which holds in-process
singleton caches for adapter/provider/model instances.
"""

from .base import CacheProvider, is_cache_master_enabled
from .factory import create_cache_service, get_provider_config, is_provider_enabled

__all__ = [
    "CacheProvider",
    "create_cache_service",
    "get_provider_config",
    "is_cache_master_enabled",
    "is_provider_enabled",
]
