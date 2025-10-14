"""
Datasource Factory Module

This module provides functionality for initializing various datasource clients
using a registry-based approach. It supports multiple datasource types including
ChromaDB, SQLite, PostgreSQL, Oracle, MySQL, MariaDB, SQL Server, MongoDB, and Cassandra.
"""

from typing import Any, Dict, Optional
from .registry import get_registry


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
    
    def initialize_datasource_client(self, provider: str) -> Any:
        """
        Initialize a datasource client based on the selected provider.
        
        Args:
            provider: The datasource provider to initialize
            
        Returns:
            An initialized datasource client or None if initialization fails
        """
        self.logger.info(f"Initializing datasource client using registry pattern: {provider}")
        
        try:
            # Create datasource instance using registry
            datasource = self.registry.create_datasource(provider, self.config, self.logger)
            
            if datasource is None:
                self.logger.error(f"Failed to create datasource: {provider}")
                return None
            
            # Initialize the datasource (this will be async in the future)
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in an async context, we can't use run_until_complete
                    # For now, we'll handle this synchronously
                    self.logger.warning(f"Async initialization not supported in sync context for {provider}")
                    return None
                else:
                    loop.run_until_complete(datasource.initialize())
            except RuntimeError:
                # No event loop running, create one
                asyncio.run(datasource.initialize())
            
            # Return the client
            return datasource.get_client()
            
        except Exception as e:
            self.logger.error(f"Failed to initialize datasource {provider}: {str(e)}")
            return None 