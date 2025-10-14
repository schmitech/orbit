"""
Base Datasource Class

Abstract base class defining the interface for all datasource implementations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseDatasource(ABC):
    """
    Abstract base class for all datasource implementations.
    
    This class defines the common interface that all datasource implementations
    must follow, ensuring consistency across different database types.
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the base datasource.
        
        Args:
            config: Configuration dictionary containing datasource settings
            logger: Logger instance for logging operations
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._client = None
        self._initialized = False
    
    @property
    @abstractmethod
    def datasource_name(self) -> str:
        """
        Return the name of this datasource for configuration lookup.
        
        Returns:
            String name of the datasource (e.g., 'mysql', 'mongodb', 'oracle')
        """
        pass
    
    @property
    def client(self) -> Any:
        """
        Get the datasource client.
        
        Returns:
            The initialized datasource client
        """
        if not self._initialized:
            raise RuntimeError(f"Datasource {self.datasource_name} not initialized. Call initialize() first.")
        return self._client
    
    @property
    def is_initialized(self) -> bool:
        """Check if the datasource is initialized."""
        return self._initialized
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the datasource client and establish connection.
        
        This method should:
        - Load datasource-specific configuration
        - Create and configure the client
        - Test the connection
        - Set self._client and self._initialized = True
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Perform a health check on the datasource connection.
        
        Returns:
            True if the datasource is healthy and accessible, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the datasource connection and clean up resources.
        """
        pass
    
    def get_client(self) -> Any:
        """
        Get the datasource client (synchronous version).
        
        Returns:
            The initialized datasource client
            
        Raises:
            RuntimeError: If the datasource is not initialized
        """
        return self.client
