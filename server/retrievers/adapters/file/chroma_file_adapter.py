"""
File adapter for uploaded document content in ChromaDB
"""

import logging
from typing import Dict, Any, List, Optional

from ..domain_adapters import DocumentAdapter

logger = logging.getLogger(__name__)

class ChromaFileAdapter(DocumentAdapter):
    """Adapter for uploaded file content in ChromaDB, optimized for CSV and structured data"""
    
    def __init__(self, config: Dict[str, Any] = None, verbose: bool = False, **kwargs):
        """
        Initialize the file adapter.
        
        Args:
            config: Optional configuration dictionary
            verbose: Enable verbose logging (can be overridden by config)
            **kwargs: Additional configuration options
        """
        super().__init__(config=config, **kwargs)
        
        # Extract configuration values with sensible defaults, following other adapter patterns
        self.confidence_threshold = self.config.get('confidence_threshold', 0.3)
        self.verbose = self.config.get('verbose', verbose)  # Config takes precedence over parameter
        
        # File-specific configuration
        self.include_file_metadata = self.config.get('include_file_metadata', True)
        self.boost_file_uploads = self.config.get('boost_file_uploads', True)
        self.file_content_weight = self.config.get('file_content_weight', 1.5)
        self.metadata_weight = self.config.get('metadata_weight', 0.8)
        
        if self.verbose:
            logger.info(f"ChromaFileAdapter initialized with confidence threshold: {self.confidence_threshold}")
            logger.info(f"File-specific settings - metadata: {self.include_file_metadata}, boost: {self.boost_file_uploads}")
        else:
            logger.info("ChromaFileAdapter initialized")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from uploaded file content.
        
        Args:
            raw_doc: The document text (file content)
            metadata: The document metadata
            
        Returns:
            A formatted context item optimized for file content
        """
        if self.verbose:
            logger.info(f"ChromaFileAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
        # Create the base item
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy(),
            "content": raw_doc
        }
        
        # Get file information from metadata
        filename = metadata.get('filename', 'Unknown file')
        file_type = metadata.get('mime_type', 'Unknown type')
        source_type = metadata.get('source_type', 'unknown')
        file_size = metadata.get('file_size', 0)
        upload_time = metadata.get('upload_timestamp', 'Unknown time')
        
        # Special handling for different file types
        if source_type == 'file_upload':
            # CSV/Structured data handling
            if 'csv' in file_type.lower() or filename.endswith('.csv'):
                item["content_type"] = "csv_data"
                item["display_name"] = f"CSV data from {filename}"
                
                # Parse CSV content for better presentation
                if '|' in raw_doc:  # Our CSV format uses | separators
                    lines = raw_doc.strip().split('\n')
                    if len(lines) > 1:
                        headers = lines[0].split(' | ')
                        data_rows = lines[1:]
                        
                        # Create structured representation
                        item["structured_data"] = {
                            "headers": headers,
                            "row_count": len(data_rows),
                            "preview": data_rows[:3] if data_rows else []  # First 3 rows
                        }
                        
                        # Enhanced content with context
                        item["content"] = f"File: {filename}\nType: CSV data with {len(headers)} columns and {len(data_rows)} rows\n\nContent:\n{raw_doc}"
                        
                        if self.verbose:
                            logger.info(f"ChromaFileAdapter: Processed CSV with {len(headers)} headers, {len(data_rows)} rows")
            
            # Excel/Spreadsheet handling
            elif any(ext in file_type.lower() for ext in ['excel', 'spreadsheet']) or filename.endswith(('.xlsx', '.xls')):
                item["content_type"] = "spreadsheet_data"
                item["display_name"] = f"Spreadsheet data from {filename}"
                item["content"] = f"File: {filename}\nType: Spreadsheet data\n\nContent:\n{raw_doc}"
            
            # PDF handling
            elif 'pdf' in file_type.lower() or filename.endswith('.pdf'):
                item["content_type"] = "pdf_document"
                item["display_name"] = f"PDF document: {filename}"
                item["content"] = f"File: {filename}\nType: PDF document\n\nContent:\n{raw_doc}"
            
            # Word document handling
            elif any(ext in file_type.lower() for ext in ['word', 'document']) or filename.endswith(('.docx', '.doc')):
                item["content_type"] = "word_document"
                item["display_name"] = f"Word document: {filename}"
                item["content"] = f"File: {filename}\nType: Word document\n\nContent:\n{raw_doc}"
            
            # Text file handling
            elif 'text' in file_type.lower() or filename.endswith(('.txt', '.md')):
                item["content_type"] = "text_document"
                item["display_name"] = f"Text file: {filename}"
                item["content"] = f"File: {filename}\nType: Text document\n\nContent:\n{raw_doc}"
            
            # Generic file handling
            else:
                item["content_type"] = "uploaded_file"
                item["display_name"] = f"Uploaded file: {filename}"
                item["content"] = f"File: {filename}\nType: {file_type}\n\nContent:\n{raw_doc}"
            
            # Add file metadata
            item["file_metadata"] = {
                "filename": filename,
                "mime_type": file_type,
                "file_size": file_size,
                "upload_timestamp": upload_time,
                "source_type": source_type
            }
            
            if self.verbose:
                logger.info(f"ChromaFileAdapter: Formatted {item['content_type']} - {filename}")
        else:
            # Non-file content, use basic formatting
            item["content"] = raw_doc
            if self.verbose:
                logger.info(f"ChromaFileAdapter: Formatted non-file content")
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from file content context items.
        
        For file content, we provide structured information about the uploaded files
        and their content when there's high confidence in the match.
        
        Args:
            context: List of context items from file uploads
            
        Returns:
            A direct answer if found, otherwise None
        """
        if not context:
            return None
            
        # Check if we have high-confidence file content matches
        high_confidence_items = [
            item for item in context 
            if item.get('confidence', 0) >= 0.8 and 
               item.get('metadata', {}).get('source_type') == 'file_upload'
        ]
        
        if not high_confidence_items:
            return None
            
        # For CSV/structured data with high confidence, provide a structured summary
        first_item = high_confidence_items[0]
        metadata = first_item.get('metadata', {})
        filename = metadata.get('filename', 'uploaded file')
        
        if first_item.get('content_type') == 'csv_data':
            structured_data = first_item.get('structured_data', {})
            if structured_data:
                headers = structured_data.get('headers', [])
                row_count = structured_data.get('row_count', 0)
                
                direct_answer = f"From {filename}: This CSV file contains {row_count} records with the following columns: {', '.join(headers)}"
                
                # Add a sample of the data if available
                preview = structured_data.get('preview', [])
                if preview:
                    direct_answer += f"\n\nSample data:\n{preview[0]}"
                    if len(preview) > 1:
                        direct_answer += f"\n{preview[1]}"
                
                return direct_answer
        
        # For other file types with specific content matches
        elif metadata.get('source_type') == 'file_upload':
            content = first_item.get('content', '')
            if len(content) > 200:
                content = content[:200] + "..."
                
            return f"From uploaded file '{filename}': {content}"
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply file-specific filtering/ranking.
        
        Args:
            context_items: List of context items to filter
            query: The user's query
            
        Returns:
            Filtered and reranked context items
        """
        if self.verbose:
            logger.info(f"ChromaFileAdapter.apply_domain_specific_filtering called with {len(context_items)} items and query: {query[:50]}...")
        
        if not context_items:
            return []
        
        # File-specific ranking logic
        enhanced_items = []
        query_lower = query.lower()
        query_terms = query_lower.split()
        
        for item in context_items:
            enhanced_item = item.copy()
            metadata = item.get('metadata', {})
            content = item.get('content', '').lower()
            
            # File-specific scoring
            if metadata.get('source_type') == 'file_upload':
                base_confidence = enhanced_item.get('confidence', 0.5)
                boost_factor = 1.0
                match_reasons = []
                
                # Boost for CSV data with exact term matches
                if item.get('content_type') == 'csv_data':
                    # Check for exact matches in structured data
                    exact_matches = sum(1 for term in query_terms if term in content)
                    if exact_matches > 0:
                        boost_factor *= (1.0 + exact_matches * 0.2)
                        match_reasons.append(f"{exact_matches} exact term matches in CSV")
                
                # Boost for filename relevance
                filename = metadata.get('filename', '').lower()
                filename_matches = sum(1 for term in query_terms if term in filename)
                if filename_matches > 0:
                    boost_factor *= (1.0 + filename_matches * 0.15)
                    match_reasons.append(f"filename matches")
                
                # Boost for recent uploads (simple recency bonus)
                if 'upload_timestamp' in metadata:
                    boost_factor *= 1.1  # Small boost for uploaded files
                    match_reasons.append("recent upload")
                
                # Apply boost
                enhanced_item['confidence'] = min(base_confidence * boost_factor, 0.95)
                enhanced_item['match_reasons'] = match_reasons
                enhanced_item['boost_factor'] = boost_factor
                
                if self.verbose and boost_factor > 1.0:
                    logger.info(f"ChromaFileAdapter: Boosted item by {boost_factor:.2f}x - {', '.join(match_reasons)}")
            
            enhanced_items.append(enhanced_item)
        
        # Sort by enhanced confidence (no confidence filtering here as parent handles it)
        enhanced_items.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        if self.verbose:
            logger.info(f"ChromaFileAdapter: Enhanced and ranked {len(enhanced_items)} items")
            for i, item in enumerate(enhanced_items[:3]):  # Show top 3
                confidence = item.get('confidence', 0)
                reasons = item.get('match_reasons', [])
                logger.info(f"  Rank {i+1}: confidence={confidence:.3f}, reasons={reasons}")
            
        return enhanced_items
    
    # Compatibility method
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match expected interface.
        """
        return self.apply_domain_specific_filtering(context_items, query)

# Auto-register the adapter when module is imported
def _register_adapter():
    """Register this adapter with the global registry."""
    try:
        from ..registry import ADAPTER_REGISTRY
        ADAPTER_REGISTRY.register(
            adapter_type='retriever',
            datasource='chroma', 
            adapter_name='file',
            factory_func=lambda config, **kwargs: ChromaFileAdapter(config=config, verbose=config.get('verbose', False), **kwargs),
            config={}
        )
        logger.info("ChromaFileAdapter registered with adapter registry")
    except Exception as e:
        logger.warning(f"Could not register ChromaFileAdapter: {e}")

# Call registration on import
_register_adapter() 