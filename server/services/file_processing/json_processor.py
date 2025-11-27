"""
JSON Processor

Handles JSON files.
"""

import logging
import json
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)


class JSONProcessor(FileProcessor):
    """
    Processor for JSON files.
    
    Supports: application/json
    """
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        return mime_type.lower() == 'application/json'
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text representation from JSON."""
        logger.debug(f"JSONProcessor.extract_text() called for file: {filename or 'unknown'} (using standard library)")

        try:
            data = json.loads(file_data.decode('utf-8'))
            
            if isinstance(data, dict):
                lines = ["JSON Object:"]
                for key, value in data.items():
                    lines.append(f"  {key}: {value}")
                return "\n".join(lines)
            
            elif isinstance(data, list):
                return f"JSON Array with {len(data)} items:\n{json.dumps(data, indent=2)}"
            
            else:
                return json.dumps(data, indent=2)
        
        except Exception as e:
            logger.error(f"Error processing JSON: {e}")
            raise
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from JSON."""
        metadata = await super().extract_metadata(file_data, filename)
        
        try:
            data = json.loads(file_data.decode('utf-8'))
            
            if isinstance(data, dict):
                metadata.update({
                    'object_type': 'dict',
                    'keys': ', '.join(str(k) for k in data.keys()),  # Convert to comma-separated string
                    'key_count': len(data),
                })
            elif isinstance(data, list):
                metadata.update({
                    'object_type': 'array',
                    'item_count': len(data),
                })
            
            metadata['mime_type'] = 'application/json'
        
        except Exception as e:
            logger.warning(f"Error extracting JSON metadata: {e}")
        
        return metadata
