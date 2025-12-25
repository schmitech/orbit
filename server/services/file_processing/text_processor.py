"""
Text Processor

Handles plain text files (TXT, MD, etc.).
"""

import logging
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)


class TextProcessor(FileProcessor):
    """
    Processor for plain text files and code files.
    
    Supports: text/plain, text/markdown, text/csv, and various code file types
    (Python, Java, SQL, JavaScript, TypeScript, C/C++, Go, Rust, Ruby, PHP, 
    shell scripts, YAML, XML, CSS, SCSS, SASS, LESS, etc.)
    """
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        text_types = [
            'text/plain',
            'text/markdown',
            'text/csv',  # Fallback if CSVProcessor not available
            # Code file MIME types
            'text/x-python',
            'text/x-python-script',  # Alternative MIME type for Python files
            'text/x-java-source',
            'text/x-java',
            'text/x-sql',
            'application/x-sql',
            'application/sql',
            'text/javascript',
            'application/javascript',
            'text/typescript',
            'application/typescript',
            'text/x-c++src',
            'text/x-csrc',
            'text/x-c',
            'text/x-go',
            'text/x-rust',
            'text/x-ruby',
            'text/x-php',
            'text/x-shellscript',
            'text/x-sh',
            'text/yaml',
            'text/x-yaml',
            'text/xml',
            'application/xml',
            'text/css',
            'text/x-scss',
            'text/x-sass',
            'text/x-less',
        ]
        return mime_type.lower() in text_types
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from file."""
        logger.debug(f"TextProcessor.extract_text() called for file: {filename or 'unknown'} (using standard library)")

        try:
            # Try UTF-8 first
            text = file_data.decode('utf-8')
        except UnicodeDecodeError:
            # Fall back to latin-1 for compatibility
            text = file_data.decode('latin-1')
        
        return text
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from text file."""
        metadata = await super().extract_metadata(file_data, filename)
        
        text = await self.extract_text(file_data, filename)
        
        metadata.update({
            'line_count': len(text.splitlines()),
            'character_count': len(text),
            'mime_type': 'text/plain',
        })
        
        return metadata
