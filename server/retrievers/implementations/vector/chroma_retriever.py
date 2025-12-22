"""
ChromaDB implementation of the AbstractVectorRetriever interface.
Uses the datasource registry pattern for connection management.
"""

import logging
import os
from typing import Dict, Any, List, Optional
from chromadb import HttpClient, PersistentClient
from chromadb.errors import InvalidArgumentError
from fastapi import HTTPException
from pathlib import Path

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class ChromaRetriever(AbstractVectorRetriever):
    """
    ChromaDB implementation of the AbstractVectorRetriever interface.
    Connection is obtained from the datasource registry.
    """

    def __init__(self,
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                datasource: Any = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize ChromaRetriever.

        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional embeddings service or model
            datasource: ChromaDB datasource instance from the registry
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, datasource=datasource, domain_adapter=domain_adapter, **kwargs)

        # Store collection
        self.collection = None
        self.collection_name = None

        # Get collection name from adapter config during initialization
        adapter_config = config.get('adapter_config', {})
        if adapter_config and 'collection' in adapter_config:
            self.collection_name = adapter_config['collection']
            logger.debug(f"ChromaRetriever using collection from adapter config: {self.collection_name}")
        elif 'collection' in self.datasource_config:
            # Fallback to datasource config
            self.collection_name = self.datasource_config['collection']
            logger.debug(f"ChromaRetriever using collection from datasource config: {self.collection_name}")

        # Configure ChromaDB and related HTTP client logging to reduce noise
        # Suppress verbose ChromaDB/httpx logs - use WARNING level
        for logger_name in ["httpx", "chromadb"]:
            client_logger = logging.getLogger(logger_name)
            client_logger.setLevel(logging.WARNING)

    @property
    def chroma_client(self):
        """Get ChromaDB client from datasource."""
        return self.vector_client

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'chroma'

    async def initialize_client(self) -> None:
        """Initialize the ChromaDB client from datasource."""
        # Ensure datasource is initialized
        await self._ensure_datasource_initialized()

        logger.info("ChromaDB client initialized from datasource")

        # Set collection if we have a collection name from config
        if self.collection_name:
            logger.debug(f"Setting collection: {self.collection_name}")
            try:
                await self.set_collection(self.collection_name)
            except HTTPException:
                # The error is already logged in set_collection, just re-raise
                raise
            except Exception as e:
                logger.error(f"Unexpected error setting collection: {str(e)}")
                raise
        else:
            logger.warning("No collection name provided during initialization")

    async def close_client(self) -> None:
        """Close the ChromaDB client via datasource."""
        # Datasource close is handled by parent class
        logger.info("ChromaDB client closed via datasource")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        try:
            # First, check if the collection exists by listing all collections
            existing_collections = [col.name for col in self.chroma_client.list_collections()]
            
            if collection_name not in existing_collections:
                # Check if we should auto-create the collection
                auto_create = self.datasource_config.get('auto_create_collection', False)
                
                if auto_create:
                    try:
                        logger.info(f"Auto-creating collection '{collection_name}' with cosine similarity...")
                        # Create collection with cosine similarity metric to match Qdrant behavior
                        self.collection = self.chroma_client.create_collection(
                            name=collection_name,
                            metadata={"hnsw:space": "cosine"}
                        )
                        self.collection_name = collection_name
                        logger.info(f"Successfully created collection: {collection_name} with cosine similarity")
                        return
                    except Exception as create_error:
                        error_msg = f"Failed to auto-create collection '{collection_name}': {str(create_error)}"
                        logger.error(error_msg)
                        raise HTTPException(status_code=500, detail=error_msg)
                else:
                    # Log warning with available collections
                    available = ', '.join(existing_collections) if existing_collections else 'none'
                    class_name = self.__class__.__name__
                    logger.warning(f"[{class_name}] Collection '{collection_name}' not found. Available: [{available}]")
                    
                    # Raise error with user-friendly message
                    custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                                f"Collection '{collection_name}' not found. Available collections: {available}")
                    raise HTTPException(status_code=404, detail=custom_msg)
            
            # Collection exists, proceed to get it
            self.collection = self.chroma_client.get_collection(name=collection_name)
            self.collection_name = collection_name
            # Use class name in log for better clarity
            class_name = self.__class__.__name__
            logger.info(f"[{class_name}] Successfully connected to existing collection: {collection_name}")
            
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Failed to set collection '{collection_name}': {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search in ChromaDB.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and distances
        """
        if not hasattr(self, 'collection') or self.collection is None:
            logger.error("Collection is not properly initialized")
            return []
        
        try:
            # Query ChromaDB
            if hasattr(self.collection, 'query'):
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"]
                )
            else:
                logger.error("Collection object does not have a query method - likely incorrect object type")
                return []
            
            # Convert ChromaDB results to our standard format
            search_results = []
            
            if results['documents'] and len(results['documents']) > 0:
                documents = results['documents'][0]
                metadatas = results['metadatas'][0] if results['metadatas'] else [{}] * len(documents)
                distances = results['distances'][0] if results['distances'] else [0.0] * len(documents)
                
                for doc, metadata, distance in zip(documents, metadatas, distances):
                    # With cosine similarity, Chroma returns distances where:
                    # 0 = identical vectors, 2 = opposite vectors
                    # Convert to similarity score (0-1) like Qdrant
                    similarity_score = 1.0 - (distance / 2.0) if distance <= 2 else 0.0
                    
                    search_results.append({
                        'document': doc,
                        'metadata': metadata or {},
                        'distance': float(distance),
                        'score': similarity_score  # Add similarity score like Qdrant
                    })
            
            return search_results
        
        except InvalidArgumentError as e:
            error_msg = str(e)
            # Handle embedding dimension mismatch gracefully
            # ChromaDB error format: "Collection expecting embedding with dimension of X, got Y"
            if "expecting embedding with dimension" in error_msg.lower():
                query_dim = len(query_embedding)
                logger.error(
                    f"Embedding dimension mismatch for collection '{self.collection_name}': "
                    f"Query embedding has {query_dim} dimensions but collection expects a different size. "
                    f"Please ensure the embedding model matches the one used to create the collection."
                )
            else:
                logger.error(f"ChromaDB invalid argument error: {error_msg}")
            return []
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert ChromaDB cosine distance to similarity score.
        With cosine similarity metric, ChromaDB returns distances where:
        - 0 = identical vectors (similarity = 1)
        - 1 = orthogonal vectors (similarity = 0)
        - 2 = opposite vectors (similarity = -1)
        
        We normalize this to 0-1 range where 1 = most similar.
        
        Args:
            distance: Cosine distance from ChromaDB (0-2)
            
        Returns:
            Similarity score between 0 and 1
        """
        # Convert cosine distance to similarity score
        # Distance range [0, 2] maps to similarity [1, -1]
        # We normalize to [0, 1] for consistency with Qdrant
        if distance <= 0:
            return 1.0
        elif distance >= 2:
            return 0.0
        else:
            # Linear conversion: distance 0->1, distance 2->0
            return 1.0 - (distance / 2.0)

# Register the retriever with the factory
RetrieverFactory.register_retriever('chroma', ChromaRetriever) 