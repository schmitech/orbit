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
from vector_stores.store_manager import StoreManager

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
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # File-specific configuration
        self.metadata_store = FileMetadataStore()
        self.collection_prefix = self.config.get('collection_prefix', 'files_')
        
        # Initialize store manager for vector operations
        self.store_manager = None
        self._default_store = None
    
    async def initialize(self):
        """Initialize the retriever."""
        if self.initialized:
            return
        
        # Initialize embeddings
        await super().initialize()
        
        # Initialize store manager
        self.store_manager = StoreManager()
        
        # Get default vector store
        vector_store_name = self.config.get('vector_store', 'chroma')
        self._default_store = await self.store_manager.get_store(vector_store_name)
        
        if not self._default_store:
            logger.error(f"Could not initialize vector store: {vector_store_name}")
        
        self.initialized = True
        logger.info("FileVectorRetriever initialized")
    
    async def get_relevant_context(self, query: str, api_key: Optional[str] = None, 
                                  file_id: Optional[str] = None,
                                  collection_name: Optional[str] = None,
                                  **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from uploaded files.
        
        Args:
            query: User query
            api_key: API key for filtering
            file_id: Optional specific file to query
            collection_name: Optional specific collection
            
        Returns:
            List of relevant context items
        """
        await self.ensure_initialized()
        
        # Generate query embedding
        query_embedding = await self.embed_query(query)
        
        # Determine collections to search
        collections = await self._get_collections(file_id, api_key, collection_name)
        
        # Search across collections
        results = []
        for collection in collections:
            collection_results = await self._search_collection(
                collection,
                query_embedding,
                file_id=file_id
            )
            results.extend(collection_results)
        
        # Apply domain filtering
        results = self.apply_domain_filtering(results, query)
        
        # Group and format results
        formatted_results = self._format_results(results)
        
        return formatted_results
    
    async def _get_collections(self, file_id: Optional[str], api_key: Optional[str],
                              collection_name: Optional[str]) -> List[str]:
        """Get list of collections to search."""
        if collection_name:
            return [collection_name]
        
        if file_id:
            # Get file info to find its collection
            file_info = await self.metadata_store.get_file_info(file_id)
            if file_info and file_info.get('collection_name'):
                return [file_info['collection_name']]
        
        # Get all collections for API key
        if api_key:
            files = await self.metadata_store.list_files(api_key)
            collections = {f['collection_name'] for f in files if f.get('collection_name')}
            return list(collections)
        
        return []
    
    async def _search_collection(self, collection_name: str, query_embedding: List[float],
                                 file_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search a specific collection for relevant chunks."""
        if not self._default_store:
            return []
        
        try:
            # Build metadata filter
            filter_metadata = {}
            if file_id:
                filter_metadata['file_id'] = file_id
            
            # Search vector store
            results = await self._default_store.search_vectors(
                query_vector=query_embedding,
                limit=limit,
                collection_name=collection_name,
                filter_metadata=filter_metadata
            )
            
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
                    'content': result.get('text', ''),
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
            
            # Add to vector store
            success = await self._default_store.add_vectors(
                vectors=embeddings,
                ids=ids,
                metadata=metadata,
                collection_name=collection_name
            )
            
            if success:
                # Record chunks in metadata store
                for chunk in chunks:
                    await self.metadata_store.record_chunk(
                        chunk_id=chunk.chunk_id,
                        file_id=file_id,
                        chunk_index=chunk.chunk_index,
                        collection_name=collection_name,
                        metadata=chunk.metadata
                    )
            
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
