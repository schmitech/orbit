"""
Base File Processor

Abstract base class for file format processors.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)


class FileProcessor(ABC):
    """
    Abstract base class for file processors.
    
    Each processor handles a specific file format or set of formats.
    """
    
    def __init__(self):
        """Initialize processor."""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def supports_mime_type(self, mime_type: str) -> bool:
        """
        Check if this processor supports a given MIME type.
        
        Args:
            mime_type: MIME type to check
            
        Returns:
            True if supported, False otherwise
        """
        pass
    
    @abstractmethod
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """
        Extract plain text from file.
        
        Args:
            file_data: File contents as bytes
            filename: Optional filename for context
            
        Returns:
            Extracted text content
        """
        pass
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """
        Extract metadata from file.
        
        Args:
            file_data: File contents as bytes
            filename: Optional filename for context
            
        Returns:
            Dictionary of metadata
        """
        metadata = {
            'filename': filename,
            'file_size': len(file_data),
        }
        return metadata
