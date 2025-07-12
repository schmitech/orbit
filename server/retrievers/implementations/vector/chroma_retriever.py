"""
ChromaDB implementation of the AbstractVectorRetriever interface
"""

import logging
import os
from typing import Dict, Any, List, Optional
from chromadb import HttpClient, PersistentClient
from fastapi import HTTPException
from pathlib import Path

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory
from utils.lazy_loader import LazyLoader

# Configure logging
logger = logging.getLogger(__name__)

class ChromaRetriever(AbstractVectorRetriever):
    """ChromaDB implementation of the AbstractVectorRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize ChromaRetriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Store collection
        self.collection = None
        self.collection_name = None
        
        # Get collection name from adapter config during initialization
        adapter_config = config.get('adapter_config', {})
        if adapter_config and 'collection' in adapter_config:
            self.collection_name = adapter_config['collection']
            logger.info(f"ChromaRetriever using collection from adapter config: {self.collection_name}")
        elif 'collection' in self.datasource_config:
            # Fallback to datasource config
            self.collection_name = self.datasource_config['collection']
            logger.info(f"ChromaRetriever using collection from datasource config: {self.collection_name}")
        
        # Create a lazy loader for the ChromaDB client
        def create_chroma_client():
            use_local = self.datasource_config.get('use_local', False)
            
            if use_local:
                # Use PersistentClient for local filesystem access
                db_path = self.datasource_config.get('db_path', '../utils/chroma/chroma_db')
                db_path = Path(db_path).resolve()
                
                # Ensure the directory exists
                os.makedirs(db_path, exist_ok=True)
                
                logger.info(f"Using local ChromaDB at path: {db_path}")
                return PersistentClient(path=str(db_path))
            else:
                # Use HttpClient for remote server access
                logger.info(f"Connecting to ChromaDB at {self.datasource_config.get('host')}:{self.datasource_config.get('port')}...")
                return HttpClient(
                    host=self.datasource_config.get('host', 'localhost'),
                    port=int(self.datasource_config.get('port', 8000))
                )
        
        # Create a lazy loader for the ChromaDB client
        self._chroma_client_loader = LazyLoader(create_chroma_client, "ChromaDB client")
        
        # Configure ChromaDB and related HTTP client logging based on verbose setting
        if not self.verbose:
            # Only show warnings and errors when not in verbose mode
            for logger_name in ["httpx", "chromadb"]:
                client_logger = logging.getLogger(logger_name)
                client_logger.setLevel(logging.WARNING)

    @property
    def chroma_client(self):
        """Lazy-loaded ChromaDB client property."""
        return self._chroma_client_loader.get_instance()

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'chroma'

    async def initialize_client(self) -> None:
        """Initialize the ChromaDB client."""
        # The client is lazily loaded, so we just ensure it's accessible
        _ = self.chroma_client
        logger.info("ChromaDB client initialized")
        
        # Set collection if we have a collection name from config
        if self.collection_name:
            try:
                await self.set_collection(self.collection_name)
                logger.info(f"ChromaRetriever initialized with collection: {self.collection_name}")
            except Exception as e:
                logger.error(f"Failed to set collection during initialization: {str(e)}")
                # Don't raise here - let it be handled during actual usage

    async def close_client(self) -> None:
        """Close the ChromaDB client."""
        # ChromaDB doesn't require explicit closure for HTTP clients
        # The lazy loader will handle cleanup if needed
        logger.info("ChromaDB client closed")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        try:
            # Try to get the collection using the lazy-loaded client
            self.collection = self.chroma_client.get_collection(name=collection_name)
            self.collection_name = collection_name
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
        except Exception as e:
            # Check if this is a "collection does not exist" error
            if "does not exist" in str(e):
                # Try to create the collection
                try:
                    logger.info(f"Collection '{collection_name}' does not exist. Attempting to create it...")
                    self.collection = self.chroma_client.create_collection(name=collection_name)
                    self.collection_name = collection_name
                    logger.info(f"Successfully created collection: {collection_name}")
                except Exception as create_error:
                    # If creation fails, return a helpful error message
                    error_msg = f"Collection '{collection_name}' does not exist and could not be created: {str(create_error)}"
                    logger.error(error_msg)
                    # Access configuration directly
                    custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                                "Collection not found. Please ensure the collection exists before querying.")
                    raise HTTPException(status_code=404, detail=custom_msg)
            else:
                # For other errors, preserve the original behavior
                error_msg = f"Failed to switch collection: {str(e)}"
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
                    search_results.append({
                        'document': doc,
                        'metadata': metadata or {},
                        'distance': float(distance)
                    })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert ChromaDB L2 distance to similarity score.
        ChromaDB uses L2 distance where smaller values = more similar.
        
        Args:
            distance: L2 distance from ChromaDB
            
        Returns:
            Similarity score between 0 and 1
        """
        # ChromaDB-specific distance scaling
        # Using sigmoid-like function optimized for L2 distance
        return 1.0 / (1.0 + (distance / self.distance_scaling_factor))

# Register the retriever with the factory
RetrieverFactory.register_retriever('chroma', ChromaRetriever) 