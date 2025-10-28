"""
Docling Universal Processor

Handles multiple document formats using IBM's Docling library.
Supports: PDF, DOCX, PPTX, XLSX, HTML, images, audio, and more.
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
    
    Supports: PDF, DOCX, PPTX, XLSX, HTML, images, audio, VTT, and more
    Provides advanced PDF understanding including:
    - Page layout and reading order
    - Table structure extraction
    - Code detection
    - Formula recognition
    - Image classification
    
    Requires: docling
    """
    
    def __init__(self):
        """Initialize Docling processor."""
        super().__init__()
        self._converter = None
        if DOCLING_AVAILABLE:
            try:
                self._converter = DocumentConverter()
            except Exception as e:
                self.logger.warning(f"Failed to initialize Docling converter: {e}")
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        if not DOCLING_AVAILABLE or not self._converter:
            return False
        
        # Docling supports a wide range of formats
        supported_types = [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
            'text/html',
            'image/png',
            'image/jpeg',
            'image/tiff',
            'audio/wav',
            'audio/mpeg',
            'text/vtt',
        ]
        
        return mime_type.lower() in supported_types
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from document using Docling."""
        if not DOCLING_AVAILABLE or not self._converter:
            raise ImportError("docling not available")
        
        text_parts = []
        
        try:
            # Docling requires a file path, so we'll create a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_data)
                temp_path = temp_file.name
            
            try:
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
            
            return "\n\n".join(text_parts)
        
        except Exception as e:
            self.logger.error(f"Error processing document with Docling: {e}")
            raise
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from document."""
        metadata = await super().extract_metadata(file_data, filename)
        
        if not DOCLING_AVAILABLE or not self._converter:
            return metadata
        
        try:
            # Docling provides rich metadata about document structure
            # This can include page count, sections, tables, images, etc.
            
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
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
            self.logger.warning(f"Error extracting Docling metadata: {e}")
        
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
        return DOCLING_AVAILABLE and self._converter is not None
    
    def get_supported_formats(self) -> list:
        """Get list of supported document formats."""
        if not DOCLING_AVAILABLE:
            return []
        
        return [
            'PDF', 'DOCX', 'PPTX', 'XLSX',
            'HTML', 'Markdown',
            'PNG', 'JPEG', 'TIFF',
            'WAV', 'MP3',
            'VTT',
            'And more...'
        ]
