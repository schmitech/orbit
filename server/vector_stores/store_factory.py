"""
Factory functions for creating store instances with configuration.
"""

import logging
from typing import Dict, Any, Optional
from config.config_manager import load_config
from .base.store_manager import StoreManager

logger = logging.getLogger(__name__)


def create_store_manager(config: Optional[Dict[str, Any]] = None) -> StoreManager:
    """
    Create a StoreManager instance with loaded configuration.
    
    Args:
        config: Configuration dictionary (if None, loads from config files)
        
    Returns:
        StoreManager instance with configuration
    """
    if config is None:
        try:
            config = load_config()
            logger.info("Loaded configuration for StoreManager")
        except Exception as e:
            logger.warning(f"Failed to load configuration for StoreManager: {e}, using defaults")
            config = {}
    
    # Extract stores configuration from main config
    stores_config = {}
    if config:
        for key in ['store_manager', 'vector_stores', 'relational_stores', 'document_stores', 'cache_stores', 'performance', 'migration', 'monitoring']:
            if key in config:
                stores_config[key] = config[key]
    
    return StoreManager(stores_config)


def get_configured_store_manager() -> StoreManager:
    """
    Get a singleton-style StoreManager with configuration.
    This should be used when you need a configured StoreManager instance.
    
    Returns:
        StoreManager instance with configuration
    """
    # For now, create a new instance each time
    # Could be modified to use a singleton pattern if needed
    return create_store_manager()