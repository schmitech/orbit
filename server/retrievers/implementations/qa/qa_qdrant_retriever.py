"""
QA-specialized Qdrant retriever that extends QdrantRetriever
"""

import logging
import traceback
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from ...base.base_retriever import RetrieverFactory
from ...adapters.registry import ADAPTER_REGISTRY
from ..vector.qdrant_retriever import QdrantRetriever

# Configure logging
logger = logging.getLogger(__name__)

class QAQdrantRetriever(QdrantRetriever):
    """
    QA-specialized Qdrant retriever that extends QdrantRetriever.
    
    This implementation adds QA-specific functionality on top of the 
    database-agnostic Qdrant retriever foundation.
    """

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                collection: Any = None,
                **kwargs):
        """
        Initialize QA Qdrant retriever.
        
        Args:
            config: Configuration dictionary containing Qdrant and general settings
            embeddings: Optional EmbeddingService instance
            domain_adapter: Optional domain adapter for specific document types
            collection: Optional Qdrant collection (not used in Qdrant, kept for compatibility)
            **kwargs: Additional arguments
        """
        # Get QA-specific adapter config if available
        adapter_config = None
        for adapter in config.get('adapters', []):
            if (adapter.get('type') == 'retriever' and 
                adapter.get('datasource') == 'qdrant' and 
                adapter.get('adapter') == 'qa'):
                adapter_config = adapter.get('config', {})
                logger.info(f"Found QA adapter config: {adapter_config}")
                break
        
        # Merge adapter config into datasource config
        merged_datasource_config = config.get('datasources', {}).get('qdrant', {}).copy()
        if adapter_config:
            merged_datasource_config.update(adapter_config)
            
        # Call parent constructor (QdrantRetriever)
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Override datasource_config with merged config
        self.datasource_config = merged_datasource_config
        
        # Override max_results and return_results after parent initialization
        if 'max_results' in merged_datasource_config:
            self.max_results = merged_datasource_config['max_results']
        if 'return_results' in merged_datasource_config:
            self.return_results = merged_datasource_config['return_results']
            
        # Override collection_name if set in adapter config (for new API key system)
        if hasattr(self, 'collection_name') and self.collection_name:
            logger.info(f"QAQdrantRetriever using collection from adapter config: {self.collection_name}")
        
        # QA-specific settings from adapter config
        self.confidence_threshold = adapter_config.get('confidence_threshold', 0.3) if adapter_config else 0.3
        self.score_threshold = adapter_config.get('score_threshold', self.confidence_threshold) if adapter_config else self.confidence_threshold
        self.score_scaling_factor = adapter_config.get('score_scaling_factor', 1.0) if adapter_config else 1.0
        
        logger.info(f"QAQdrantRetriever initialized with:")
        logger.info(f"  confidence_threshold={self.confidence_threshold}")
        logger.info(f"  score_threshold={self.score_threshold}")
        logger.info(f"  score_scaling_factor={self.score_scaling_factor}")
        logger.info(f"  max_results={self.max_results}")
        logger.info(f"  return_results={self.return_results}")

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
                    datasource='qdrant',
                    adapter_name='qa',
                    config=self.config
                )
                logger.info("Successfully created QA domain adapter for Qdrant")
            except Exception as e:
                logger.error(f"Failed to create domain adapter: {str(e)}")
                # Try to fall back to a generic QA adapter
                try:
                    self.domain_adapter = ADAPTER_REGISTRY.create(
                        adapter_type='retriever',
                        datasource='chroma',  # Use chroma_qa as fallback
                        adapter_name='qa',
                        config=self.config
                    )
                    logger.info("Using generic QA adapter as fallback")
                except Exception as fallback_e:
                    logger.error(f"Failed to create fallback domain adapter: {str(fallback_e)}")
                    # Continue without domain adapter
                    self.domain_adapter = None
        
        logger.info("QAQdrantRetriever initialized successfully")

    async def close(self) -> None:
        """Close any open services."""
        # Close parent services
        await super().close()
        
        # Close embedding service if using new architecture
        if self.embeddings:
            await self.embeddings.close()
        
        logger.info("QAQdrantRetriever closed successfully")

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
        
        # Fall back to QA-specific formatting if no adapter
        item = {
            "raw_document": doc,
            "metadata": metadata.copy(),
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
        Retrieve and filter relevant context from Qdrant.
        
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
                logger.info(f"=== Starting QA Qdrant retrieval for query: '{query}' ===")
                logger.info(f"API Key: {'Provided' if api_key else 'None'}")
                logger.info(f"Collection name: {collection_name or 'From config'}")
                logger.info(f"Domain adapter: {type(self.domain_adapter).__name__}")
            
            # Resolve collection: use provided collection_name or fall back to config
            resolved_collection = collection_name or self.collection_name or self.datasource_config.get('collection')
            
            if self.verbose:
                logger.info(f"Resolved collection: {resolved_collection}")
                
            # Set the collection
            if resolved_collection:
                self.collection_name = resolved_collection
            
            # Check if embeddings are available
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            if self.verbose:
                logger.info(f"Using embedding service: {type(self.embeddings).__name__}")
            
            # Ensure collection is properly set
            if not self.collection_name:
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
                
                # Query Qdrant for multiple results to enable filtering
                if self.verbose:
                    logger.info(f"Querying Qdrant with {len(query_embedding)}-dimensional embedding")
                    logger.info(f"Max results: {self.max_results}")
                    logger.info(f"Confidence threshold: {self.confidence_threshold}")
                    
                try:
                    # Perform search using Qdrant client
                    search_results = self.qdrant_client.search(
                        collection_name=self.collection_name,
                        query_vector=query_embedding,
                        limit=self.max_results,
                        with_payload=True
                    )
                    
                    if self.verbose:
                        logger.info(f"Qdrant query returned {len(search_results)} documents")
                        
                except Exception as qdrant_error:
                    logger.error(f"Error querying Qdrant: {str(qdrant_error)}")
                    logger.error(traceback.format_exc())
                    return []
                
                context_items = []
                
                # Process search results
                for result in search_results:
                    raw_similarity = float(result.score)
                    similarity = raw_similarity * self.score_scaling_factor
                    if similarity >= self.score_threshold:
                        payload = result.payload or {}
                        doc = (payload.get('content') or 
                               payload.get('document') or 
                               payload.get('text') or 
                               '')
                        context_item = self.format_document(str(doc), payload)
                        context_item["confidence"] = raw_similarity
                        if "metadata" not in context_item:
                            context_item["metadata"] = {}
                        context_item["metadata"]["source"] = self._get_datasource_name()
                        context_item["metadata"]["collection"] = self.collection_name
                        context_item["metadata"]["similarity"] = raw_similarity
                        context_item["metadata"]["scaled_similarity"] = similarity
                        context_item["metadata"]["score"] = raw_similarity
                        context_item["metadata"]["score_scaling_factor"] = self.score_scaling_factor
                        context_items.append(context_item)
                
                # Log how many docs passed filtering
                if self.verbose:
                    logger.info(f"{len(context_items)} documents passed score threshold filtering")
                
                # Sort and filter as before
                context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)
                if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_filtering'):
                    context_items = self.domain_adapter.apply_domain_filtering(context_items, query)
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
                logger.error(traceback.format_exc())
                return []
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

# Register the QA-specialized retriever with the factory
RetrieverFactory.register_retriever('qa_qdrant', QAQdrantRetriever)