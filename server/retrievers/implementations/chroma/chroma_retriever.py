"""
ChromaDB implementation of the BaseRetriever interface with QA enhancement
"""

import logging
import traceback
import os
from typing import Dict, Any, List, Optional, Union
from chromadb import HttpClient, PersistentClient
from langchain_ollama import OllamaEmbeddings
from fastapi import HTTPException
from pathlib import Path

from ...base.vector_retriever import VectorDBRetriever
from ...base.base_retriever import RetrieverFactory
from services.api_key_service import ApiKeyService
from embeddings.base import EmbeddingService
from ...adapters.registry import ADAPTER_REGISTRY

# Configure logging
logger = logging.getLogger(__name__)

class ChromaRetriever(VectorDBRetriever):
    """Chroma implementation of the VectorDBRetriever interface with QA support"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Union[OllamaEmbeddings, EmbeddingService]] = None,
                domain_adapter=None,
                collection: Any = None,
                **kwargs):
        """
        Initialize ChromaRetriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional OllamaEmbeddings instance or EmbeddingService
            domain_adapter: Optional domain adapter for specific document types
            collection: Optional ChromaDB collection
        """
        # Get ChromaDB configuration from datasources section
        datasource_config = config.get('datasources', {}).get('chroma', {})
        
        # Get adapter config if available
        adapter_config = None
        for adapter in config.get('adapters', []):
            if (adapter.get('type') == 'retriever' and 
                adapter.get('datasource') == 'chroma' and 
                adapter.get('adapter') == 'qa'):
                adapter_config = adapter.get('config', {})
                break
        
        # Merge configs with adapter config taking precedence
        merged_config = {**datasource_config}
        if adapter_config:
            merged_config.update(adapter_config)
            
        # Override max_results and return_results in config before parent initialization
        if 'max_results' in merged_config:
            config['max_results'] = merged_config['max_results']
        if 'return_results' in merged_config:
            config['return_results'] = merged_config['return_results']
            
        # Call the parent constructor with the merged config
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, datasource_config=merged_config)
        
        # Store collection
        self.collection = collection
        
        # Flag to determine if we're using the old or new embedding service
        self.using_new_embedding_service = isinstance(embeddings, EmbeddingService)
        
        # Store datasource config for later use
        self.datasource_config = merged_config
        
        # Initialize ChromaDB client based on use_local setting
        use_local = self.datasource_config.get('use_local', False)
        
        if use_local:
            # Use PersistentClient for local filesystem access
            db_path = self.datasource_config.get('db_path', '../utils/chroma/chroma_db')
            db_path = Path(db_path).resolve()
            
            # Ensure the directory exists
            os.makedirs(db_path, exist_ok=True)
            
            self.chroma_client = PersistentClient(path=str(db_path))
            logger.info(f"Using local ChromaDB at path: {db_path}")
        else:
            # Use HttpClient for remote server access
            self.chroma_client = HttpClient(
                host=self.datasource_config.get('host', 'localhost'),
                port=int(self.datasource_config.get('port', 8000))
            )
            logger.info(f"Connected to ChromaDB server at {self.datasource_config.get('host')}:{self.datasource_config.get('port')}")
        
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
        
        # Initialize domain adapter if not provided
        if self.domain_adapter is None:
            try:
                # Get adapter configuration from datasource config
                adapter_path = self.datasource_config.get('domain_adapter', 'adapters.chroma.qa')
                logger.info(f"Creating domain adapter: {adapter_path}")
                
                # Create adapter using registry
                self.domain_adapter = ADAPTER_REGISTRY.create(
                    adapter_type='retriever',
                    datasource='chroma',
                    adapter_name='qa',
                    config=self.config
                )
                logger.info(f"Successfully created {adapter_path} domain adapter")
            except Exception as e:
                logger.error(f"Failed to create domain adapter: {str(e)}")
                raise
        
        logger.info("ChromaRetriever initialized successfully")

    async def close(self) -> None:
        """Close any open services."""
        # Close parent services
        await super().close()
        
        # Close embedding service if using new architecture
        if self.using_new_embedding_service and self.embeddings:
            await self.embeddings.close()
        
        logger.info("ChromaRetriever closed successfully")

    async def set_collection(self, collection_name: str) -> None:
        """Set the current collection for retrieval."""
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
        try:
            # Try to get the collection
            self.collection = self.chroma_client.get_collection(name=collection_name)
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
        except Exception as e:
            # Check if this is a "collection does not exist" error
            if "does not exist" in str(e):
                # Try to create the collection
                try:
                    logger.info(f"Collection '{collection_name}' does not exist. Attempting to create it...")
                    self.collection = self.chroma_client.create_collection(name=collection_name)
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

    def format_document(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document using domain adapter if available.
        This provides compatibility with domain adapter pattern.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        if self.domain_adapter and hasattr(self.domain_adapter, 'format_document'):
            return self.domain_adapter.format_document(doc, metadata)
        
        # Fall back to basic formatting if no adapter
        return {
            "raw_document": doc,
            "metadata": metadata.copy(),
            "content": doc
        }
    
    def apply_domain_filtering(self, context_items, query):
        """
        Apply domain-specific filtering if domain adapter is available.
        Otherwise return items as-is.
        
        Args:
            context_items: List of context items to filter/rerank
            query: The original query
            
        Returns:
            Filtered/reranked list of context items
        """
        if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_filtering'):
            return self.domain_adapter.apply_domain_filtering(context_items, query)
        
        return context_items

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
            
            if debug_mode:
                logger.info(f"Using embedding service: {type(self.embeddings).__name__}")
                logger.info(f"New embedding service: {self.using_new_embedding_service}")
                logger.info(f"Using confidence threshold: {self.confidence_threshold}")
                logger.info(f"Using relevance threshold: {self.relevance_threshold}")
            
            # Ensure collection is properly set
            if not hasattr(self, 'collection') or self.collection is None:
                logger.error("Collection is not properly initialized")
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
                    # Make sure we're not trying to query on the client instead of the collection
                    if hasattr(self.collection, 'query'):
                        results = self.collection.query(
                            query_embeddings=[query_embedding],
                            n_results=self.max_results,
                            include=["documents", "metadatas", "distances"]
                        )
                    else:
                        logger.error("Collection object does not have a query method - likely incorrect object type")
                        return []
                    
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
                
                # Process and filter each result based on both thresholds
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
                    
                    # Apply both thresholds - only include if meets both thresholds
                    if (similarity >= self.relevance_threshold and 
                        similarity >= self.confidence_threshold):
                        # Create formatted context item using format_document which handles domain adapters
                        item = self.format_document(doc, metadata)
                        item["confidence"] = similarity  # Add confidence score
                        context_items.append(item)
                        if debug_mode:
                            logger.info(f"Added document with confidence {similarity:.4f}")
                    else:
                        if debug_mode:
                            logger.info(f"Filtered out document with confidence {similarity:.4f} (below thresholds: relevance={self.relevance_threshold}, confidence={self.confidence_threshold})")
                
                # Sort the context items by confidence
                context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)
                
                # Apply domain-specific filtering/reranking if available
                context_items = self.apply_domain_filtering(context_items, query)
                
                # Apply final limit
                context_items = context_items[:self.return_results]
                
                if debug_mode:
                    logger.info(f"Retrieved {len(context_items)} relevant context items")
                    if context_items:
                        logger.info(f"Top confidence score: {context_items[0].get('confidence', 0):.4f}")
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
RetrieverFactory.register_retriever('chroma', ChromaRetriever)