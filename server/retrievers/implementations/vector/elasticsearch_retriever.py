"""
Elasticsearch implementation of the AbstractVectorRetriever interface
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class ElasticsearchRetriever(AbstractVectorRetriever):
    """Elasticsearch implementation of the AbstractVectorRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize ElasticsearchRetriever.
        
        Args:
            config: Configuration dictionary containing Elasticsearch and general settings
            embeddings: Optional embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Elasticsearch-specific settings
        self.node = self.datasource_config.get('node', 'https://localhost:9200')
        self.username = self.datasource_config.get('auth', {}).get('username')
        self.password = self.datasource_config.get('auth', {}).get('password')
        self.verify_certs = self.datasource_config.get('verify_certs', True)
        self.ca_certs = self.datasource_config.get('ca_certs')
        
        # Vector field settings
        self.vector_field = self.datasource_config.get('vector_field', 'embedding')
        self.text_field = self.datasource_config.get('text_field', 'content')
        
        # Store index
        self.index_name = None
        
        # Elasticsearch client
        self.es_client = None

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'elasticsearch'

    async def initialize_client(self) -> None:
        """Initialize the Elasticsearch client."""
        try:
            from elasticsearch import Elasticsearch
            
            # Prepare connection parameters
            es_config = {
                'hosts': [self.node],
                'verify_certs': self.verify_certs,
            }
            
            # Add authentication if provided
            if self.username and self.password:
                es_config['basic_auth'] = (self.username, self.password)
            
            # Add CA certs if provided
            if self.ca_certs:
                es_config['ca_certs'] = self.ca_certs
            
            # Create client
            self.es_client = Elasticsearch(**es_config)
            
            # Test connection
            if not self.es_client.ping():
                raise Exception("Failed to connect to Elasticsearch")
            
            logger.info(f"Connected to Elasticsearch at {self.node}")
            
        except ImportError:
            error_msg = "elasticsearch package is required for Elasticsearch retriever. Install with: pip install elasticsearch"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"Failed to connect to Elasticsearch: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def close_client(self) -> None:
        """Close the Elasticsearch client."""
        try:
            if self.es_client:
                self.es_client.close()
            logger.info("Elasticsearch client closed")
        except Exception as e:
            logger.error(f"Error closing Elasticsearch connection: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current index for retrieval.
        In Elasticsearch, collections are called indexes.
        
        Args:
            collection_name: Name of the index to use
        """
        if not collection_name:
            raise ValueError("Index name cannot be empty")
            
        try:
            # Check if index exists
            if not self.es_client.indices.exists(index=collection_name):
                error_msg = f"Index '{collection_name}' does not exist in Elasticsearch"
                logger.error(error_msg)
                custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                            "Collection not found. Please ensure the collection exists before querying.")
                raise HTTPException(status_code=404, detail=custom_msg)
            
            self.index_name = collection_name
            
            if self.verbose:
                logger.info(f"Switched to index: {collection_name}")
                
        except Exception as e:
            error_msg = f"Failed to switch index: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search in Elasticsearch.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and scores
        """
        if not self.index_name:
            logger.error("Index is not properly initialized")
            return []
        
        try:
            # Build the KNN search query
            query = {
                "knn": {
                    "field": self.vector_field,
                    "query_vector": query_embedding,
                    "k": top_k,
                    "num_candidates": max(top_k * 2, 100)  # Use more candidates for better recall
                },
                "_source": True  # Include all source fields
            }
            
            # Perform the search
            response = self.es_client.search(
                index=self.index_name,
                body=query,
                size=top_k
            )
            
            # Convert Elasticsearch results to our standard format
            search_results = []
            
            if 'hits' in response and 'hits' in response['hits']:
                for hit in response['hits']['hits']:
                    # Extract source data
                    source = hit.get('_source', {})
                    
                    # Get document content
                    doc = source.get(self.text_field, str(source))
                    
                    # Build metadata from source (exclude the vector field and text field)
                    metadata = {k: v for k, v in source.items() 
                              if k not in [self.vector_field, self.text_field]}
                    
                    # Get score (Elasticsearch returns similarity scores, higher is better)
                    score = hit.get('_score', 0.0)
                    
                    search_results.append({
                        'document': str(doc),
                        'metadata': metadata,
                        'score': float(score)  # Use score instead of distance
                    })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error querying Elasticsearch: {str(e)}")
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert Elasticsearch score to similarity score.
        Elasticsearch returns similarity scores directly (higher is better).
        
        Args:
            distance: Not used - Elasticsearch returns scores directly
            
        Returns:
            Similarity score between 0 and 1
        """
        # This method won't be called for Elasticsearch since we use scores directly
        # But we implement it for interface compatibility
        return distance

    async def get_relevant_context(self, 
                           query: str, 
                           api_key: Optional[str] = None, 
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Override to handle Elasticsearch's score-based results instead of distance-based.
        """
        try:
            # Call the parent's collection resolution logic
            await super().get_relevant_context(query, api_key, collection_name, **kwargs)
            
            debug_mode = self.verbose
            
            # Check for embeddings
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            # 1. Generate embedding for query
            query_embedding = await self.embed_query(query)
            
            if not query_embedding or len(query_embedding) == 0:
                logger.error("Received empty embedding, cannot perform vector search")
                return []
            
            if debug_mode:
                logger.info(f"Generated {len(query_embedding)}-dimensional embedding for query")
            
            # 2. Perform vector search
            search_results = await self.vector_search(query_embedding, self.max_results)
            
            if debug_mode:
                logger.info(f"Vector search returned {len(search_results)} results")
            
            # 3. Process and filter results (Elasticsearch-specific)
            context_items = []
            
            for result in search_results:
                # Extract data from result
                doc = result.get('document', '')
                metadata = result.get('metadata', {})
                score = result.get('score', 0.0)  # Elasticsearch returns similarity scores
                
                # Use score directly (no conversion needed)
                similarity = float(score)
                
                # Only include results that meet threshold
                if similarity >= self.confidence_threshold:
                    # Format document using domain adapter
                    item = self.format_document(doc, metadata)
                    item["confidence"] = similarity
                    item["metadata"]["source"] = self._get_datasource_name()
                    item["metadata"]["collection"] = self.collection
                    item["metadata"]["similarity"] = similarity
                    item["metadata"]["score"] = score
                    
                    context_items.append(item)
                    
                    if debug_mode:
                        logger.info(f"Accepted result with confidence: {similarity:.4f}")
                else:
                    if debug_mode:
                        logger.info(f"Rejected result with confidence: {similarity:.4f} (threshold: {self.confidence_threshold})")
            
            # 4. Sort by confidence (highest first)
            context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)
            
            # 5. Apply domain-specific filtering
            context_items = self.apply_domain_filtering(context_items, query)
            
            # 6. Apply final limit
            context_items = context_items[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                
            return context_items
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []

# Register the retriever with the factory
RetrieverFactory.register_retriever('elasticsearch', ElasticsearchRetriever) 