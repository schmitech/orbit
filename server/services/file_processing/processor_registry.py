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
        # Check processor configuration
        files_config = self.config.get('files', {})
        processing_config = files_config.get('processing', {})

        # Universal processor settings
        docling_enabled = processing_config.get('docling_enabled', True)
        markitdown_enabled = processing_config.get('markitdown_enabled', False)
        processor_priority = processing_config.get('processor_priority', 'docling')

        # MarkItDown specific config
        markitdown_config = processing_config.get('markitdown', {})
        enable_plugins = markitdown_config.get('enable_plugins', False)

        # Register universal processors based on priority
        # First registered processor gets priority for overlapping MIME types
        if processor_priority == 'markitdown':
            # MarkItDown first, Docling as fallback
            self._register_markitdown(markitdown_enabled, enable_plugins)
            self._register_docling(docling_enabled)
        else:
            # Docling first (default), MarkItDown as fallback
            self._register_docling(docling_enabled)
            self._register_markitdown(markitdown_enabled, enable_plugins)

        # Register native format-specific processors as final fallback
        self._register_native_processors()

    def _register_docling(self, enabled: bool):
        """Register Docling processor if enabled."""
        if enabled:
            try:
                from .docling_processor import DoclingProcessor
                self.register(DoclingProcessor(enabled=True))
                logger.info("Registered DoclingProcessor (IBM Docling for advanced document understanding)")
            except ImportError as e:
                logger.debug(f"DoclingProcessor not available: {e}")
        else:
            logger.info("Docling processor is disabled in configuration (prevents outbound connections to HuggingFace)")

    def _register_markitdown(self, enabled: bool, enable_plugins: bool = False):
        """Register MarkItDown processor if enabled."""
        if enabled:
            try:
                from .markitdown_processor import MarkItDownProcessor
                self.register(MarkItDownProcessor(enabled=True, enable_plugins=enable_plugins))
                logger.info("Registered MarkItDownProcessor (Microsoft MarkItDown for document conversion)")
            except ImportError as e:
                logger.debug(f"MarkItDownProcessor not available: {e}")
        else:
            logger.debug("MarkItDown processor is disabled in configuration")

    def _register_native_processors(self):
        
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
            self.register(CSVProcessor(config=self.config))
        except ImportError as e:
            logger.debug(f"CSVProcessor not available: {e}")

        try:
            from .json_processor import JSONProcessor
            self.register(JSONProcessor(config=self.config))
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
        Get the first processor for a given MIME type.

        Args:
            mime_type: MIME type to find processor for

        Returns:
            Processor instance or None if not found
        """
        processors = self.get_processors(mime_type)
        return processors[0] if processors else None

    def get_processors(self, mime_type: str) -> List[FileProcessor]:
        """
        Get all processors that support a given MIME type, in priority order.

        Args:
            mime_type: MIME type to find processors for

        Returns:
            List of matching processor instances (highest priority first)
        """
        matching = []
        for processor in self._processors:
            if processor.supports_mime_type(mime_type):
                matching.append(processor)

        if matching:
            logger.debug(
                f"[ProcessorRegistry] Found {len(matching)} processor(s) for MIME type '{mime_type}': "
                f"{', '.join(p.__class__.__name__ for p in matching)}"
            )
        else:
            logger.warning(f"[ProcessorRegistry] No processor found for MIME type '{mime_type}'")

        return matching
    
    def list_supported_types(self) -> List[str]:
        """List all supported MIME types."""
        types = set()
        for processor in self._processors:
            # This is a simplified approach - in practice, each processor would
            # expose its supported MIME types
            types.add(f"processor:{processor.__class__.__name__}")
        return list(types)
