"""
Template embedding storage system for managing SQL template embeddings.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
import hashlib
import json

from ..base.base_vector_store import BaseVectorStore
from ..base.store_manager import get_store_manager

logger = logging.getLogger(__name__)


class TemplateEmbeddingStore:
    """
    Manages template embeddings for SQL intent matching.
    
    This class provides:
    - Template embedding storage and retrieval
    - Similarity search for template matching
    - Template metadata management
    - Caching and optimization
    """
    
    def __init__(self, 
                 store_name: str = "template_embeddings",
                 store_type: str = "chroma",
                 collection_name: str = "sql_templates",
                 config: Optional[Dict[str, Any]] = None,
                 store_manager = None):
        """
        Initialize the template embedding store.
        
        Args:
            store_name: Name for the vector store instance
            store_type: Type of vector store to use
            collection_name: Name of the collection for templates
            config: Optional configuration for the store
            store_manager: Optional StoreManager instance
        """
        self.store_name = store_name
        self.store_type = store_type
        self.collection_name = collection_name
        self.config = config or {}
        self.store_manager = store_manager
        
        # Vector store instance
        self._vector_store: Optional[BaseVectorStore] = None
        
        # Template cache
        self._template_cache: Dict[str, Dict[str, Any]] = {}
        
        # Embedding dimension (will be set when first template is added)
        self._embedding_dimension: Optional[int] = None
        
        logger.info(f"TemplateEmbeddingStore initialized with store_type={store_type}, collection={collection_name}")
    
    async def initialize(self, config_path: Optional[str] = None):
        """
        Initialize the vector store connection.

        Args:
            config_path: Optional path to configuration file
        """
        try:
            # Use provided store manager or get/create one
            if self.store_manager:
                store_manager = self.store_manager
            else:
                store_manager = get_store_manager(config_path)

            # Determine which store type to use
            store_type_to_use = self.store_type
            available_types = store_manager.get_available_store_types()

            if not available_types:
                raise ValueError("No vector stores are enabled in stores.yaml configuration")

            # Check if requested store type is available
            if store_type_to_use not in available_types:
                # Fall back to the first available store type
                fallback_type = available_types[0]
                logger.warning(
                    f"Requested store type '{store_type_to_use}' is not available "
                    f"(available: {available_types}). Falling back to '{fallback_type}'"
                )
                store_type_to_use = fallback_type
                self.store_type = fallback_type  # Update instance variable

            # Create or get vector store
            store_config = self.config.copy()
            # Don't override ephemeral setting if it's already specified
            # The config should come from intent_sql_base.py which sets it based on chroma_persist

            self._vector_store = await store_manager.get_or_create_store(
                name=self.store_name,
                store_type=store_type_to_use,
                config={'connection_params': store_config}
            )

            # Ensure collection exists - but don't create it with wrong dimensions
            # Let the collection be created automatically when first vectors are added
            # This ensures the dimension matches the actual embeddings
            collection_exists = await self._vector_store.collection_exists(self.collection_name)
            if collection_exists:
                collection_info = await self._vector_store.get_collection_info(self.collection_name)
                collection_info.get('metadata', {}).get('dimension')

            logger.info(f"TemplateEmbeddingStore initialized successfully with store_type={store_type_to_use}")

        except Exception as e:
            logger.error(f"Failed to initialize TemplateEmbeddingStore: {e}")
            raise
    
    async def add_template(self, 
                          template_id: str,
                          template_data: Dict[str, Any],
                          embedding: List[float]) -> bool:
        """
        Add a template with its embedding to the store.
        
        Args:
            template_id: Unique identifier for the template
            template_data: Template data including SQL, description, etc.
            embedding: Vector embedding for the template
            
        Returns:
            True if successful, False otherwise
        """
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return False
        
        try:
            # Update embedding dimension if needed
            if self._embedding_dimension is None:
                self._embedding_dimension = len(embedding)
            elif len(embedding) != self._embedding_dimension:
                logger.warning(f"Embedding dimension mismatch: expected {self._embedding_dimension}, got {len(embedding)}")
            
            # Prepare metadata
            metadata = {
                'template_id': template_id,
                'sql': template_data.get('sql', ''),
                'description': template_data.get('description', ''),
                'category': template_data.get('category', ''),
                'parameters': json.dumps(template_data.get('parameters', [])),
                'examples': json.dumps(template_data.get('examples', [])),
                'confidence_score': template_data.get('confidence_score', 1.0)
            }
            
            # Add to vector store
            success = await self._vector_store.add_vectors(
                vectors=[embedding],
                ids=[template_id],
                metadata=[metadata],
                collection_name=self.collection_name
            )
            
            if success:
                # Update cache
                self._template_cache[template_id] = {
                    'data': template_data,
                    'embedding': embedding,
                    'metadata': metadata
                }
                logger.info(f"Added template {template_id} to embedding store")
            
            return success
            
        except Exception as e:
            logger.error(f"Error adding template {template_id}: {e}")
            return False
    
    async def batch_add_templates(self, 
                                 templates: List[Tuple[str, Dict[str, Any], List[float]]]) -> Dict[str, bool]:
        """
        Add multiple templates in batch.
        
        Args:
            templates: List of (template_id, template_data, embedding) tuples
            
        Returns:
            Dictionary of template_id to success status
        """
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return {t[0]: False for t in templates}
        
        try:
            ids = []
            vectors = []
            metadata_list = []
            
            for template_id, template_data, embedding in templates:
                # Update embedding dimension if needed
                if self._embedding_dimension is None:
                    self._embedding_dimension = len(embedding)
                
                ids.append(template_id)
                vectors.append(embedding)
                
                # Prepare metadata
                metadata = {
                    'template_id': template_id,
                    'sql': template_data.get('sql', ''),
                    'description': template_data.get('description', ''),
                    'category': template_data.get('category', ''),
                    'parameters': json.dumps(template_data.get('parameters', [])),
                    'examples': json.dumps(template_data.get('examples', [])),
                    'confidence_score': template_data.get('confidence_score', 1.0)
                }
                metadata_list.append(metadata)
                
                # Update cache
                self._template_cache[template_id] = {
                    'data': template_data,
                    'embedding': embedding,
                    'metadata': metadata
                }
            
            # Add to vector store
            success = await self._vector_store.add_vectors(
                vectors=vectors,
                ids=ids,
                metadata=metadata_list,
                collection_name=self.collection_name
            )
            
            logger.info(f"Added {len(templates)} templates to embedding store")
            
            return {template_id: success for template_id in ids}
            
        except Exception as e:
            logger.error(f"Error in batch add templates: {e}")
            return {t[0]: False for t in templates}
    
    async def search_similar_templates(self, 
                                      query_embedding: List[float],
                                      limit: int = 5,
                                      threshold: float = 0.5,
                                      filter_category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for similar templates based on embedding similarity.
        
        Args:
            query_embedding: Query vector embedding
            limit: Maximum number of results
            threshold: Minimum similarity threshold
            filter_category: Optional category filter
            
        Returns:
            List of similar templates with scores
        """
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return []
        
        try:
            # Prepare filter if category specified
            if filter_category:
                pass
            
            # Search for similar vectors
            results = await self._vector_store.similarity_search_with_threshold(
                query_vector=query_embedding,
                threshold=threshold,
                limit=limit,
                collection_name=self.collection_name
            )
            
            # Format results
            formatted_results = []
            for result in results:
                template_result = {
                    'template_id': result['metadata'].get('template_id'),
                    'score': result.get('score', 0),
                    'sql': result['metadata'].get('sql'),
                    'description': result['metadata'].get('description'),
                    'category': result['metadata'].get('category'),
                    'parameters': json.loads(result['metadata'].get('parameters', '[]')),
                    'examples': json.loads(result['metadata'].get('examples', '[]')),
                    'confidence_score': result['metadata'].get('confidence_score', 1.0)
                }
                formatted_results.append(template_result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching similar templates: {e}")
            return []
    
    async def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific template by ID.
        
        Args:
            template_id: Template identifier
            
        Returns:
            Template data or None if not found
        """
        # Check cache first
        if template_id in self._template_cache:
            return self._template_cache[template_id]['data']
        
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return None
        
        try:
            # Get from vector store
            result = await self._vector_store.get_vector(
                vector_id=template_id,
                collection_name=self.collection_name
            )
            
            if result:
                template_data = {
                    'template_id': result['metadata'].get('template_id'),
                    'sql': result['metadata'].get('sql'),
                    'description': result['metadata'].get('description'),
                    'category': result['metadata'].get('category'),
                    'parameters': json.loads(result['metadata'].get('parameters', '[]')),
                    'examples': json.loads(result['metadata'].get('examples', '[]')),
                    'confidence_score': result['metadata'].get('confidence_score', 1.0)
                }
                
                # Update cache
                self._template_cache[template_id] = {
                    'data': template_data,
                    'embedding': result.get('vector'),
                    'metadata': result['metadata']
                }
                
                return template_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting template {template_id}: {e}")
            return None
    
    async def update_template(self, 
                            template_id: str,
                            template_data: Optional[Dict[str, Any]] = None,
                            embedding: Optional[List[float]] = None) -> bool:
        """
        Update a template's data and/or embedding.
        
        Args:
            template_id: Template identifier
            template_data: New template data (optional)
            embedding: New embedding (optional)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return False
        
        try:
            update_metadata = None
            if template_data:
                update_metadata = {
                    'template_id': template_id,
                    'sql': template_data.get('sql', ''),
                    'description': template_data.get('description', ''),
                    'category': template_data.get('category', ''),
                    'parameters': json.dumps(template_data.get('parameters', [])),
                    'examples': json.dumps(template_data.get('examples', [])),
                    'confidence_score': template_data.get('confidence_score', 1.0)
                }
            
            success = await self._vector_store.update_vector(
                vector_id=template_id,
                vector=embedding,
                metadata=update_metadata,
                collection_name=self.collection_name
            )
            
            if success:
                # Update cache
                if template_id in self._template_cache:
                    if template_data:
                        self._template_cache[template_id]['data'] = template_data
                        self._template_cache[template_id]['metadata'] = update_metadata
                    if embedding:
                        self._template_cache[template_id]['embedding'] = embedding
                
                logger.info(f"Updated template {template_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating template {template_id}: {e}")
            return False
    
    async def delete_template(self, template_id: str) -> bool:
        """
        Delete a template from the store.
        
        Args:
            template_id: Template identifier
            
        Returns:
            True if successful, False otherwise
        """
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return False
        
        try:
            success = await self._vector_store.delete_vector(
                vector_id=template_id,
                collection_name=self.collection_name
            )
            
            if success:
                # Remove from cache
                if template_id in self._template_cache:
                    del self._template_cache[template_id]
                
                logger.info(f"Deleted template {template_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting template {template_id}: {e}")
            return False
    
    async def clear_all_templates(self) -> bool:
        """
        Clear all templates from the store.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._vector_store:
            logger.error("Vector store not initialized")
            return False
        
        try:
            success = await self._vector_store.clear_collection(self.collection_name)
            
            if success:
                # Clear cache
                self._template_cache.clear()
                logger.info("Cleared all templates from embedding store")
            
            return success
            
        except Exception as e:
            logger.error(f"Error clearing templates: {e}")
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the template store.
        
        Returns:
            Dictionary of statistics
        """
        stats = {
            'store_name': self.store_name,
            'store_type': self.store_type,
            'collection_name': self.collection_name,
            'cached_templates': len(self._template_cache),
            'embedding_dimension': self._embedding_dimension
        }
        
        if self._vector_store:
            try:
                collection_info = await self._vector_store.get_collection_info(self.collection_name)
                stats['total_templates'] = collection_info.get('count', 0)
                stats['collection_metadata'] = collection_info.get('metadata', {})
            except Exception as e:
                logger.error(f"Error getting collection info: {e}")
                stats['total_templates'] = 0
        
        return stats
    
    def generate_template_id(self, sql: str, description: str = "") -> str:
        """
        Generate a unique template ID based on SQL and description.
        
        Args:
            sql: SQL template
            description: Template description
            
        Returns:
            Unique template ID
        """
        content = f"{sql}:{description}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    async def close(self):
        """Close the template embedding store."""
        if self._vector_store:
            # The store manager will handle disconnection
            self._vector_store = None
            self._template_cache.clear()
            logger.info("TemplateEmbeddingStore closed")