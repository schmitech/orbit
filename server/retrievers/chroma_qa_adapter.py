"""
ChromaDB-specific QA adapter that matches the original implementation
"""

from typing import Dict, Any, List, Optional
from domain_adapters import DocumentAdapter, DocumentAdapterFactory

class ChromaQAAdapter(DocumentAdapter):
    """Adapter for question-answer pairs in ChromaDB, matching original implementation"""
    
    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
    
    def format_document(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        Matches the original QAChromaRetriever._format_metadata implementation.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        # Create the base item with confidence
        item = {
            "raw_document": doc,
            "metadata": metadata.copy(),  # Include full metadata
        }
        
        # Set the content field based on document type
        if "question" in metadata and "answer" in metadata:
            # If it's a QA pair, set content to the question and answer together
            item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
            item["question"] = metadata["question"]
            item["answer"] = metadata["answer"]
        else:
            # Otherwise, use the document content
            item["content"] = doc
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        Matches the original BaseRetriever.get_direct_answer implementation.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        if not context:
            return None
            
        first_result = context[0]
        
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            
            # Return a formatted answer that includes both question and answer for clarity
            return f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """Apply QA-specific filtering/ranking"""
        # Original implementation didn't do domain-specific filtering, just sorted by confidence
        return context_items


# Register the ChromaDB-specific QA adapter
DocumentAdapterFactory.register_adapter("chroma_qa", ChromaQAAdapter)