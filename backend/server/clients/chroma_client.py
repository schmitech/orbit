"""
Chroma client for document retrieval
"""

import logging
from typing import Dict, Any, List, Optional
from chromadb import HttpClient
from langchain_ollama import OllamaEmbeddings
from services.summarization_service import SummarizationService

# Configure logging
logger = logging.getLogger(__name__)


class ChromaRetriever:
    """Handles document retrieval from ChromaDB"""

    def __init__(self, collection, embeddings: OllamaEmbeddings, config: Dict[str, Any]):
        self.collection = collection
        self.embeddings = embeddings
        self.config = config
        self.confidence_threshold = config['chroma'].get('confidence_threshold', 0.7)
        self.relevance_threshold = config['chroma'].get('relevance_threshold', 0.5)
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Initialize summarization service if enabled
        self.summarization_enabled = config['ollama'].get('enable_summarization', False)
        if self.summarization_enabled:
            self.summarization_service = SummarizationService(config)
        else:
            self.summarization_service = None

    async def initialize(self):
        """Initialize the summarization service if enabled"""
        if self.summarization_service:
            await self.summarization_service.initialize()

    async def close(self):
        """Close the summarization service if enabled"""
        if self.summarization_service:
            await self.summarization_service.close()

    def get_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Check if there's a direct answer with high confidence
        
        Args:
            context: List of context items from Chroma
            
        Returns:
            Optional[str]: Direct answer if found, None otherwise
        """
        if not context:
            return None
            
        # Get the first (most relevant) result
        first_result = context[0]
        
        # Check if it's a Q&A pair with high confidence
        if "question" in first_result and "answer" in first_result:
            if first_result.get("confidence", 0) >= self.confidence_threshold:
                if self.verbose:
                    logger.info(f"Found direct answer with confidence {first_result.get('confidence')}")
                return first_result["answer"]
        
        return None

    async def get_relevant_context(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from ChromaDB
        
        Args:
            query: The user's query
            
        Returns:
            List[Dict[str, Any]]: List of relevant context items
        """
        try:
            # Generate embedding for the query
            query_embedding = self.embeddings.embed_query(query)
            
            # Query ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=3,  # Get top 3 most relevant results
                include=["documents", "metadatas", "distances"]
            )
            
            context_items = []
            
            # Process each result
            for doc, metadata, distance in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                similarity = 1 - distance
                
                # Only include results above relevance threshold
                if similarity >= self.relevance_threshold:
                    item = {
                        "content": doc,
                        "confidence": similarity,
                        **metadata
                    }
                    
                    # If this is a direct answer and summarization is enabled, summarize it
                    if (self.summarization_enabled and 
                        "question" in metadata and 
                        "answer" in metadata and 
                        len(metadata["answer"]) > 200):  # Only summarize long answers
                        
                        if self.verbose:
                            logger.info(f"Summarizing long answer (length: {len(metadata['answer'])})")
                        
                        summary = await self.summarization_service.summarize(metadata["answer"])
                        if summary:
                            item["answer"] = summary
                            if self.verbose:
                                logger.info(f"Summarized answer (new length: {len(summary)})")
                    
                    context_items.append(item)
            
            if self.verbose:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
            
            return context_items
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return [] 