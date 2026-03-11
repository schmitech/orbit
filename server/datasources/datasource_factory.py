"""
Datasource Factory Module

This module provides functionality for initializing various datasource clients
using a registry-based approach. It supports multiple datasource types including
ChromaDB, SQLite, PostgreSQL, Oracle, MySQL, MariaDB, SQL Server, MongoDB, and Cassandra.
"""

import logging
from typing import Any, Dict
from .registry import get_registry

logger = logging.getLogger(__name__)


class DatasourceFactory:
    """
    Factory class for creating datasource clients using the registry pattern.
    
    This class provides a backward-compatible interface while delegating to the
    registry for actual datasource creation and management.
    """
    
    def __init__(self, config: Dict[str, Any], logger):
        """
        Initialize the DatasourceFactory.
        
        Args:
            config: The application configuration dictionary
            logger: Logger instance for logging operations
        """
        self.config = config
        self.logger = logger
        self.registry = get_registry()
    
    async def initialize_datasource_client(self, provider: str) -> Any:
        """
        Initialize a datasource client based on the selected provider.
        
        Args:
            provider: The datasource provider to initialize
            
        Returns:
            An initialized datasource client or None if initialization fails
        """
        logger.info(f"Initializing datasource client using registry pattern: {provider}")
        
        try:
            # Create datasource instance using registry
            datasource = self.registry.create_datasource(provider, self.config, self.logger)
            
            if datasource is None:
                logger.error(f"Failed to create datasource: {provider}")
                return None
            
            await datasource.initialize()
            
            # Return the client
            return datasource.get_client()
            
        except Exception as e:
            logger.error(f"Failed to initialize datasource {provider}: {str(e)}")
            return None 
