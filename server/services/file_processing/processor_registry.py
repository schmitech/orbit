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
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize processor registry.
        
        Args:
            config: Optional configuration dictionary to check for docling enable/disable setting
        """
        self._processors: List[FileProcessor] = []
        self._initialized = False
        self.config = config or {}
        self._register_builtin_processors()
    
    def _register_builtin_processors(self):
        """Register built-in file processors."""
        # Check if docling is enabled in config
        # Default to enabled for backward compatibility
        files_config = self.config.get('files', {})
        processing_config = files_config.get('processing', {})
        docling_enabled = processing_config.get('docling_enabled', True)
        
        # Register Docling first (universal processor, acts as fallback)
        if docling_enabled:
            try:
                from .docling_processor import DoclingProcessor
                self.register(DoclingProcessor(enabled=True))
                logger.info("Registered DoclingProcessor (IBM Docling for advanced document understanding)")
            except ImportError as e:
                logger.debug(f"DoclingProcessor not available: {e}")
        else:
            logger.info("Docling processor is disabled in configuration (prevents outbound connections to HuggingFace)")
        
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

        try:
            from .pptx_processor import PPTXProcessor
            self.register(PPTXProcessor())
        except ImportError as e:
            logger.debug(f"PPTXProcessor not available: {e}")

        try:
            from .xlsx_processor import XLSXProcessor
            self.register(XLSXProcessor())
        except ImportError as e:
            logger.debug(f"XLSXProcessor not available: {e}")

        try:
            from .vtt_processor import VTTProcessor
            self.register(VTTProcessor())
        except ImportError as e:
            logger.debug(f"VTTProcessor not available: {e}")
    
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
                processor_name = processor.__class__.__name__
                if processor_name == "DoclingProcessor":
                    logger.debug(f"Selected DoclingProcessor for MIME type '{mime_type}' (advanced document understanding)")
                else:
                    logger.debug(f"Selected {processor_name} for MIME type '{mime_type}' (format-specific processor)")
                return processor

        logger.debug(f"No processor found for MIME type '{mime_type}'")
        return None
    
    def list_supported_types(self) -> List[str]:
        """List all supported MIME types."""
        types = set()
        for processor in self._processors:
            # This is a simplified approach - in practice, each processor would
            # expose its supported MIME types
            types.add(f"processor:{processor.__class__.__name__}")
        return list(types)
