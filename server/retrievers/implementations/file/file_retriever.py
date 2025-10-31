"""
File Vector Retriever

Retriever for querying uploaded files using vector stores.
Supports semantic search over chunked document content.
"""

import logging
from typing import Dict, Any, List, Optional
import uuid

from retrievers.base.abstract_vector_retriever import AbstractVectorRetriever
from services.file_metadata.metadata_store import FileMetadataStore
from vector_stores.base.store_manager import StoreManager

logger = logging.getLogger(__name__)


class FileVectorRetriever(AbstractVectorRetriever):
    """
    Retriever for querying uploaded files via vector store.
    
    Leverages chunked file content stored in vector stores (Chroma, Pinecone, etc.)
    for semantic search and Q&A over uploaded documents.
    """
    
    def __init__(self, config: Dict[str, Any] = None, datasource=None, domain_adapter=None, **kwargs):
        """
        Initialize file retriever.
        
        Args:
            config: Configuration dictionary
            datasource: Not used (file adapter manages storage)
            domain_adapter: Domain adapter for formatting
            **kwargs: Additional parameters
        """
        # Ensure config is not None or empty (base_retriever requires non-empty config)
        if config is None or config == {}:
            # Provide minimal config structure
            config = {'files': {}}
        
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # File-specific configuration
        self.metadata_store = FileMetadataStore(config=config)
        
        # Get collection_prefix from adapter config first, then files.retriever, then global files config, then default
        files_config = self.config.get('files', {})
        retriever_config = files_config.get('retriever', {})
        self.collection_prefix = self.config.get('collection_prefix') or \
                                retriever_config.get('collection_prefix') or \
                                files_config.get('default_collection_prefix', 'files_')
        
        # Initialize store manager for vector operations
        self.store_manager = None
        self._default_store = None
    
    async def ensure_initialized(self):
        """Ensure retriever is initialized before use."""
        if not self.initialized:
            await self.initialize()
    
    async def initialize(self):
        """Initialize the retriever."""
        if self.initialized:
            return
        
        # Initialize embeddings
        await super().initialize()
        
        # Initialize store manager (only if not already set - allows test mocking)
        if self.store_manager is None:
            self.store_manager = StoreManager()
        
        # Get default vector store from adapter config first, then global files.retriever config, then default
        files_config = self.config.get('files', {})
        retriever_config = files_config.get('retriever', {})
        vector_store_name = self.config.get('vector_store') or \
                           retriever_config.get('vector_store') or \
                           files_config.get('default_vector_store', 'chroma')
        
        try:
            # First try to get existing store
            self._default_store = await self.store_manager.get_store(vector_store_name)
            
            # If not found, try to create it (will use default Chroma config if available)
            if not self._default_store:
                try:
                    logger.debug(f"Store '{vector_store_name}' not found, attempting to create it...")
                    self._default_store = await self.store_manager.get_or_create_store(
                        name=vector_store_name,
                        store_type='chroma'  # Default type
                    )
                    logger.info(f"Created vector store: {vector_store_name}")
                except Exception as create_error:
                    logger.warning(f"Could not create vector store '{vector_store_name}': {create_error}. "
                                 f"File adapter will operate in limited mode without vector search. "
                                 f"Ensure Chroma is configured in config/stores.yaml")
                    self._default_store = None
            else:
                logger.info(f"Initialized vector store: {vector_store_name}")
        except Exception as e:
            logger.warning(f"Error initializing vector store {vector_store_name}: {e}. "
                         f"File adapter will operate in limited mode. Check vector store configuration in config/stores.yaml.")
            self._default_store = None
        
        self.initialized = True
        logger.info("FileVectorRetriever initialized")
    
    async def get_relevant_context(self, query: str, api_key: Optional[str] = None, 
                                  file_id: Optional[str] = None,
                                  file_ids: Optional[List[str]] = None,
                                  collection_name: Optional[str] = None,
                                  **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from uploaded files.
        
        Args:
            query: User query
            api_key: API key for filtering
            file_id: Optional specific file to query (legacy parameter)
            file_ids: Optional list of specific files to query
            collection_name: Optional specific collection
            
        Returns:
            List of relevant context items
        """
        await self.ensure_initialized()
        
        # Support both file_id (singular) and file_ids (plural) for backward compatibility
        target_file_ids = file_ids or ([file_id] if file_id else None)
        
        # Generate query embedding
        query_embedding = await self.embed_query(query)
        
        # Determine collections to search
        collections = await self._get_collections_multiple(target_file_ids, api_key, collection_name)
        
        # Search across collections
        results = []
        for collection in collections:
            collection_results = await self._search_collection(
                collection,
                query_embedding,
                file_ids=target_file_ids
            )
            results.extend(collection_results)
        
        # Apply domain filtering
        results = self.apply_domain_filtering(results, query)
        
        # Group and format results
        formatted_results = self._format_results(results)
        
        return formatted_results
    
    async def _get_collections(self, file_id: Optional[str], api_key: Optional[str],
                              collection_name: Optional[str]) -> List[str]:
        """Get list of collections to search (legacy method for single file_id)."""
        return await self._get_collections_multiple([file_id] if file_id else None, api_key, collection_name)
    
    async def _get_collections_multiple(self, file_ids: Optional[List[str]], api_key: Optional[str],
                                       collection_name: Optional[str]) -> List[str]:
        """Get list of collections to search for multiple file IDs."""
        if collection_name:
            return [collection_name]
        
        if file_ids:
            # Get collections for all specified files
            collections = set()
            for file_id in file_ids:
                file_info = await self.metadata_store.get_file_info(file_id)
                if file_info and file_info.get('collection_name'):
                    collections.add(file_info['collection_name'])
            return list(collections) if collections else []
        
        # Get all collections for API key
        if api_key:
            files = await self.metadata_store.list_files(api_key)
            collections = {f['collection_name'] for f in files if f.get('collection_name')}
            return list(collections)
        
        return []
    
    async def _search_collection(self, collection_name: str, query_embedding: List[float],
                                 file_id: Optional[str] = None, file_ids: Optional[List[str]] = None,
                                 limit: int = 10) -> List[Dict[str, Any]]:
        """Search a specific collection for relevant chunks."""
        if not self._default_store:
            return []
        
        try:
            # Build metadata filter
            filter_metadata = {}
            # Support both single file_id and multiple file_ids
            target_file_ids = file_ids or ([file_id] if file_id else None)
            if target_file_ids:
                # If multiple file_ids, we need to filter by any of them
                # Note: Some vector stores support OR filters, others may need multiple queries
                # For now, filter by the first file_id if multiple (we'll search all collections anyway)
                if len(target_file_ids) == 1:
                    filter_metadata['file_id'] = target_file_ids[0]
                # TODO: Support proper OR filtering for multiple file_ids in vector store queries
            
            # Search vector store
            results = await self._default_store.search_vectors(
                query_vector=query_embedding,
                limit=limit,
                collection_name=collection_name,
                filter_metadata=filter_metadata
            )
            
            # Post-filter results by file_ids if multiple files specified
            if target_file_ids and len(target_file_ids) > 1:
                results = [r for r in results if r.get('metadata', {}).get('file_id') in target_file_ids]
            
            # Retrieve full chunk information from metadata store
            enriched_results = []
            for result in results:
                chunk_id = result.get('id')
                if chunk_id:
                    # Get chunk metadata
                    chunk_info = await self.metadata_store.get_chunk_info(chunk_id)
                    if chunk_info:
                        result['chunk_metadata'] = chunk_info
                    
                    enriched_results.append(result)
            
            return enriched_results
        
        except Exception as e:
            logger.error(f"Error searching collection {collection_name}: {e}")
            return []
    
    def _format_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format search results with file metadata."""
        formatted = []
        
        for result in results:
            # Get file info from chunk metadata
            file_id = result.get('metadata', {}).get('file_id')
            if file_id:
                formatted_item = {
                    'content': result.get('content', result.get('text', '')),
                    'metadata': {
                        'chunk_id': result.get('id'),
                        'file_id': file_id,
                        'chunk_index': result.get('metadata', {}).get('chunk_index'),
                        'confidence': result.get('score', 0.0),
                    }
                }
                
                # Add file metadata
                if 'chunk_metadata' in result:
                    formatted_item['file_metadata'] = result['chunk_metadata']
                
                formatted.append(formatted_item)
        
        return formatted
    
    async def index_file_chunks(self, file_id: str, chunks: List, collection_name: str) -> bool:
        """
        Index file chunks into vector store.
        
        Args:
            file_id: File identifier
            chunks: List of Chunk objects
            collection_name: Collection name
            
        Returns:
            True if successful
        """
        if not self._default_store or not chunks:
            return False
        
        try:
            # Generate embeddings for chunks
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = []
            
            for text in chunk_texts:
                embedding = await self.embed_query(text)
                embeddings.append(embedding)
            
            # Prepare data for vector store
            ids = [chunk.chunk_id for chunk in chunks]
            metadata = []
            
            for chunk in chunks:
                metadata.append({
                    'file_id': file_id,
                    'chunk_index': chunk.chunk_index,
                    **chunk.metadata
                })
            
            # Add to vector store with chunk texts as documents
            success = await self._default_store.add_vectors(
                vectors=embeddings,
                ids=ids,
                metadata=metadata,
                collection_name=collection_name,
                documents=chunk_texts  # Pass chunk texts as documents for ChromaDB
            )
            
            # Note: Chunks are already recorded in FileProcessingService.process_file()
            # before indexing, so we don't need to record them again here.
            # This method only handles the vector store indexing.
            
            return success
        
        except Exception as e:
            logger.error(f"Error indexing file chunks: {e}")
            return False
    
    async def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific chunk by ID."""
        # This would query the vector store for a specific chunk
        # For now, return None as this requires vector store ID lookup
        return None
    
    async def delete_file_chunks(self, file_id: str) -> bool:
        """Delete all chunks for a file."""
        try:
            # Get file info
            file_info = await self.metadata_store.get_file_info(file_id)
            if not file_info:
                return False
            
            collection_name = file_info.get('collection_name')
            if collection_name and self._default_store:
                # Get all chunks for file
                chunks = await self.metadata_store.get_file_chunks(file_id)
                
                # Delete from vector store
                chunk_ids = [c['chunk_id'] for c in chunks]
                # Note: Vector store deletion would need to be implemented
            
            # Delete from metadata store
            return await self.metadata_store.delete_file_chunks(file_id)
        
        except Exception as e:
            logger.error(f"Error deleting file chunks: {e}")
            return False
    
    # Implement abstract methods required by AbstractVectorRetriever
    
    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return "file"
    
    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search.
        
        This method is required by AbstractVectorRetriever but FileVectorRetriever
        uses a different search pattern via _search_collection. This is a stub implementation.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        # FileVectorRetriever uses collection-based search via get_relevant_context
        # This is called from parent's get_relevant_context, but we override it
        # So this method should not be called in normal operation
        logger.warning("vector_search called on FileVectorRetriever - this should use get_relevant_context instead")
        return []
    
    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        # FileVectorRetriever handles collections dynamically in _get_collections
        # No need to set a single collection
        pass
    
    async def initialize_client(self) -> None:
        """Initialize the vector database client/connection."""
        # FileVectorRetriever uses StoreManager which is initialized in initialize()
        # This is called from parent but we handle it differently
        # Don't call initialize() here to avoid double initialization
        pass
    
    async def close_client(self) -> None:
        """Close the vector database client/connection."""
        # FileVectorRetriever doesn't maintain a persistent client connection
        # The store manager handles its own lifecycle
        pass
