"""
Simple summarization adapter for document retrieval
"""

from typing import Dict, Any, List, Optional
import logging
from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

logger = logging.getLogger(__name__)

class SummarizationAdapter(DocumentAdapter):
    """Adapter for document summarization tasks"""
    
    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize summarization adapter.
        
        Args:
            config: Optional configuration dictionary
            **kwargs: Additional parameters
        """
        super().__init__(config=config, **kwargs)
        
        # Extract configuration values
        self.max_summary_length = self.config.get('max_summary_length', 200)
        self.confidence_threshold = self.config.get('confidence_threshold', 0.5)
        self.verbose = self.config.get('verbose', False)
        
        if self.verbose:
            logger.info(f"Initialized Summarization Adapter with max_summary_length: {self.max_summary_length}")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format document for summarization"""
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
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Extract summary from the top result"""
        if not context:
            return None
            
        first_result = context[0]
        
        # If we have a pre-made summary with good confidence, return it
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
        """Apply summarization-specific filtering"""
        if not context_items:
            return []
            
        # Filter by confidence threshold
        filtered_items = [item for item in context_items 
                         if item.get("confidence", 0) >= self.confidence_threshold]
        
        # Boost items that have existing summaries
        for item in filtered_items:
            if "summary" in item:
                item["confidence"] = min(1.0, item["confidence"] * 1.1)
        
        # Sort by confidence
        filtered_items.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return filtered_items


# Factory function to create the adapter
def create_summarization_adapter(config: Dict[str, Any] = None, **kwargs) -> SummarizationAdapter:
    """Factory function to create a summarization adapter"""
    return SummarizationAdapter(config=config, **kwargs)


# Register the adapter with the factory
DocumentAdapterFactory.register_adapter("summarization", create_summarization_adapter)
logger.info("Registered SummarizationAdapter as 'summarization'") 