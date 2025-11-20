"""
Base store class providing common interface for vector storage backends.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StoreType(Enum):
    """Types of storage backends."""
    VECTOR = "vector"
    RELATIONAL = "relational" 
    DOCUMENT = "document"
    CACHE = "cache"
    HYBRID = "hybrid"


class StoreStatus(Enum):
    """Store connection status."""
    UNINITIALIZED = "uninitialized"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class StoreConfig:
    """Configuration for a vector store instance."""
    name: str
    connection_params: Dict[str, Any]
    pool_size: int = 5
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    ephemeral: bool = False  # If True, data is temporary
    auto_cleanup: bool = True  # Auto cleanup on close
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseStore(ABC):
    """
    Abstract base class for vector storage implementations.
    
    This provides a unified interface for:
    - Connection management
    - Vector CRUD operations
    - Collection management
    - Resource cleanup
    """
    
    def __init__(self, config: StoreConfig):
        """
        Initialize the store with configuration.

        Args:
            config: Store configuration
        """
        self.config = config
        self.status = StoreStatus.UNINITIALIZED
        self._lock = asyncio.Lock()
        self._created_at = datetime.now(timezone.utc)
        self._last_accessed = datetime.now(timezone.utc)
        self._operation_count = 0
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the storage backend.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection to the storage backend.
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the store is healthy and operational.
        
        Returns:
            True if healthy, False otherwise
        """
        pass
    
    async def ensure_connected(self) -> bool:
        """
        Ensure the store is connected, attempting to connect if not.
        
        Returns:
            True if connected, False otherwise
        """
        if self.status == StoreStatus.CONNECTED:
            # Verify connection is still healthy
            if await self.health_check():
                return True
            else:
                self.status = StoreStatus.DISCONNECTED
        
        if self.status != StoreStatus.CONNECTED:
            return await self.connect()
        
        return True
    
    async def with_retry(self, operation, *args, **kwargs):
        """
        Execute an operation with retry logic.
        
        Args:
            operation: Async function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation
            
        Returns:
            Result of the operation
        """
        last_error = None
        for attempt in range(self.config.retry_attempts):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    logger.warning(f"Retry {attempt + 1}/{self.config.retry_attempts} for {operation.__name__}: {e}")
        
        raise last_error
    
    def update_access_time(self):
        """Update the last accessed timestamp."""
        self._last_accessed = datetime.now(timezone.utc)
        self._operation_count += 1
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the store.
        
        Returns:
            Dictionary of statistics
        """
        return {
            'store_name': self.config.name,
            'status': self.status.value,
            'ephemeral': self.config.ephemeral,
            'operation_count': self._operation_count,
            'created_at': self._created_at.isoformat(),
            'last_accessed': self._last_accessed.isoformat()
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
    
    def __repr__(self) -> str:
        """String representation of the store."""
        return (f"{self.__class__.__name__}("
                f"name='{self.config.name}', "
                f"status={self.status.value})")