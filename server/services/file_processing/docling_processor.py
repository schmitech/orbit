"""
Docling Universal Processor

Handles multiple document formats using IBM's Docling library.
Supports: PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, XML, images, VTT, and more.
"""

import logging
from typing import Any

from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    # Docling expects torch.xpu to exist (for Intel XPU builds). Some CPU-only
    # PyTorch wheels omit the attribute, which causes runtime errors. We provide
    # a minimal stub before docling imports torch so CPU installs keep working.
    import torch  # type: ignore
    if not hasattr(torch, "xpu"):
        import types

        torch.xpu = types.SimpleNamespace(  # type: ignore[attr-defined]
            is_available=lambda: False,
            device_count=lambda: 0,
            current_device=lambda: None,
        )
except Exception:  # noqa: BLE001 - optional torch.xpu shim, must not break CPU-only installs
    torch = None  # type: ignore

try:
    import os
    import tempfile
    from io import BytesIO  # noqa: F401

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
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
        self._last_tables: list[dict[str, Any]] = []
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
            pipeline_options = PdfPipelineOptions(do_table_structure=True)
            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                }
            )
            self._initialized = True
            logger.debug("Docling DocumentConverter initialized successfully")
        except Exception as e:  # noqa: BLE001 - docling library init boundary, must not crash the app
            logger.warning(f"Failed to initialize Docling converter: {e}")
            self._initialized = True  # Mark as initialized to prevent retries
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        if not self._enabled or not DOCLING_AVAILABLE:
            return False
        # Don't initialize converter just to check support - use lazy init
        # We can return True for supported types without initializing
        
        # Docling supports a wide range of formats
        # NOTE: CSV and JSON are excluded here to use native token-optimized processors
        # which are more efficient for LLMs with limited context windows
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
            # CSV excluded - use native CSVProcessor for token-efficient output
            # JSON excluded - use native JSONProcessor for token-efficient output
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
    
    async def extract_text(self, file_data: bytes, filename: str | None = None) -> str:
        """Extract text from document using Docling."""
        if not self._enabled:
            raise ValueError("Docling processor is disabled")
        if not DOCLING_AVAILABLE:
            raise ImportError("docling not available")

        logger.debug(f"[Docling] Starting text extraction for: {filename or 'unknown'} ({len(file_data)} bytes)")

        # Lazy initialization - only create converter when actually processing a file
        self._ensure_initialized()

        if not self._converter:
            raise RuntimeError("Docling converter failed to initialize")

        text_parts = []
        self._last_tables = []

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
                logger.debug("[Docling] Converting document to markdown...")
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

                    self._last_tables = self._extract_tables(doc)

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
    
    def _extract_tables(self, doc: Any) -> list[dict[str, Any]]:
        """Extract structured table data (cells, dimensions, page number) from a converted Docling document."""
        tables: list[dict[str, Any]] = []

        for table_index, table_item in enumerate(getattr(doc, 'tables', []) or []):
            data = getattr(table_item, 'data', None)
            if data is None:
                continue

            prov = getattr(table_item, 'prov', None) or []
            page_numbers = sorted({
                getattr(item, 'page_no', None) for item in prov
                if getattr(item, 'page_no', None) is not None
            })

            page_no = None
            page_range = None
            if len(page_numbers) == 1:
                page_no = page_numbers[0]
            elif len(page_numbers) > 1:
                page_range = [page_numbers[0], page_numbers[-1]]

            cells = [
                {
                    'row': cell.start_row_offset_idx,
                    'col': cell.start_col_offset_idx,
                    'row_span': cell.row_span,
                    'col_span': cell.col_span,
                    'text': cell.text,
                }
                for cell in getattr(data, 'table_cells', []) or []
            ]

            tables.append({
                'table_index': table_index,
                'page_number': page_no,
                'page_range': page_range,
                'num_rows': getattr(data, 'num_rows', None),
                'num_cols': getattr(data, 'num_cols', None),
                'cells': cells,
            })

        return tables

    async def extract_metadata(self, file_data: bytes, filename: str | None = None) -> dict[str, Any]:
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
        
        except Exception as e:  # noqa: BLE001 - best-effort metadata extraction, must not fail the primary parse
            logger.warning(f"Error extracting Docling metadata: {e}")
        
        return metadata
    
    def get_converter_config(self) -> dict[str, Any]:
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
