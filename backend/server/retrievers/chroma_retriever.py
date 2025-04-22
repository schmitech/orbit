"""
ChromaDB implementation of the BaseRetriever interface
"""

import logging
from typing import Dict, Any, List, Optional
from chromadb import HttpClient
from langchain_ollama import OllamaEmbeddings
from fastapi import HTTPException

from retrievers.base_retriever import BaseRetriever
from services.api_key_service import ApiKeyService

# Configure logging
logger = logging.getLogger(__name__)

class ChromaRetriever(BaseRetriever):
    """Chroma implementation of the BaseRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],  # Make config the first required parameter
                embeddings: Optional[OllamaEmbeddings] = None,
                collection: Any = None):
        """
        Initialize ChromaRetriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional OllamaEmbeddings instance
            collection: Optional ChromaDB collection
        """
        if not config:
            raise ValueError("Config is required for ChromaRetriever initialization")
            
        self.config = config
        self.embeddings = embeddings
        self.collection = collection
        
        # Extract chroma-specific configuration
        chroma_config = config.get('chroma', {})
        self.confidence_threshold = chroma_config.get('confidence_threshold', 0.7)
        self.relevance_threshold = chroma_config.get('relevance_threshold', 0.5)
        self.verbose = config.get('general', {}).get('verbose', False)
        self.max_results = chroma_config.get('max_results', 10)
        self.return_results = chroma_config.get('return_results', 3)
        
        # Initialize dependent services
        self.api_key_service = ApiKeyService(config)
        
        # Initialize ChromaDB client
        self.chroma_client = HttpClient(
            host=chroma_config.get('host', 'localhost'),  # Add default values
            port=int(chroma_config.get('port', 8000))
        )

    async def initialize(self) -> None:
        """Initialize required services."""
        await self.api_key_service.initialize()
        
        # Initialize embeddings if not provided in constructor
        if self.embeddings is None:
            from langchain_ollama import OllamaEmbeddings
            ollama_conf = self.config.get('ollama', {})
            self.embeddings = OllamaEmbeddings(
                model=ollama_conf.get('embed_model', 'bge-m3'),
                base_url=ollama_conf.get('base_url', 'http://localhost:11434')
            )

    async def close(self) -> None:
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

    def _format_metadata(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        
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

    async def get_relevant_context(self, 
                               query: str, 
                               api_key: Optional[str] = None, 
                               collection_name: Optional[str] = None,
                               **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from ChromaDB.
        
        Args:
            query: The user's query.
            api_key: Optional API key for accessing the collection.
            collection_name: Optional explicit collection name.
            **kwargs: Additional parameters
            
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
                n_results=self.max_results,
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
                    # Create formatted context item
                    item = self._format_metadata(doc, metadata)
                    item["confidence"] = similarity  # Add confidence score
                    
                    context_items.append(item)
            
            # Sort the context items by confidence and select the top N results
            context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)[:self.return_results]
            
            if self.verbose:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                if context_items:
                    logger.info(f"Top confidence score: {context_items[0].get('confidence', 0)}")
            
            return context_items
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []