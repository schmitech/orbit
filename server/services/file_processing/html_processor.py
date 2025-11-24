"""
HTML Processor

Handles HTML files using BeautifulSoup.
"""

import logging
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    HTML_AVAILABLE = True
except ImportError:
    HTML_AVAILABLE = False
    logger.warning("beautifulsoup4 not available. HTML processing disabled.")


class HTMLProcessor(FileProcessor):
    """
    Processor for HTML files.
    
    Supports: text/html
    Requires: beautifulsoup4
    """
    
    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        return HTML_AVAILABLE and mime_type.lower() == 'text/html'
    
    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from HTML."""
        if not HTML_AVAILABLE:
            raise ImportError("beautifulsoup4 not available")
        
        try:
            html_text = file_data.decode('utf-8')
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Extract title
            title = soup.find('title')
            text_parts = []
            if title:
                text_parts.append(f"Title: {title.get_text()}")
                text_parts.append("")
            
            # Extract main content
            main_content = soup.get_text(separator=' ', strip=True)
            text_parts.append(main_content)
            
            return "\n".join(text_parts)
        
        except Exception as e:
            logger.error(f"Error processing HTML: {e}")
            raise
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from HTML."""
        metadata = await super().extract_metadata(file_data, filename)
        
        if not HTML_AVAILABLE:
            return metadata
        
        try:
            html_text = file_data.decode('utf-8')
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Extract meta tags
            meta_tags = {}
            for meta in soup.find_all('meta'):
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                if name and content:
                    meta_tags[name] = content
            
            # Count elements
            link_count = len(soup.find_all('a'))
            img_count = len(soup.find_all('img'))
            
            metadata.update({
                'meta_tags': meta_tags,
                'link_count': link_count,
                'image_count': img_count,
                'mime_type': 'text/html',
            })
        
        except Exception as e:
            logger.warning(f"Error extracting HTML metadata: {e}")
        
        return metadata
