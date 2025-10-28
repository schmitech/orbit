"""
File Processor Registry

Manages available file processors and routes requests to appropriate processors.
"""

import logging
from typing import Dict, List, Optional
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)


class FileProcessorRegistry:
    """
    Registry for file processors.
    
    Automatically discovers and manages file format processors.
    """
    
    def __init__(self):
        """Initialize processor registry."""
        self._processors: List[FileProcessor] = []
        self._initialized = False
        self._register_builtin_processors()
    
    def _register_builtin_processors(self):
        """Register built-in file processors."""
        # Register Docling first (universal processor, acts as fallback)
        try:
            from .docling_processor import DoclingProcessor
            self.register(DoclingProcessor())
            logger.info("Registered DoclingProcessor (IBM Docling for advanced document understanding)")
        except ImportError as e:
            logger.debug(f"DoclingProcessor not available: {e}")
        
        # Register format-specific processors
        try:
            from .text_processor import TextProcessor
            self.register(TextProcessor())
        except ImportError as e:
            logger.warning(f"Could not import TextProcessor: {e}")
        
        try:
            from .pdf_processor import PDFProcessor
            self.register(PDFProcessor())
        except ImportError as e:
            logger.debug(f"PDFProcessor not available: {e}")
        
        try:
            from .docx_processor import DOCXProcessor
            self.register(DOCXProcessor())
        except ImportError as e:
            logger.debug(f"DOCXProcessor not available: {e}")
        
        try:
            from .csv_processor import CSVProcessor
            self.register(CSVProcessor())
        except ImportError as e:
            logger.debug(f"CSVProcessor not available: {e}")
        
        try:
            from .json_processor import JSONProcessor
            self.register(JSONProcessor())
        except ImportError as e:
            logger.debug(f"JSONProcessor not available: {e}")
        
        try:
            from .html_processor import HTMLProcessor
            self.register(HTMLProcessor())
        except ImportError as e:
            logger.debug(f"HTMLProcessor not available: {e}")
    
    def register(self, processor: FileProcessor):
        """
        Register a file processor.
        
        Args:
            processor: Processor instance to register
        """
        if processor not in self._processors:
            self._processors.append(processor)
            logger.debug(f"Registered processor: {processor.__class__.__name__}")
    
    def get_processor(self, mime_type: str) -> Optional[FileProcessor]:
        """
        Get processor for a given MIME type.
        
        Args:
            mime_type: MIME type to find processor for
            
        Returns:
            Processor instance or None if not found
        """
        for processor in self._processors:
            if processor.supports_mime_type(mime_type):
                return processor
        
        return None
    
    def list_supported_types(self) -> List[str]:
        """List all supported MIME types."""
        types = set()
        for processor in self._processors:
            # This is a simplified approach - in practice, each processor would
            # expose its supported MIME types
            types.add(f"processor:{processor.__class__.__name__}")
        return list(types)
