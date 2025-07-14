"""
QA-specialized ChromaDB retriever that extends ChromaRetriever
"""

import logging
import traceback
import os
from typing import Dict, Any, List, Optional, Union
from chromadb import HttpClient, PersistentClient
from langchain_ollama import OllamaEmbeddings
from fastapi import HTTPException
from pathlib import Path

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory
from services.api_key_service import ApiKeyService
from embeddings.base import EmbeddingService, EmbeddingServiceFactory
from ...adapters.registry import ADAPTER_REGISTRY
from utils.lazy_loader import LazyLoader
from ..vector.chroma_retriever import ChromaRetriever

# Configure logging
logger = logging.getLogger(__name__)

class QAChromaRetriever(ChromaRetriever):
    """
    QA-specialized ChromaDB retriever that extends ChromaRetriever.
    
    This implementation adds QA-specific functionality on top of the 
    database-agnostic ChromaDB retriever foundation.
    """

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                collection: Any = None,
                **kwargs):
        """
        Initialize QA ChromaDB retriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional EmbeddingService instance
            domain_adapter: Optional domain adapter for specific document types
            collection: Optional ChromaDB collection
            **kwargs: Additional arguments
        """
        # Get QA-specific adapter config if available
        adapter_config = None
        for adapter in config.get('adapters', []):
            if (adapter.get('type') == 'retriever' and 
                adapter.get('datasource') == 'chroma' and 
                adapter.get('adapter') == 'qa'):
                adapter_config = adapter.get('config', {})
                break
        
        # Merge adapter config into datasource config
        merged_datasource_config = config.get('datasources', {}).get('chroma', {}).copy()
        if adapter_config:
            merged_datasource_config.update(adapter_config)
            
        # Override max_results and return_results in config before parent initialization
        if 'max_results' in merged_datasource_config:
            config['max_results'] = merged_datasource_config['max_results']
        if 'return_results' in merged_datasource_config:
            config['return_results'] = merged_datasource_config['return_results']
            
        # Call parent constructor (ChromaRetriever)
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Override datasource_config with merged config
        self.datasource_config = merged_datasource_config
        
        # Store collection if provided
        if collection is not None:
            self.collection = collection
            
        # Override collection_name if set in adapter config (for new API key system)
        if hasattr(self, 'collection_name') and self.collection_name:
            logger.info(f"QAChromaRetriever using collection from adapter config: {self.collection_name}")
        
        # QA-specific settings from adapter config
        self.confidence_threshold = adapter_config.get('confidence_threshold', 0.3) if adapter_config else 0.3
        self.distance_scaling_factor = adapter_config.get('distance_scaling_factor', 200.0) if adapter_config else 200.0
        
        logger.info(f"QAChromaRetriever initialized with confidence_threshold={self.confidence_threshold}")

    async def initialize(self) -> None:
        """Initialize required services."""
        # Call parent initialize to set up basic services
        await super().initialize()
        
        # Initialize client
        await self.initialize_client()
        
        # Initialize domain adapter if not provided
        if self.domain_adapter is None:
            try:
                # Create adapter using registry
                self.domain_adapter = ADAPTER_REGISTRY.create(
                    adapter_type='retriever',
                    datasource='chroma',
                    adapter_name='qa',
                    config=self.config
                )
                logger.info("Successfully created QA domain adapter")
            except Exception as e:
                logger.error(f"Failed to create domain adapter: {str(e)}")
                raise
        
        logger.info("QAChromaRetriever initialized successfully")

    async def close(self) -> None:
        """Close any open services."""
        # Close parent services
        await super().close()
        
        # Close embedding service if using new architecture
        if self.embeddings:
            await self.embeddings.close()
        
        logger.info("QAChromaRetriever closed successfully")

    async def set_collection(self, collection_name: str) -> None:
        """Set the current collection for retrieval."""
        if self.verbose:
            logger.info(f"[QAChromaRetriever] set_collection called with collection_name='{collection_name}'")
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
        try:
            # Try to get the collection using the lazy-loaded client
            self.collection = self.chroma_client.get_collection(name=collection_name)
            self.collection_name = collection_name
            if self.verbose:
                logger.info(f"[QAChromaRetriever] Switched to collection: {collection_name}")
        except Exception as e:
            # Check if this is a "collection does not exist" error
            if "does not exist" in str(e):
                # Try to create the collection
                try:
                    if self.verbose:
                        logger.info(f"[QAChromaRetriever] Collection '{collection_name}' does not exist. Attempting to create it...")
                    self.collection = self.chroma_client.create_collection(name=collection_name)
                    self.collection_name = collection_name
                    if self.verbose:
                        logger.info(f"[QAChromaRetriever] Successfully created collection: {collection_name}")
                except Exception as create_error:
                    # If creation fails, return a helpful error message
                    error_msg = f"Collection '{collection_name}' does not exist and could not be created: {str(create_error)}"
                    logger.error(f"[QAChromaRetriever] {error_msg}")
                    # Access configuration directly
                    custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                                "Collection not found. Please ensure the collection exists before querying.")
                    raise HTTPException(status_code=404, detail=custom_msg)
            else:
                # For other errors, preserve the original behavior
                error_msg = f"Failed to switch collection: {str(e)}"
                logger.error(f"[QAChromaRetriever] {error_msg}")
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
            collection_name: Optional collection name (falls back to config)
            **kwargs: Additional parameters, including domain-specific options
            
        Returns:
            A list of context items filtered by relevance.
        """
        try:
            # Check initialization status
            if not self.initialized:
                await self.initialize()
            
            if self.verbose:
                logger.info(f"[QAChromaRetriever] get_relevant_context called with query='{query}', api_key='{api_key}', collection_name='{collection_name}'")
                logger.info(f"[QAChromaRetriever] self.collection_name before resolution: {self.collection_name}")
                logger.info(f"[QAChromaRetriever] self.datasource_config.get('collection'): {self.datasource_config.get('collection')}")
            
            # Resolve collection: use provided collection_name or fall back to config
            resolved_collection = collection_name or self.collection_name or self.datasource_config.get('collection')
            
            if self.verbose:
                logger.info(f"[QAChromaRetriever] Resolved collection: {resolved_collection}")
            
            # Set the collection
            if resolved_collection:
                await self.set_collection(resolved_collection)
            else:
                logger.error("[QAChromaRetriever] No collection could be resolved! Not calling set_collection.")
            
            # Check if embeddings are available
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            if self.verbose:
                logger.info(f"Using embedding service: {type(self.embeddings).__name__}")
            
            # Ensure collection is properly set
            if not hasattr(self, 'collection') or self.collection is None:
                logger.error("Collection is not properly initialized")
                return []
            
            # Generate an embedding for the query
            try:
                if self.verbose:
                    logger.info("Generating embedding for query...")
                
                # Use the embed_query method from the parent class
                query_embedding = await self.embed_query(query)
                
                if not query_embedding or len(query_embedding) == 0:
                    logger.error("Received empty embedding, cannot perform vector search")
                    return []
                
                # Query ChromaDB for multiple results to enable filtering
                if self.verbose:
                    logger.info(f"Querying ChromaDB with {len(query_embedding)}-dimensional embedding")
                    logger.info(f"Max results: {self.max_results}")
                    logger.info(f"Confidence threshold: {self.confidence_threshold}")
                    
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
                    
                    if self.verbose:
                        doc_count = len(results['documents'][0]) if results['documents'] else 0
                        logger.info(f"ChromaDB query returned {doc_count} documents")
                        if doc_count > 0:
                            logger.info("=== Initial Results from ChromaDB ===")
                            for i, (doc, metadata, distance) in enumerate(zip(results['documents'][0], results['metadatas'][0], results['distances'][0])):
                                logger.info(f"\nDocument {i+1}:")
                                logger.info(f"Distance: {distance:.4f}")
                                logger.info(f"Content (truncated): {doc[:200]}...")
                                if metadata:
                                    logger.info(f"Metadata: {metadata}")
                        else:
                            logger.warning("NO DOCUMENTS RETURNED FROM CHROMADB")
                except Exception as chroma_error:
                    logger.error(f"Error querying ChromaDB: {str(chroma_error)}")
                    logger.error(traceback.format_exc())
                    return []
                
                context_items = []
                
                # Calculate similarity score from distance
                # ChromaDB returns L2 distances, where smaller values = more similar
                # Convert to similarity score between 0 and 1
                distance = float(results['distances'][0][0])
                
                # More lenient similarity calculation for cross-language matching
                # Using a sigmoid-like function that gives higher scores for larger distances
                similarity = 1.0 / (1.0 + (distance / self.distance_scaling_factor))  # Scale down the distance to get higher similarity scores
                
                if self.verbose:
                    logger.info("\n=== Processing Results ===")
                    logger.info(f"Raw distance: {distance:.4f}")
                    logger.info(f"Converted similarity score: {similarity:.4f}")
                    logger.info(f"Confidence threshold: {self.confidence_threshold}")
                    logger.info(f"Distance scaling factor: {self.distance_scaling_factor}")
                
                # Process if score exceeds threshold
                if similarity >= self.confidence_threshold:
                    # Format the document using the domain adapter
                    context_item = self.format_document(results['documents'][0][0][0], results['metadatas'][0][0])
                    
                    # Add confidence score
                    context_item["confidence"] = similarity
                    
                    # Add metadata about the source
                    if "metadata" not in context_item:
                        context_item["metadata"] = {}
                    
                    context_item["metadata"]["source"] = self._get_datasource_name()
                    context_item["metadata"]["collection"] = self.collection.name # Use the collection name from the adapter config
                    context_item["metadata"]["similarity"] = similarity
                    context_item["metadata"]["distance"] = distance  # Keep original distance for debugging
                    
                    context_items.append(context_item)
                    
                    if self.verbose:
                        logger.info("\n=== Accepted Document ===")
                        logger.info(f"Confidence: {similarity:.4f}")
                        logger.info(f"Content (truncated): {context_item.get('content', '')[:200]}...")
                        logger.info(f"Metadata: {context_item.get('metadata', {})}")
                else:
                    if self.verbose:
                        logger.info("\n=== Rejected Document ===")
                        logger.info(f"Confidence: {similarity:.4f} (below threshold: {self.confidence_threshold})")
                        logger.info(f"Content (truncated): {results['documents'][0][0][:200]}...")
                        logger.info(f"Metadata: {results['metadatas'][0][0]}")
                
                # Sort the context items by confidence
                context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)
                
                # Apply domain-specific filtering/reranking if available
                if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_filtering'):
                    if self.verbose:
                        logger.info("\n=== Before Domain Filtering ===")
                        logger.info(f"Number of items: {len(context_items)}")
                        for i, item in enumerate(context_items):
                            logger.info(f"\nItem {i+1}:")
                            logger.info(f"Confidence: {item.get('confidence', 0):.4f}")
                            logger.info(f"Content (truncated): {item.get('content', '')[:200]}...")
                    
                    context_items = self.domain_adapter.apply_domain_filtering(context_items, query)
                    
                    if self.verbose:
                        logger.info("\n=== After Domain Filtering ===")
                        logger.info(f"Number of items: {len(context_items)}")
                        for i, item in enumerate(context_items):
                            logger.info(f"\nItem {i+1}:")
                            logger.info(f"Confidence: {item.get('confidence', 0):.4f}")
                            logger.info(f"Content (truncated): {item.get('content', '')[:200]}...")
                
                # Apply final limit
                context_items = context_items[:self.return_results]
                
                if self.verbose:
                    logger.info("\n=== Final Results ===")
                    logger.info(f"Retrieved {len(context_items)} relevant context items")
                    if context_items:
                        logger.info(f"Top confidence score: {context_items[0].get('confidence', 0):.4f}")
                        for i, item in enumerate(context_items):
                            logger.info(f"\nFinal Item {i+1}:")
                            logger.info(f"Confidence: {item.get('confidence', 0):.4f}")
                            logger.info(f"Content (truncated): {item.get('content', '')[:200]}...")
                            logger.info(f"Metadata: {item.get('metadata', {})}")
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

# Register the QA-specialized retriever with the factory
RetrieverFactory.register_retriever('qa_chroma', QAChromaRetriever)