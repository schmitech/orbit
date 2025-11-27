"""
PDF Processor

Handles PDF files using pypdf (formerly PyPDF2).
"""

import logging
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader
    from io import BytesIO
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("pypdf not available. PDF processing disabled.")


class PDFProcessor(FileProcessor):
    """
    Processor for PDF files.
    
    Supports: application/pdf
    Requires: pypdf (formerly PyPDF2)
    """
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        return PDF_AVAILABLE and mime_type.lower() == 'application/pdf'
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from PDF."""
        if not PDF_AVAILABLE:
            raise ImportError("pypdf not available")

        logger.debug(f"PDFProcessor.extract_text() called for file: {filename or 'unknown'} (using pypdf)")

        text_parts = []

        try:
            pdf_file = BytesIO(file_data)
            pdf_reader = PdfReader(pdf_file)
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"Page {page_num + 1}\n\n{page_text}")
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
            
            return "\n\n".join(text_parts)
        
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from PDF."""
        metadata = await super().extract_metadata(file_data, filename)
        
        if not PDF_AVAILABLE:
            return metadata
        
        try:
            pdf_file = BytesIO(file_data)
            pdf_reader = PdfReader(pdf_file)
            
            metadata.update({
                'page_count': len(pdf_reader.pages),
                'mime_type': 'application/pdf',
            })
            
            # Extract PDF metadata if available
            if pdf_reader.metadata:
                for key, value in pdf_reader.metadata.items():
                    metadata[key.lower()] = value
        
        except Exception as e:
            logger.warning(f"Error extracting PDF metadata: {e}")
        
        return metadata
