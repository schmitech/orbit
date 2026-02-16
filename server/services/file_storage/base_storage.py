"""
Base Storage Backend Interface

Abstract base class for file storage implementations.
Supports pluggable storage backends (filesystem, S3, MinIO, etc.).
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class FileStorageBackend(ABC):
    """
    Abstract base class for file storage backends.
    
    Defines the interface that all storage implementations must follow.
    This abstraction enables switching between filesystem, S3, MinIO, etc.
    without changing adapter code.
    """
    
    @abstractmethod
    async def put_file(self, file_data: bytes, key: str, metadata: Dict[str, Any]) -> str:
        """
        Store a file with metadata.
        
        Args:
            file_data: File contents as bytes
            key: Storage key/path for the file
            metadata: File metadata dictionary
            
        Returns:
            Final storage key/path
        """
        pass
    
    @abstractmethod
    async def get_file(self, key: str) -> bytes:
        """
        Retrieve a file by key.
        
        Args:
            key: Storage key/path
            
        Returns:
            File contents as bytes
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass
    
    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """
        Delete a file by key.
        
        Args:
            key: Storage key/path
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def list_files(self, prefix: str) -> List[str]:
        """
        List files with a given prefix.
        
        Args:
            prefix: Key prefix to filter by
            
        Returns:
            List of file keys
        """
        pass
    
    @abstractmethod
    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """
        Get file metadata.
        
        Args:
            key: Storage key/path
            
        Returns:
            File metadata dictionary
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass
    
    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """
        Check if a file exists.
        
        Args:
            key: Storage key/path
            
        Returns:
            True if file exists, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_file_size(self, key: str) -> int:
        """
        Get file size in bytes.
        
        Args:
            key: Storage key/path
            
        Returns:
            File size in bytes
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass
