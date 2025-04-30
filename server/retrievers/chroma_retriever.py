"""
Enhanced ChromaDB implementation with domain adaptation support
"""

import logging
import traceback
from typing import Dict, Any, List, Optional, Union
from chromadb import HttpClient
from fastapi import HTTPException

from retrievers.base_retriever import VectorDBRetriever, RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class ChromaRetriever(VectorDBRetriever):
    """Enhanced Chroma implementation with domain support"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                collection: Any = None,
                **kwargs):
        """
        Initialize ChromaRetriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional embedding service
            domain_adapter: Optional domain adapter for specific document types
            collection: Optional ChromaDB collection
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter)
        
        # Store collection
        self.collection = collection
        
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
            **kwargs: Additional parameters, including domain-specific options
            
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
                except Exception as chroma_error:
                    logger.error(f"Error querying ChromaDB: {str(chroma_error)}")
                    logger.error(traceback.format_exc())
                    return []
                
                # DISTANCE HANDLING: Check if distances are unusually large (suggesting L2 or Euclidean)
                is_euclidean = False
                first_distance = results['distances'][0][0] if results['distances'] and results['distances'][0] else 0
                if first_distance > 10:  # Arbitrary threshold for detecting Euclidean distances
                    is_euclidean = True
                    if debug_mode:
                        logger.info(f"Detected Euclidean distances (large values). Will adjust similarity calculation.")
                
                # Get max distance to normalize if using Euclidean
                max_distance = max(results['distances'][0]) if is_euclidean else 1
                
                context_items = []
                
                # Process and filter each result based on the relevance threshold
                for doc, metadata, distance in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                ):
                    # Adjust similarity calculation based on distance metric
                    if is_euclidean:
                        # For Euclidean: normalize to [0,1] range and invert (smaller is better)
                        normalized_distance = distance / max_distance if max_distance > 0 else 0
                        similarity = 1 - normalized_distance
                    else:
                        # For cosine: just use 1 - distance (closer to 1 is better)
                        similarity = 1 - distance
                    
                    # Always include at least the top result if we got results back
                    is_top_result = (doc == results['documents'][0][0] and 
                                    metadata == results['metadatas'][0][0])
                    
                    if similarity >= self.relevance_threshold or is_top_result:
                        # Use domain adapter to format the document
                        item = self.format_document(doc, metadata)
                        item["confidence"] = similarity  # Add confidence score
                        
                        context_items.append(item)
                
                # Sort the context items by confidence
                context_items = sorted(context_items, 
                                     key=lambda x: x.get("confidence", 0), 
                                     reverse=True)
                
                # Apply domain-specific filtering/reranking
                context_items = self.apply_domain_filtering(context_items, query)
                
                # Apply final limit
                context_items = context_items[:self.return_results]
                
                if debug_mode:
                    logger.info(f"Retrieved {len(context_items)} relevant context items")
                    if context_items:
                        logger.info(f"Top confidence score: {context_items[0].get('confidence', 0)}")
                
                return context_items
                
            except Exception as embedding_error:
                logger.error(f"Error during embeddings or query: {str(embedding_error)}")
                logger.error(traceback.format_exc())
                return []
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

# Register the retriever with the factory
RetrieverFactory.register_retriever('chroma', ChromaRetriever)