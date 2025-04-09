"""
Chroma client for document retrieval
"""

import logging
from typing import Dict, Any, List, Optional
from chromadb import HttpClient
from langchain_ollama import OllamaEmbeddings
from services.summarization_service import SummarizationService
from services.api_key_service import ApiKeyService
from fastapi import HTTPException

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
        
        # Initialize services
        self.summarization_service = SummarizationService(config)
        self.api_key_service = ApiKeyService(config)
        
        # Initialize Chroma client
        self.chroma_client = HttpClient(
            host=config['chroma']['host'],
            port=int(config['chroma']['port'])
        )

    async def initialize(self):
        """Initialize the services"""
        await self.summarization_service.initialize()
        await self.api_key_service.initialize()

    async def close(self):
        """Close the services"""
        await self.summarization_service.close()
        await self.api_key_service.close()

    async def set_collection(self, collection_name: str) -> None:
        """Set the current collection for retrieval"""
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        try:
            self.collection = self.chroma_client.get_collection(name=collection_name)
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to switch collection: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to access collection: {str(e)}")

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

    async def get_relevant_context(self, query: str, api_key: Optional[str] = None, collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from ChromaDB
        
        Args:
            query: The user's query
            api_key: Optional API key to determine collection
            collection_name: Optional collection name to use directly
            
        Returns:
            List[Dict[str, Any]]: List of relevant context items
        """
        try:
            # If API key is provided, validate and get collection
            if api_key:
                is_valid, collection_name = await self.api_key_service.validate_api_key(api_key)
                if not is_valid:
                    raise ValueError("Invalid API key")
                if collection_name:
                    await self.set_collection(collection_name)
            # If collection_name is provided directly, use it
            elif collection_name:
                await self.set_collection(collection_name)
            
            # If no collection is set yet, use the default from config
            if self.collection is None:
                default_collection = self.config.get('chroma', {}).get('collection')
                if default_collection:
                    await self.set_collection(default_collection)
                else:
                    logger.error("No collection available. Ensure a default collection is configured or an API key is provided.")
                    return []
            
            # Generate embedding for the query
            query_embedding = self.embeddings.embed_query(query)
            
            # Query ChromaDB with increased n_results to allow for better filtering
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=10,  # Get more results for better filtering
                include=["documents", "metadatas", "distances"]
            )
            
            context_items = []
            
            # Process each result with stricter filtering
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
                    
                    # If this is a direct answer, check if it needs summarizing
                    if "question" in metadata and "answer" in metadata:
                        # Let the summarization service handle length checks
                        summary = await self.summarization_service.summarize(metadata["answer"])
                        if summary != metadata["answer"]:  # Only update if summarization occurred
                            if self.verbose:
                                logger.info(f"Summarized answer: {len(metadata['answer'])} → {len(summary)} chars")
                            item["answer"] = summary
                    
                    context_items.append(item)
            
            # Sort by confidence and take top 3 most relevant items
            context_items.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            context_items = context_items[:3]
            
            if self.verbose:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                if context_items:
                    logger.info(f"Top confidence score: {context_items[0].get('confidence', 0)}")
            
            return context_items
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []