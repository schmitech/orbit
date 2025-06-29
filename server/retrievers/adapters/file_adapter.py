"""
File adapter for processing uploaded files with domain-specific formatting
"""

from typing import Dict, Any, List, Optional
import logging
from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

logger = logging.getLogger(__name__)

class FileAdapter(DocumentAdapter):
    """Adapter for uploaded files with intelligent content processing"""
    
    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize file adapter.
        
        Args:
            config: Optional configuration dictionary
            **kwargs: Additional parameters
        """
        super().__init__(config=config, **kwargs)
        
        # Extract configuration values
        self.confidence_threshold = self.config.get('confidence_threshold', 0.5)
        self.preserve_file_structure = self.config.get('preserve_file_structure', True)
        self.extract_metadata = self.config.get('extract_metadata', True)
        self.verbose = self.config.get('verbose', False)
        self.max_summary_length = self.config.get('max_summary_length', 200)
        
        if self.verbose:
            logger.info(f"Initialized File Adapter with confidence_threshold: {self.confidence_threshold}")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format uploaded file documents with enhanced metadata"""
        # Start with basic formatting
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy() if metadata else {},
        }
        
        # Add title if available
        if metadata and "title" in metadata:
            item["title"] = metadata["title"]
            item["content"] = f"Title: {metadata['title']}\n\nContent: {raw_doc}"
        else:
            item["content"] = raw_doc
            
        # Add summary if available in metadata
        if metadata and "summary" in metadata:
            item["summary"] = metadata["summary"]
        
        # Add file-specific enhancements
        if metadata:
            # File-specific metadata
            if 'file_id' in metadata:
                item['file_id'] = metadata['file_id']
            if 'filename' in metadata:
                item['filename'] = metadata['filename']
            if 'mime_type' in metadata:
                item['mime_type'] = metadata['mime_type']
            if 'file_size' in metadata:
                item['file_size'] = metadata['file_size']
            if 'upload_timestamp' in metadata:
                item['upload_timestamp'] = metadata['upload_timestamp']
            if 'extraction_method' in metadata:
                item['extraction_method'] = metadata['extraction_method']
            
            # File type specific formatting
            if 'mime_type' in metadata:
                item['content_type'] = self._classify_content_type(metadata['mime_type'])
                
                # Apply content-type specific formatting
                if item['content_type'] == 'document':
                    item = self._format_document_content(item, raw_doc, metadata)
                elif item['content_type'] == 'spreadsheet':
                    item = self._format_spreadsheet_content(item, raw_doc, metadata)
                elif item['content_type'] == 'data':
                    item = self._format_data_content(item, raw_doc, metadata)
        
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Extract direct answer with file-aware processing"""
        if not context:
            return None
            
        first_result = context[0]
        
        # Check confidence threshold
        if first_result.get("confidence", 0) < self.confidence_threshold:
            return None
        
        # File-specific answer extraction
        if 'file_id' in first_result and 'filename' in first_result:
            filename = first_result['filename']
            content_type = first_result.get('content_type', 'unknown')
            
            # For documents, try to extract key information
            if content_type == 'document':
                return self._extract_document_answer(first_result, filename)
            
            # For data files, provide structured information
            elif content_type in ['data', 'spreadsheet']:
                return self._extract_data_answer(first_result, filename)
        
        # Fallback to basic summarization logic
        if ("summary" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            return first_result["summary"]
        
        # Otherwise, create a truncated version as a quick summary
        content = first_result.get("content", "")
        if len(content) > self.max_summary_length:
            return content[:self.max_summary_length] + "..."
            
        return content
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """Apply file-aware filtering"""
        if not context_items:
            return []
        
        # Apply basic filtering
        filtered_items = [item for item in context_items 
                         if item.get("confidence", 0) >= self.confidence_threshold]
        
        # File-specific boosts
        for item in filtered_items:
            confidence_boost = 0
            
            # Boost based on file type relevance
            content_type = item.get('content_type', 'unknown')
            if self._is_relevant_content_type(content_type, query):
                confidence_boost += 0.05
            
            # Boost if filename matches query terms
            filename = item.get('filename', '')
            if any(term.lower() in filename.lower() for term in query.split() if len(term) > 2):
                confidence_boost += 0.1
            
            # Boost recent uploads
            if 'upload_timestamp' in item:
                confidence_boost += 0.02  # Small boost for recent files
            
            # Apply boost
            if confidence_boost > 0:
                item["confidence"] = min(1.0, item["confidence"] + confidence_boost)
        
        # Sort by confidence
        filtered_items.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return filtered_items
    
    def _classify_content_type(self, mime_type: str) -> str:
        """Classify file content type based on MIME type"""
        if mime_type.startswith('text/'):
            return 'text'
        elif mime_type == 'application/pdf':
            return 'document'
        elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                          'application/msword']:
            return 'document'
        elif mime_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                          'application/vnd.ms-excel', 'text/csv']:
            return 'spreadsheet'
        elif mime_type == 'application/json':
            return 'data'
        else:
            return 'unknown'
    
    def _format_document_content(self, item: Dict[str, Any], raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format document-type content"""
        # Extract page information if available
        if 'Page ' in raw_doc:
            pages = raw_doc.split('\n\nPage ')
            item['page_count'] = len(pages)
            
            # Create a more structured content representation
            if len(pages) > 1:
                item['content'] = f"Document: {metadata.get('filename', 'Unknown')}\n"
                item['content'] += f"Pages: {len(pages)}\n\n"
                item['content'] += pages[0][:500] + "..." if len(pages[0]) > 500 else pages[0]
        
        return item
    
    def _format_spreadsheet_content(self, item: Dict[str, Any], raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format spreadsheet-type content"""
        lines = raw_doc.split('\n')
        
        # Count rows and estimate columns
        data_lines = [line for line in lines if '|' in line and not line.startswith('Sheet:')]
        if data_lines:
            item['row_count'] = len(data_lines)
            item['column_count'] = data_lines[0].count('|') + 1 if data_lines else 0
            
            # Create a summary
            item['content'] = f"Spreadsheet: {metadata.get('filename', 'Unknown')}\n"
            item['content'] += f"Rows: {len(data_lines)}, Columns: {item['column_count']}\n\n"
            
            # Include first few rows as preview
            preview_rows = data_lines[:5]
            item['content'] += '\n'.join(preview_rows)
            if len(data_lines) > 5:
                item['content'] += f"\n... ({len(data_lines) - 5} more rows)"
        
        return item
    
    def _format_data_content(self, item: Dict[str, Any], raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format data file content (JSON, CSV, etc.)"""
        # For JSON files, try to extract structure info
        if metadata.get('mime_type') == 'application/json':
            try:
                import json
                data = json.loads(raw_doc)
                if isinstance(data, dict):
                    item['json_keys'] = list(data.keys())
                elif isinstance(data, list):
                    item['json_array_length'] = len(data)
            except:
                pass
        
        return item
    
    def _extract_document_answer(self, result: Dict[str, Any], filename: str) -> str:
        """Extract answer for document files"""
        answer = f"From document '{filename}':\n\n"
        
        if 'page_count' in result:
            answer += f"Document has {result['page_count']} pages.\n\n"
        
        # Get content preview
        content = result.get('content', '')
        if len(content) > 300:
            answer += content[:300] + "..."
        else:
            answer += content
            
        return answer
    
    def _extract_data_answer(self, result: Dict[str, Any], filename: str) -> str:
        """Extract answer for data files"""
        answer = f"From data file '{filename}':\n\n"
        
        if 'row_count' in result and 'column_count' in result:
            answer += f"Spreadsheet contains {result['row_count']} rows and {result['column_count']} columns.\n\n"
        elif 'json_keys' in result:
            answer += f"JSON object with keys: {', '.join(result['json_keys'])}\n\n"
        elif 'json_array_length' in result:
            answer += f"JSON array with {result['json_array_length']} items.\n\n"
        
        # Get content preview
        content = result.get('content', '')
        if len(content) > 200:
            answer += content[:200] + "..."
        else:
            answer += content
            
        return answer
    
    def _is_relevant_content_type(self, content_type: str, query: str) -> bool:
        """Check if content type is relevant to the query"""
        query_lower = query.lower()
        
        # Simple relevance matching
        if content_type == 'document' and any(word in query_lower for word in ['document', 'pdf', 'text', 'content']):
            return True
        elif content_type == 'spreadsheet' and any(word in query_lower for word in ['data', 'table', 'spreadsheet', 'excel', 'csv']):
            return True
        elif content_type == 'data' and any(word in query_lower for word in ['data', 'json', 'structure']):
            return True
        
        return False


# Factory function to create the adapter
def create_file_adapter(config: Dict[str, Any] = None, **kwargs) -> FileAdapter:
    """Factory function to create a file adapter"""
    return FileAdapter(config=config, **kwargs)


# Register the adapter with the factory
DocumentAdapterFactory.register_adapter("file", create_file_adapter)
logger.info("Registered FileAdapter as 'file'") 