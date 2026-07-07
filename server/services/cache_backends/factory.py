"""
Cache Provider Factory
=======================

Single extension point for cache backends. To add a new provider:
1. Implement CacheProvider in its own module.
2. Add it to _PROVIDERS below.
3. Add its connection settings under internal_services.<config section> in config.yaml,
   and register that section name in _PROVIDER_CONFIG_SECTIONS if it differs from the
   provider name (e.g. "sqlite" -> "sqlite_cache", to avoid colliding with the
   internal_services.backend.sqlite document-database config).
"""

import logging
from typing import Any, Dict, Tuple

from .base import CacheProvider
from .memcached_provider import MemcachedCacheProvider
from .redis_provider import RedisCacheProvider
from .sqlite_provider import SqliteCacheProvider

logger = logging.getLogger(__name__)

_PROVIDERS = {
    "redis": RedisCacheProvider,
    "memcached": MemcachedCacheProvider,
    "sqlite": SqliteCacheProvider,
}

# Maps provider name -> internal_services config section name, for providers whose
# section name isn't identical to the provider name.
_PROVIDER_CONFIG_SECTIONS = {
    "sqlite": "sqlite_cache",
}


def get_provider_config(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Resolve the configured provider name and its internal_services config section."""
    provider_name = config.get('internal_services', {}).get('cache', {}).get('provider', 'redis')
    provider_name = (provider_name or 'redis').lower()
    section_name = _PROVIDER_CONFIG_SECTIONS.get(provider_name, provider_name)
    provider_config = config.get('internal_services', {}).get(section_name, {})
    return provider_name, provider_config


def create_cache_service(config: Dict[str, Any]) -> CacheProvider:
    """Instantiate the configured cache provider (internal_services.cache.provider)."""
    provider_name, _ = get_provider_config(config)

    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        logger.error(
            f"Unknown cache provider '{provider_name}', supported: {list(_PROVIDERS)}. Falling back to redis."
        )
        provider_cls = RedisCacheProvider

    logger.debug(f"Using cache provider: {provider_name}")
    return provider_cls(config)
