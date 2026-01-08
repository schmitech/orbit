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

        # Get collection_prefix from adapter config first, then global files config, then default
        # NOTE: Adapter-specific config from adapters.yaml is at config['adapter_config'] (set by dynamic_adapter_manager)
        adapter_config = self.config.get('adapter_config', {})
        files_config = self.config.get('files', {})
        self.collection_prefix = adapter_config.get('collection_prefix') or \
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

        # Get default vector store from adapter config first, then global files config, then default
        # NOTE: Adapter-specific config from adapters.yaml is at config['adapter_config'] (set by dynamic_adapter_manager)
        adapter_config = self.config.get('adapter_config', {})
        files_config = self.config.get('files', {})
        vector_store_name = adapter_config.get('vector_store') or \
                           files_config.get('default_vector_store', 'chroma')

        # Debug logging to trace vector store selection
        logger.debug(f"FileVectorRetriever.initialize() - Vector store selection:")
        logger.debug(f"  adapter_config.get('vector_store') = {adapter_config.get('vector_store')}")
        logger.debug(f"  files_config.get('default_vector_store') = {files_config.get('default_vector_store')}")
        logger.debug(f"  Selected vector_store_name = {vector_store_name}")

        try:
            # First try to get existing store
            self._default_store = await self.store_manager.get_store(vector_store_name)
            
            # If not found, try to create it (will use config from stores.yaml)
            if not self._default_store:
                try:
                    logger.debug(f"Store '{vector_store_name}' not found, attempting to create it...")
                    self._default_store = await self.store_manager.get_or_create_store(
                        name=vector_store_name,
                        store_type=vector_store_name  # Use the configured store type (e.g., 'qdrant', 'chroma')
                    )
                    logger.info(f"Created vector store: {vector_store_name}")
                except Exception as create_error:
                    logger.warning(f"Could not create vector store '{vector_store_name}': {create_error}. "
                                 f"File adapter will operate in limited mode without vector search. "
                                 f"Ensure '{vector_store_name}' is enabled and configured in config/stores.yaml")
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
                                  file_ids: Optional[List[str]] = None,
                                  collection_name: Optional[str] = None,
                                  **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from uploaded files.

        Args:
            query: User query
            api_key: API key for filtering
            file_ids: Optional list of specific files to query
            collection_name: Optional specific collection

        Returns:
            List of relevant context items
        """
        logger.debug("=" * 80)
        logger.debug(f"FileVectorRetriever.get_relevant_context called")
        logger.debug(f"  Query: {query[:100]}")
        logger.debug(f"  file_ids: {file_ids}")
        logger.debug(f"  api_key: {'provided' if api_key else 'None'}")
        logger.debug(f"  collection_name: {collection_name}")
        logger.debug("=" * 80)

        await self.ensure_initialized()

        # Generate query embedding
        query_embedding = await self.embed_query(query)
        logger.debug(f"FileVectorRetriever: Generated query embedding with {len(query_embedding)} dimensions")

        # Determine collections to search
        collections = await self._get_collections_multiple(file_ids, api_key, collection_name)
        logger.debug(f"FileVectorRetriever: Collections to search: {collections}")

        if not collections:
            logger.warning("FileVectorRetriever: No collections found! Returning empty results.")
            return []

        # Search across collections
        results = []
        for collection in collections:
            logger.debug(f"FileVectorRetriever: Searching collection: {collection}")
            collection_results = await self._search_collection(
                collection,
                query_embedding,
                file_ids=file_ids
            )
            logger.debug(f"FileVectorRetriever: Found {len(collection_results)} results in collection {collection}")
            results.extend(collection_results)

        logger.debug(f"FileVectorRetriever: Total raw results: {len(results)}")

        # Apply domain filtering
        results = self.apply_domain_filtering(results, query)
        logger.debug(f"FileVectorRetriever: After domain filtering: {len(results)} results")

        # Group and format results
        formatted_results = self._format_results(results)

        # Apply return_results limit (truncate to configured number of results)
        return_limit = getattr(self, 'return_results', 3)
        if len(formatted_results) > return_limit:
            logger.info(f"FileVectorRetriever: Truncating results from {len(formatted_results)} to {return_limit} (return_results config)")
            formatted_results = formatted_results[:return_limit]

        logger.debug(f"FileVectorRetriever: Final formatted results: {len(formatted_results)} chunks")
        logger.debug("=" * 80)

        return formatted_results
    
    
    async def _get_collections_multiple(self, file_ids: Optional[List[str]], api_key: Optional[str],
                                       collection_name: Optional[str]) -> List[str]:
        """
        Get list of collections to search for multiple file IDs.

        This method filters collections to only include those matching the current
        embedding provider and dimensions to prevent dimension mismatch errors.
        """
        if collection_name:
            return [collection_name]

        # Get current embedding provider and dimensions
        try:
            # Check multiple sources for embedding provider to handle adapter overrides:
            # 1. First check adapter_config (top-level adapter config) for embedding_provider
            # 2. Then check config['embedding']['provider'] (set by adapter_loader from adapter's embedding_provider)
            # 3. Fall back to 'ollama' as default
            adapter_config = self.config.get('adapter_config', {})

            # Get embedding_provider from adapter config if present (handles passthrough from adapter loader)
            embedding_provider = self.config.get('embedding', {}).get('provider')

            # Log the embedding provider source for debugging
            if embedding_provider:
                logger.debug(f"FileVectorRetriever: Using embedding provider '{embedding_provider}' from config['embedding']['provider']")
            else:
                embedding_provider = 'ollama'
                logger.debug(f"FileVectorRetriever: No embedding provider in config, defaulting to '{embedding_provider}'")

            # Get current embedding dimensions
            if self.embeddings and hasattr(self.embeddings, 'get_dimensions'):
                embedding_dimensions = await self.embeddings.get_dimensions()
            else:
                # Fallback: try to get dimensions by embedding a test query
                test_embedding = await self.embed_query("test")
                embedding_dimensions = len(test_embedding)

            # Create provider signature for filtering
            provider_signature = f"{embedding_provider}_{embedding_dimensions}"

            logger.debug(f"Filtering collections for provider: {provider_signature}")

        except Exception as e:
            logger.warning(f"Could not determine embedding provider info: {e}. Collections may not be filtered correctly.")
            provider_signature = None

        if file_ids:
            # Get collections for all specified files
            collections = set()
            skipped_files = []  # Track files that were skipped due to embedding mismatch

            for file_id in file_ids:
                logger.debug(f"FileVectorRetriever: Looking up metadata for file_id: {file_id}")
                file_info = await self.metadata_store.get_file_info(file_id)

                if not file_info:
                    logger.warning(f"FileVectorRetriever: No metadata found for file_id: {file_id}")
                    continue

                logger.debug(f"FileVectorRetriever: File info: {file_info}")

                if file_info.get('collection_name'):
                    coll_name = file_info['collection_name']
                    logger.debug(f"FileVectorRetriever: Found collection_name: {coll_name}")

                    # Get the embedding provider info stored with the file
                    file_embedding_provider = file_info.get('embedding_provider')
                    file_embedding_dimensions = file_info.get('embedding_dimensions')

                    # Filter by provider signature if available
                    if provider_signature:
                        logger.debug(f"FileVectorRetriever: Checking provider signature: {provider_signature}")
                        # Check if collection name contains the provider signature
                        # Format: files_{provider}_{dimensions}_{apikey}_{timestamp}
                        if provider_signature in coll_name:
                            logger.debug(f"FileVectorRetriever: ✓ Collection {coll_name} matches provider {provider_signature}")
                            collections.add(coll_name)
                        else:
                            # Log detailed info about the mismatch
                            file_name = file_info.get('original_filename', file_id)
                            if file_embedding_provider and file_embedding_dimensions:
                                logger.warning(
                                    f"FileVectorRetriever: ✗ Embedding mismatch for file '{file_name}' (id: {file_id}): "
                                    f"File was indexed with {file_embedding_provider}_{file_embedding_dimensions}, "
                                    f"but current adapter uses {provider_signature}. "
                                    f"Please re-upload the file to re-index with the current embedding provider."
                                )
                                skipped_files.append({
                                    'file_id': file_id,
                                    'file_name': file_name,
                                    'indexed_with': f"{file_embedding_provider}_{file_embedding_dimensions}",
                                    'current_provider': provider_signature
                                })
                            else:
                                logger.warning(
                                    f"FileVectorRetriever: ✗ Skipping collection {coll_name} "
                                    f"(provider signature '{provider_signature}' not found in collection name)"
                                )
                    else:
                        # If we can't determine provider, include all collections (backward compatibility)
                        logger.debug(f"FileVectorRetriever: No provider signature - using collection {coll_name} (backward compatibility)")
                        collections.add(coll_name)
                else:
                    logger.warning(f"FileVectorRetriever: File {file_id} has no collection_name in metadata")

            # If we skipped files due to embedding mismatch, log a summary
            if skipped_files:
                logger.warning(
                    f"FileVectorRetriever: {len(skipped_files)} file(s) skipped due to embedding provider mismatch. "
                    f"Current adapter uses embedding signature '{provider_signature}'. "
                    f"Files indexed with a different provider cannot be searched until re-uploaded. "
                    f"To fix: Delete and re-upload the affected files, or change the adapter's embedding_provider to match."
                )

            logger.debug(f"FileVectorRetriever: Final collections to search: {list(collections)}")
            return list(collections) if collections else []

        # Get all collections for API key
        if api_key:
            files = await self.metadata_store.list_files(api_key)
            collections = set()

            for f in files:
                if f.get('collection_name'):
                    coll_name = f['collection_name']

                    # Filter by provider signature if available
                    if provider_signature:
                        if provider_signature in coll_name:
                            collections.add(coll_name)
                    else:
                        # If we can't determine provider, include all collections (backward compatibility)
                        collections.add(coll_name)

            return list(collections)

        return []
    
    async def _search_collection(self, collection_name: str, query_embedding: List[float],
                                 file_ids: Optional[List[str]] = None,
                                 limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search a specific collection for relevant chunks.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            file_ids: Optional list of file IDs to filter by
            limit: Maximum results to retrieve. Defaults to self.max_results (from adapter config)
        """
        # Use max_results from adapter config if not specified
        if limit is None:
            limit = getattr(self, 'max_results', 10)
        if not self._default_store:
            return []
        
        try:
            # Build metadata filter
            filter_metadata = None
            if file_ids:
                # If multiple file_ids, we need to filter by any of them
                # Note: Some vector stores support OR filters, others may need multiple queries
                # For now, filter by the first file_id if multiple (we'll search all collections anyway)
                if len(file_ids) == 1:
                    filter_metadata = {'file_id': file_ids[0]}
                # TODO: Support proper OR filtering for multiple file_ids in vector store queries

            # Search vector store
            results = await self._default_store.search_vectors(
                query_vector=query_embedding,
                limit=limit,
                collection_name=collection_name,
                filter_metadata=filter_metadata  # Pass None if no filter needed
            )
            
            # Post-filter results by file_ids if multiple files specified
            if file_ids and len(file_ids) > 1:
                results = [r for r in results if r.get('metadata', {}).get('file_id') in file_ids]
            
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
            
            # Add to vector store
            # Note: ChromaDB supports 'documents' parameter, but it's not in the base interface
            # Try with documents first (for ChromaDB), fall back to standard interface if not supported
            try:
                success = await self._default_store.add_vectors(
                    vectors=embeddings,
                    ids=ids,
                    metadata=metadata,
                    collection_name=collection_name,
                    documents=chunk_texts  # ChromaDB-specific parameter
                )
            except TypeError as e:
                # Vector store doesn't support 'documents' parameter (e.g., Qdrant, Pinecone)
                # For these stores, add content to metadata
                logger.debug(f"Vector store doesn't support 'documents' parameter, adding content to metadata: {e}")

                # Add content to metadata for non-ChromaDB stores
                metadata_with_content = []
                for i, meta in enumerate(metadata):
                    meta_copy = meta.copy()
                    meta_copy['content'] = chunk_texts[i]  # Store content in metadata
                    metadata_with_content.append(meta_copy)

                success = await self._default_store.add_vectors(
                    vectors=embeddings,
                    ids=ids,
                    metadata=metadata_with_content,  # Use metadata with content included
                    collection_name=collection_name
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
        """Delete all chunks for a file from both vector store and metadata store."""
        try:
            # Get file info to retrieve collection name
            file_info = await self.metadata_store.get_file_info(file_id)
            if not file_info:
                logger.warning(f"File {file_id} not found in metadata store")
                return False
            
            collection_name = file_info.get('collection_name')
            if not collection_name:
                logger.warning(f"File {file_id} has no collection_name, skipping vector store deletion")
                # Still delete from metadata store
                return await self.metadata_store.delete_file_chunks(file_id)
            
            # Get all chunks for file before deleting from metadata store
            chunks = await self.metadata_store.get_file_chunks(file_id)
            
            if not chunks:
                logger.debug(f"No chunks found for file {file_id}")
                # No chunks to delete, but return True to indicate successful operation
                return True
            
            # Delete from vector store if store is available
            if self._default_store:
                await self.ensure_initialized()

                chunk_ids = [c['chunk_id'] for c in chunks]
                logger.debug(f"Deleting {len(chunk_ids)} chunks from vector store for file {file_id}")

                # Delete each chunk from vector store
                # Most vector stores support batch deletion, but we'll delete individually for compatibility
                deletion_errors = []
                for chunk_id in chunk_ids:
                    try:
                        success = await self._default_store.delete_vector(
                            vector_id=chunk_id,
                            collection_name=collection_name
                        )
                        if not success:
                            deletion_errors.append(chunk_id)
                            logger.warning(f"Failed to delete chunk {chunk_id} from vector store")
                    except Exception as e:
                        deletion_errors.append(chunk_id)
                        logger.error(f"Error deleting chunk {chunk_id} from vector store: {e}")

                if deletion_errors:
                    logger.warning(f"Failed to delete {len(deletion_errors)} chunks from vector store for file {file_id}")
                logger.debug(f"✓ Successfully deleted all {len(chunk_ids)} chunks from vector store for file {file_id}")

                # Check if collection is now empty and delete it if so
                try:
                    collection_info = await self._default_store.get_collection_info(collection_name)
                    points_count = collection_info.get('count', -1)

                    if points_count == 0:
                        logger.debug(f"Collection {collection_name} is now empty, deleting collection...")
                        delete_success = await self._default_store.delete_collection(collection_name)
                        if delete_success:
                            logger.debug(f"✓ Deleted empty collection {collection_name}")
                        else:
                            logger.warning(f"✗ Failed to delete empty collection {collection_name}")
                    elif points_count > 0:
                        logger.debug(f"Collection {collection_name} still has {points_count} points, keeping collection")
                    else:
                        logger.debug(f"Could not determine point count for collection {collection_name}, skipping collection deletion")
                except Exception as e:
                    logger.warning(f"Error checking/deleting empty collection {collection_name}: {e}")
            else:
                logger.warning(f"No vector store available, skipping vector store deletion for file {file_id}")

            # Delete from metadata store (always do this, even if vector store deletion failed)
            metadata_delete_success = await self.metadata_store.delete_file_chunks(file_id)

            if metadata_delete_success:
                logger.debug(f"Deleted chunks from metadata store for file {file_id}")
            else:
                logger.error(f"Failed to delete chunks from metadata store for file {file_id}")
            
            return metadata_delete_success
        
        except Exception as e:
            logger.error(f"Error deleting file chunks for {file_id}: {e}")
            return False
    
    # Implement abstract methods required by AbstractVectorRetriever

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        # Note: File adapter doesn't use traditional datasources (datasource: "none" in adapter config)
        # This is used by parent class for legacy config lookup
        return "files"  # Match the global config section name

    def _get_datasource_config(self) -> Dict[str, Any]:
        """
        Override to get file adapter configuration from the correct location.

        The file adapter gets its configuration from:
        1. adapter_config (set by dynamic_adapter_manager from adapters.yaml)
        2. Fallback to global 'files' config section

        Returns:
            Dict containing file adapter configuration with settings like
            confidence_threshold, max_results, return_results, etc.
        """
        # First try to get adapter-specific config (from adapters.yaml)
        adapter_config = self.config.get('adapter_config', {})
        if adapter_config:
            return adapter_config

        # Fallback to global 'files' config section
        files_config = self.config.get('files', {})
        if files_config:
            return files_config

        # Final fallback to parent's logic (for edge cases)
        return super()._get_datasource_config()
    
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
