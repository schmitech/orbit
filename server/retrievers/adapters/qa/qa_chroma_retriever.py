"""
ChromaDB implementation of the BaseRetriever interface
"""

import logging
import traceback
from typing import Dict, Any, List, Optional, Union
from chromadb import HttpClient
from langchain_ollama import OllamaEmbeddings
from fastapi import HTTPException

from ...base.vector_retriever import VectorDBRetriever
from ...base.base_retriever import RetrieverFactory
from services.api_key_service import ApiKeyService
from embeddings.base import EmbeddingService

# Configure logging
logger = logging.getLogger(__name__)

class QAChromaRetriever(VectorDBRetriever):
    """Chroma implementation of the VectorDBRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Union[OllamaEmbeddings, EmbeddingService]] = None,
                collection: Any = None,
                **kwargs):
        """
        Initialize ChromaRetriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional OllamaEmbeddings instance or EmbeddingService
            collection: Optional ChromaDB collection
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings)
        
        # Store collection
        self.collection = collection
        
        # Flag to determine if we're using the old or new embedding service
        self.using_new_embedding_service = isinstance(embeddings, EmbeddingService)
        
        # Initialize ChromaDB client
        chroma_config = self.datasource_config
        self.chroma_client = HttpClient(
            host=chroma_config.get('host', 'localhost'),
            port=int(chroma_config.get('port', 8000))
        )
        
        # Configure ChromaDB and related HTTP client logging based on verbose setting
        if not self.verbose:
            # Only show warnings and errors when not in verbose mode
            for logger_name in ["httpx", "chromadb"]:
                client_logger = logging.getLogger(logger_name)
                client_logger.setLevel(logging.WARNING)

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'chroma'

    async def initialize(self) -> None:
        """Initialize required services."""
        # Call parent initialize to set up API key service
        await super().initialize()
        
        # Check if embedding is enabled
        embedding_enabled = self.config.get('embedding', {}).get('enabled', True)
        
        # Skip initialization if embeddings are disabled
        if not embedding_enabled:
            logger.info("Embedding services are disabled, retriever will operate in limited mode")
            self.embeddings = None
            self.using_new_embedding_service = False
            return
        
        # Initialize embeddings if not provided in constructor
        if self.embeddings is None:
            embedding_provider = self.config.get('embedding', {}).get('provider')
            
            # Use new embedding service architecture if specified
            if embedding_provider and 'embeddings' in self.config:
                from embeddings.base import EmbeddingServiceFactory
                self.embeddings = EmbeddingServiceFactory.create_embedding_service(self.config, embedding_provider)
                await self.embeddings.initialize()
                self.using_new_embedding_service = True
            else:
                # Fall back to legacy Ollama embeddings
                from langchain_ollama import OllamaEmbeddings
                ollama_conf = self.config.get('ollama', {})
                if not ollama_conf and 'inference' in self.config and 'ollama' in self.config['inference']:
                    # Handle new config structure
                    ollama_conf = self.config.get('inference', {}).get('ollama', {})
                    
                self.embeddings = OllamaEmbeddings(
                    model=ollama_conf.get('embed_model', 'nomic-embed-text'),
                    base_url=ollama_conf.get('base_url', 'http://localhost:11434')
                )
                self.using_new_embedding_service = False

    async def close(self) -> None:
        """Close any open services."""
        # Close parent services
        await super().close()
        
        # Close embedding service if using new architecture
        if self.using_new_embedding_service and self.embeddings:
            await self.embeddings.close()

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
            # Call the parent implementation first which resolves collection
            # and handles common logging/error handling
            await super().get_relevant_context(query, api_key, collection_name, **kwargs)
            
            debug_mode = self.verbose
            
            # Check if embeddings are available
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            if debug_mode:
                logger.info(f"Using embedding service: {type(self.embeddings).__name__}")
                logger.info(f"New embedding service: {self.using_new_embedding_service}")
            
            # Generate an embedding for the query
            try:
                if debug_mode:
                    logger.info("Generating embedding for query...")
                
                # Use the embed_query method from the parent class
                query_embedding = await self.embed_query(query)
                
                if not query_embedding or len(query_embedding) == 0:
                    logger.error("Received empty embedding, cannot perform vector search")
                    return []
                
                # Query ChromaDB for multiple results to enable filtering
                if debug_mode:
                    logger.info(f"Querying ChromaDB with {len(query_embedding)}-dimensional embedding")
                    logger.info(f"Max results: {self.max_results}")
                    
                try:
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=self.max_results,
                        include=["documents", "metadatas", "distances"]
                    )
                    
                    if debug_mode:
                        doc_count = len(results['documents'][0]) if results['documents'] else 0
                        logger.info(f"ChromaDB query returned {doc_count} documents")
                        if doc_count > 0:
                            logger.info(f"First document (truncated): {results['documents'][0][0][:100] if results['documents'][0] else 'None'}")
                            logger.info(f"First distance: {results['distances'][0][0] if results['distances'][0] else 'None'}")
                        else:
                            logger.warning("NO DOCUMENTS RETURNED FROM CHROMADB")
                except Exception as chroma_error:
                    logger.error(f"Error querying ChromaDB: {str(chroma_error)}")
                    logger.error(traceback.format_exc())
                    return []
                
                context_items = []
                
                # DISTANCE HANDLING: Check if distances are unusually large (suggesting L2 or Euclidean)
                is_euclidean = False
                first_distance = results['distances'][0][0] if results['distances'] and results['distances'][0] else 0
                if first_distance > 10:  # Arbitrary threshold for detecting Euclidean distances
                    is_euclidean = True
                    if debug_mode:
                        logger.info(f"Detected Euclidean distances (large values). Will adjust similarity calculation.")
                
                # Get max distance to normalize if using Euclidean
                max_distance = max(results['distances'][0]) if is_euclidean else 1
                
                # Process and filter each result based on the relevance threshold
                for doc, metadata, distance in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                ):
                    # Adjust similarity calculation based on distance metric
                    if is_euclidean:
                        # For Euclidean: normalize to [0,1] range and invert (smaller is better)
                        # This handles the case where distances are very large
                        normalized_distance = distance / max_distance if max_distance > 0 else 0
                        similarity = 1 - normalized_distance
                    else:
                        # For cosine: just use 1 - distance (closer to 1 is better)
                        similarity = 1 - distance
                    
                    # Always include at least the top result if we got results back
                    is_top_result = (doc == results['documents'][0][0] and 
                                    metadata == results['metadatas'][0][0])
                    
                    if similarity >= self.relevance_threshold or is_top_result:
                        # Create formatted context item
                        item = self._format_metadata(doc, metadata)
                        item["confidence"] = similarity  # Add confidence score
                        
                        context_items.append(item)
                
                # Sort the context items by confidence and select the top N results
                context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)[:self.return_results]
                
                if debug_mode:
                    logger.info(f"Retrieved {len(context_items)} relevant context items")
                    if context_items:
                        logger.info(f"Top confidence score: {context_items[0].get('confidence', 0)}")
                    else:
                        logger.warning("NO CONTEXT ITEMS AFTER FILTERING")
                
                return context_items
                
            except Exception as embedding_error:
                logger.error(f"Error during embeddings or query: {str(embedding_error)}")
                # Print more detailed error information
                logger.error(traceback.format_exc())
                return []
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            # Print more detailed error information
            logger.error(traceback.format_exc())
            return []

# Register the retriever with the factory
RetrieverFactory.register_retriever('chroma', QAChromaRetriever)