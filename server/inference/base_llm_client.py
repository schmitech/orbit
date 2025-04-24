"""
Inference Adapter Pattern Implementation

This file contains the base classes and implementations for an inference adapter pattern,
which allows different LLM providers to be used while maintaining a consistent API.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
import logging
import asyncio
import json

class BaseLLMClient(ABC):
    """Base LLM client interface that all provider-specific clients should implement."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        """
        Initialize the LLM client with configuration.
        
        Args:
            config: Application configuration dictionary
            retriever: The retriever to use for document lookup
            guardrail_service: Optional service for content safety checks
            reranker_service: Optional service for reranking results
            prompt_service: Optional service for system prompts
            no_results_message: Message to show when no results are found
        """
        self.config = config
        self.retriever = retriever
        self.guardrail_service = guardrail_service
        self.reranker_service = reranker_service
        self.prompt_service = prompt_service
        self.no_results_message = no_results_message
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the LLM client."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass
    
    @abstractmethod
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to the LLM provider is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        pass
    
    @abstractmethod
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            Dictionary containing response and metadata
        """
        pass
    
    @abstractmethod
    async def generate_response_stream(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Yields:
            Chunks of the response as they are generated
        """
        pass
    
    def _format_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        Format retrieved documents into a context string.
        
        Args:
            documents: List of retrieved documents
            
        Returns:
            Formatted context string
        """
        if not documents:
            return self.no_results_message or "No relevant information found."
        
        context = ""
        for i, doc in enumerate(documents):
            content = doc.get('content', '')
            metadata = doc.get('metadata', {})
            source = metadata.get('source', f"Document {i+1}")
            
            # Try different field names based on what's available
            confidence = doc.get('confidence', doc.get('relevance', 0.0))
            
            # Add document to context with confidence score if available
            context += f"[{i+1}] {source} (confidence: {confidence:.2f})\n{content}\n\n"
        
        return context
    
    def _format_sources(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format retrieved documents into source citations.
        
        Args:
            documents: List of retrieved documents
            
        Returns:
            List of source dictionaries
        """
        sources = []
        for i, doc in enumerate(documents):
            metadata = doc.get('metadata', {})
            source = metadata.get('source', f"Document {i+1}")
            
            # Get additional metadata
            title = metadata.get('title', source)
            url = metadata.get('url', '')
            date = metadata.get('date', '')
            
            # Try different field names based on what's available
            confidence = doc.get('confidence', doc.get('relevance', 0.0))
            
            sources.append({
                "id": i + 1,
                "title": title,
                "source": source,
                "url": url,
                "date": date,
                "confidence": confidence  # Use confidence as the key regardless of source field name
            })
        
        return sources

# Factory will be moved to a separate file