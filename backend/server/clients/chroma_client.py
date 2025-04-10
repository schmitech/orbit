"""
Chroma client for document retrieval
"""

import logging
from typing import Dict, Any, List, Optional
from chromadb import HttpClient
from langchain_ollama import OllamaEmbeddings
from services.api_key_service import ApiKeyService
from fastapi import HTTPException

# Configure logging
logger = logging.getLogger(__name__)

class ChromaRetriever:
    """Handles document retrieval from ChromaDB"""

    def __init__(self, collection: Any, embeddings: OllamaEmbeddings, config: Dict[str, Any]):
        self.collection = collection
        self.embeddings = embeddings
        self.config = config
        
        # Extract chroma-specific configuration for clarity
        chroma_config = config.get('chroma', {})
        self.confidence_threshold = chroma_config.get('confidence_threshold', 0.7)
        self.relevance_threshold = chroma_config.get('relevance_threshold', 0.5)
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Initialize dependent services
        self.api_key_service = ApiKeyService(config)
        self.chroma_client = HttpClient(
            host=chroma_config.get('host'),
            port=int(chroma_config.get('port'))
        )

    async def initialize(self):
        """Initialize required services."""
        await self.api_key_service.initialize()

    async def close(self):
        """Close any open services."""
        await self.api_key_service.close()

    async def _resolve_collection(self, api_key: Optional[str] = None, collection_name: Optional[str] = None) -> None:
        """
        Determine and set the appropriate collection.
        
        Priority:
          1. If an API key is provided, validate it and use its collection.
          2. If a collection name is provided directly, use it.
          3. If none is provided and the current collection is None, try the default from config.
        
        Raises:
            HTTPException: If no valid collection can be determined.
        """
        if api_key:
            is_valid, resolved_collection_name = await self.api_key_service.validate_api_key(api_key)
            if not is_valid:
                raise ValueError("Invalid API key")
            if resolved_collection_name:
                await self.set_collection(resolved_collection_name)
                return
        elif collection_name:
            await self.set_collection(collection_name)
            return

        # Fallback to the default collection if none is set
        if not self.collection:
            default_collection = self.config.get('chroma', {}).get('collection')
            if default_collection:
                await self.set_collection(default_collection)
            else:
                error_msg = ("No collection available. Ensure a default collection is configured "
                             "or a valid API key is provided.")
                logger.error(error_msg)
                raise HTTPException(status_code=500, detail=error_msg)

    async def set_collection(self, collection_name: str) -> None:
        """Set the current collection for retrieval."""
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
        try:
            self.collection = self.chroma_client.get_collection(name=collection_name)
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
        except Exception as e:
            error_msg = f"Failed to switch collection: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Return a direct answer from the most relevant result if it meets the confidence threshold.
        
        Args:
            context: List of context items from Chroma.
            
        Returns:
            The direct answer if found, otherwise None.
        """
        if not context:
            return None
            
        first_result = context[0]
        
        # Detailed debugging if verbose mode is enabled
        if self.verbose:
            logger.info(f"Direct answer check - confidence: {first_result.get('confidence', 0)}")
            logger.info(f"Direct answer check - has question: {'question' in first_result}")
            logger.info(f"Direct answer check - has answer: {'answer' in first_result}")
            
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            if self.verbose:
                logger.info(f"Found direct answer with confidence {first_result.get('confidence')}")
            
            # Return a formatted answer that includes both question and answer for clarity
            return f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
        
        return None

    async def get_relevant_context(self, query: str, api_key: Optional[str] = None, collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from ChromaDB.
        
        Args:
            query: The user's query.
            api_key: Optional API key for accessing the collection.
            collection_name: Optional explicit collection name.
            
        Returns:
            A list of context items filtered by relevance.
        """
        try:
            await self._resolve_collection(api_key, collection_name)
            
            # Generate an embedding for the query
            query_embedding = self.embeddings.embed_query(query)
            
            # Query ChromaDB for multiple results to enable filtering
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=10,  # Fetch extra results to enable better filtering.
                include=["documents", "metadatas", "distances"]
            )
            
            context_items = []
            
            # Process and filter each result based on the relevance threshold.
            for doc, metadata, distance in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                similarity = 1 - distance
                if similarity >= self.relevance_threshold:
                    # Create the base item with confidence and metadata
                    item = {
                        "confidence": similarity,
                        **metadata
                    }
                    
                    # Set the content field correctly - prioritize answer if available
                    if "question" in metadata and "answer" in metadata:
                        # If it's a QA pair, set content to the question and answer together
                        item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
                        item["question"] = metadata["question"]
                        item["answer"] = metadata["answer"]
                    else:
                        # Otherwise, use the document content
                        item["content"] = doc
                    
                    context_items.append(item)
            
            # Sort the context items by confidence and select the top 3 results
            context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)[:3]
            
            if self.verbose:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                if context_items:
                    logger.info(f"Top confidence score: {context_items[0].get('confidence', 0)}")
                    if "answer" in context_items[0]:
                        logger.info(f"Top result has answer field: {True}")
            
            return context_items
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []
