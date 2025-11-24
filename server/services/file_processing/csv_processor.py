"""
CSV Processor

Handles CSV files using pandas.
"""

import logging
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    from io import BytesIO, StringIO
    import csv
    CSV_AVAILABLE = True
except ImportError:
    CSV_AVAILABLE = False
    logger.warning("pandas not available. CSV processing disabled.")


class CSVProcessor(FileProcessor):
    """
    Processor for CSV files.
    
    Supports: text/csv
    Requires: pandas
    """
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        return CSV_AVAILABLE and mime_type.lower() == 'text/csv'
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from CSV file."""
        if not CSV_AVAILABLE:
            raise ImportError("pandas not available")
        
        try:
            # Try to decode as UTF-8
            csv_text = file_data.decode('utf-8')
        except UnicodeDecodeError:
            csv_text = file_data.decode('latin-1')
        
        # Parse CSV and create a readable text representation
        df = pd.read_csv(StringIO(csv_text))
        
        # Convert to markdown-like format
        text_parts = [
            f"CSV file with {len(df)} rows and {len(df.columns)} columns",
            "",
            "Columns: " + ", ".join(df.columns.tolist()),
            "",
            df.head(10).to_string(index=False),
        ]
        
        return "\n".join(text_parts)
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from CSV."""
        metadata = await super().extract_metadata(file_data, filename)
        
        if not CSV_AVAILABLE:
            return metadata
        
        try:
            csv_text = file_data.decode('utf-8')
            df = pd.read_csv(StringIO(csv_text))
            
            metadata.update({
                'row_count': len(df),
                'column_count': len(df.columns),
                'columns': df.columns.tolist(),
                'mime_type': 'text/csv',
            })
        
        except Exception as e:
            logger.warning(f"Error extracting CSV metadata: {e}")
        
        return metadata
