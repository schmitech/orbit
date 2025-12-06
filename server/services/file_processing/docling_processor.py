"""
Docling Universal Processor

Handles multiple document formats using IBM's Docling library.
Supports: PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, XML, images, VTT, and more.
"""

import logging
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from io import BytesIO
    import tempfile
    import os
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    logger.warning("docling not available. Advanced document processing disabled.")


class DoclingProcessor(FileProcessor):
    """
    Universal processor for multiple document formats using IBM Docling.
    
    Supports: PDF, DOCX, PPTX, XLSX, HTML, XHTML, Markdown, AsciiDoc, CSV, JSON, XML, images, VTT
    Provides advanced PDF understanding including:
    - Page layout and reading order
    - Table structure extraction
    - Code detection
    - Formula recognition
    - Image classification
    
    Requires: docling
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize Docling processor.
        
        Args:
            enabled: Whether docling is enabled. If False, converter will not be initialized.
        """
        super().__init__()
        self._converter = None
        self._enabled = enabled
        self._initialized = False
        # Don't initialize converter at startup - use lazy initialization
        # This prevents outbound connections to HuggingFace during server startup
    
    def _ensure_initialized(self):
        """Lazy initialization of DocumentConverter - only when actually needed."""
        if self._initialized:
            return
        
        if not self._enabled:
            self._initialized = True
            return
        
        if not DOCLING_AVAILABLE:
            self._initialized = True
            return
        
        try:
            logger.debug("Lazy initializing Docling DocumentConverter (this may connect to HuggingFace)")
            self._converter = DocumentConverter()
            self._initialized = True
            logger.debug("Docling DocumentConverter initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Docling converter: {e}")
            self._initialized = True  # Mark as initialized to prevent retries
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        if not self._enabled or not DOCLING_AVAILABLE:
            return False
        # Don't initialize converter just to check support - use lazy init
        # We can return True for supported types without initializing
        
        # Docling supports a wide range of formats
        supported_types = [
            # Documents
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
            # Markup/Text
            'text/html',
            'application/xhtml+xml',  # XHTML
            'text/markdown',
            'text/x-markdown',
            'text/asciidoc',
            'text/x-asciidoc',
            'text/csv',
            # Note: 'application/json' removed - Docling only supports its own
            # serialized format, not arbitrary JSON files. Regular JSON should
            # be handled by a dedicated JSON processor.
            # XML formats (USPTO, JATS)
            'application/xml',
            'text/xml',
            # Images
            'image/png',
            'image/jpeg',
            'image/tiff',
            'image/bmp',
            'image/webp',
            # Subtitles
            'text/vtt',
        ]
        
        return mime_type.lower() in supported_types
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from document using Docling."""
        if not self._enabled:
            raise ValueError("Docling processor is disabled")
        if not DOCLING_AVAILABLE:
            raise ImportError("docling not available")

        logger.info(f"[Docling] Starting text extraction for: {filename or 'unknown'} ({len(file_data)} bytes)")

        # Lazy initialization - only create converter when actually processing a file
        self._ensure_initialized()

        if not self._converter:
            raise RuntimeError("Docling converter failed to initialize")

        text_parts = []

        # Get file extension from filename for Docling format detection
        suffix = ''
        if filename:
            _, ext = os.path.splitext(filename)
            if ext:
                suffix = ext

        try:
            # Docling requires a file path, so we'll create a temporary file
            # Preserve file extension so Docling can detect the format
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_data)
                temp_path = temp_file.name

            try:
                logger.debug(f"[Docling] Converting document to markdown...")
                # Convert document
                result = self._converter.convert(temp_path)

                # Extract text from document
                # Docling provides rich document structure
                if hasattr(result, 'document'):
                    doc = result.document

                    # Export to markdown for clean text extraction
                    markdown_text = doc.export_to_markdown()
                    if markdown_text:
                        text_parts.append(markdown_text)

            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

            extracted_text = "\n\n".join(text_parts)
            logger.debug(f"[Docling] Successfully extracted {len(extracted_text)} characters from {filename or 'unknown'}")
            return extracted_text

        except Exception as e:
            logger.error(f"[Docling] Error processing document '{filename or 'unknown'}': {e}")
            raise
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from document."""
        metadata = await super().extract_metadata(file_data, filename)
        
        if not self._enabled:
            return metadata
        if not DOCLING_AVAILABLE:
            return metadata
        
        # Lazy initialization - only create converter when actually processing a file
        self._ensure_initialized()
        
        if not self._converter:
            return metadata
        
        # Get file extension from filename for Docling format detection
        suffix = ''
        if filename:
            _, ext = os.path.splitext(filename)
            if ext:
                suffix = ext

        try:
            # Docling provides rich metadata about document structure
            # This can include page count, sections, tables, images, etc.
            
            # Preserve file extension so Docling can detect the format
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_data)
                temp_path = temp_file.name
            
            try:
                result = self._converter.convert(temp_path)
                
                if hasattr(result, 'document'):
                    doc = result.document
                    
                    # Extract document-level metadata
                    if hasattr(doc, 'page_count'):
                        metadata['page_count'] = doc.page_count
                    
                    # Extract structure information
                    # This depends on Docling's API - adjust based on actual API
                    metadata['has_structure'] = True
                    metadata['processed_by'] = 'docling'
            
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        
        except Exception as e:
            logger.warning(f"Error extracting Docling metadata: {e}")
        
        return metadata
    
    def get_converter_config(self) -> Dict[str, Any]:
        """
        Get Docling converter configuration.
        
        Returns:
            Configuration dictionary for Docling settings
        """
        return {
            'do_table_structure': True,
            'do_caption': True,
            'do_footer': True,
            'do_page_header': True,
            'split_by_page': False,  # Keep full document together
            'formats': ['text/markdown', 'application/json'],  # Output formats
        }
    
    def supports_advanced_features(self) -> bool:
        """Check if advanced features are enabled."""
        return self._enabled and DOCLING_AVAILABLE
    
    def get_supported_formats(self) -> list:
        """Get list of supported document formats."""
        if not DOCLING_AVAILABLE:
            return []
        
        return [
            'PDF', 'DOCX', 'PPTX', 'XLSX',
            'HTML', 'XHTML', 'Markdown', 'AsciiDoc',
            'CSV', 'XML',
            'PNG', 'JPEG', 'TIFF', 'BMP', 'WebP',
            'VTT'
        ]
