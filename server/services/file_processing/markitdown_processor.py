"""
MarkItDown Universal Processor

Handles multiple document formats using Microsoft's MarkItDown library.
Supports: PDF, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML,
          images, audio, ZIP, EPUB, and more.
"""

import logging
import tempfile
import os
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False
    logger.warning("markitdown not available. MarkItDown document processing disabled.")


class MarkItDownProcessor(FileProcessor):
    """
    Universal processor for multiple document formats using Microsoft MarkItDown.

    Supports: PDF, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML,
              images (EXIF/OCR), audio (transcription), ZIP, EPUB, YouTube URLs

    Converts documents to clean Markdown format, ideal for LLM consumption.

    Requires: markitdown (pip install markitdown[all])
    """

    def __init__(self, enabled: bool = True, enable_plugins: bool = False):
        """
        Initialize MarkItDown processor.

        Args:
            enabled: Whether markitdown is enabled. If False, converter will not be initialized.
            enable_plugins: Whether to enable third-party plugins (default False for security).
        """
        super().__init__()
        self._converter = None
        self._enabled = enabled
        self._enable_plugins = enable_plugins
        self._initialized = False
        # Don't initialize converter at startup - use lazy initialization

    def _ensure_initialized(self):
        """Lazy initialization of MarkItDown - only when actually needed."""
        if self._initialized:
            return

        if not self._enabled:
            self._initialized = True
            return

        if not MARKITDOWN_AVAILABLE:
            self._initialized = True
            return

        try:
            logger.debug("Lazy initializing MarkItDown converter")
            self._converter = MarkItDown(enable_plugins=self._enable_plugins)
            self._initialized = True
            logger.debug("MarkItDown converter initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize MarkItDown converter: {e}")
            self._initialized = True  # Mark as initialized to prevent retries

    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        if not self._enabled or not MARKITDOWN_AVAILABLE:
            return False

        # MarkItDown supports a wide range of formats
        # NOTE: CSV and JSON are excluded here to use native token-optimized processors
        # which are more efficient for LLMs with limited context windows
        supported_types = [
            # Documents
            'application/pdf',
            'application/msword',  # DOC
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
            'application/vnd.ms-powerpoint',  # PPT
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
            'application/vnd.ms-excel',  # XLS (old Excel - MarkItDown supports this!)

            # Text formats
            'text/html',
            # CSV excluded - use native CSVProcessor for token-efficient output
            'text/plain',
            'text/markdown',
            'text/xml',
            'application/xml',
            # JSON excluded - use native JSONProcessor for token-efficient output

            # Images (EXIF metadata extraction)
            'image/png',
            'image/jpeg',
            'image/gif',
            'image/webp',
            'image/tiff',

            # Audio (transcription support)
            'audio/wav',
            'audio/mpeg',
            'audio/mp3',
            'audio/ogg',
            'audio/flac',
            'audio/webm',
            'audio/x-m4a',

            # Archives
            'application/zip',
            'application/x-zip-compressed',

            # Ebooks
            'application/epub+zip',

            # Outlook
            'application/vnd.ms-outlook',  # MSG files
        ]

        return mime_type.lower() in supported_types

    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from document using MarkItDown."""
        if not self._enabled:
            raise ValueError("MarkItDown processor is disabled")
        if not MARKITDOWN_AVAILABLE:
            raise ImportError("markitdown not available")

        logger.info(f"[MarkItDown] Starting text extraction for: {filename or 'unknown'} ({len(file_data)} bytes)")

        # Lazy initialization - only create converter when actually processing a file
        self._ensure_initialized()

        if not self._converter:
            raise RuntimeError("MarkItDown converter failed to initialize")

        try:
            # MarkItDown requires a file path, so we'll create a temporary file
            # Preserve the original extension for proper format detection
            suffix = ""
            if filename:
                _, ext = os.path.splitext(filename)
                if ext:
                    suffix = ext
                    logger.debug(f"[MarkItDown] Using file extension: {ext}")

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_data)
                temp_path = temp_file.name

            try:
                logger.debug("[MarkItDown] Converting document to markdown...")
                # Convert document to markdown
                result = self._converter.convert(temp_path)

                # Extract text content
                if hasattr(result, 'text_content') and result.text_content:
                    text_length = len(result.text_content)
                    logger.info(f"[MarkItDown] Successfully extracted {text_length} characters from {filename or 'unknown'}")
                    return result.text_content

                logger.warning(f"[MarkItDown] No text content extracted from {filename or 'unknown'}")
                return ""

            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            logger.error(f"[MarkItDown] Error processing document '{filename or 'unknown'}': {e}")
            raise

    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from document."""
        metadata = await super().extract_metadata(file_data, filename)

        if not self._enabled:
            return metadata
        if not MARKITDOWN_AVAILABLE:
            return metadata

        # Lazy initialization
        self._ensure_initialized()

        if not self._converter:
            return metadata

        try:
            # Add processor identification
            metadata['processed_by'] = 'markitdown'

            # MarkItDown doesn't expose detailed metadata like Docling,
            # but we can add basic info
            if filename:
                _, ext = os.path.splitext(filename)
                metadata['format'] = ext.lstrip('.').upper() if ext else 'unknown'

        except Exception as e:
            logger.warning(f"Error extracting MarkItDown metadata: {e}")

        return metadata

    def supports_advanced_features(self) -> bool:
        """Check if advanced features are enabled."""
        return self._enabled and MARKITDOWN_AVAILABLE

    def get_supported_formats(self) -> list:
        """Get list of supported document formats."""
        if not MARKITDOWN_AVAILABLE:
            return []

        return [
            'PDF', 'DOC', 'DOCX', 'PPT', 'PPTX', 'XLS', 'XLSX',
            'HTML', 'CSV', 'JSON', 'XML',
            'PNG', 'JPEG', 'GIF', 'WEBP', 'TIFF',
            'WAV', 'MP3', 'OGG', 'FLAC',
            'ZIP',
            'EPUB',
            'MSG (Outlook)',
            'YouTube URLs',
        ]
