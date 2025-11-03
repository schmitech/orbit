"""
File Processing Service

Main service for processing uploaded files: extraction, chunking, and storage preparation.
"""

import logging
import uuid
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC

from services.file_processing.processor_registry import FileProcessorRegistry
from services.file_processing.chunking import FixedSizeChunker, SemanticChunker, Chunk
from services.file_storage.filesystem_storage import FilesystemStorage
from services.file_metadata.metadata_store import FileMetadataStore

logger = logging.getLogger(__name__)


class FileProcessingService:
    """
    Main service for file processing pipeline.
    
    Handles:
    - File type detection
    - Text extraction
    - Chunking
    - Storage preparation
    - Metadata tracking
    """
    
    def __init__(self, config: Dict[str, Any], app_state=None):
        """
        Initialize file processing service.

        Args:
            config: Configuration dictionary
            app_state: Optional FastAPI app state for accessing services (e.g., dynamic_adapter_manager)
        """
        self.config = config
        self.app_state = app_state
        self.logger = logging.getLogger(self.__class__.__name__)

        # Get files configuration section
        files_config = config.get('files', {})
        processing_config = files_config.get('processing', {})

        # Initialize components
        self.storage = self._init_storage()
        self.metadata_store = FileMetadataStore(config=config)
        self.processor_registry = FileProcessorRegistry()
        self.chunker = self._init_chunker()

        # Configuration - get from adapter config first, then files.processing, then default
        self.max_file_size = config.get('max_file_size') or \
                             processing_config.get('max_file_size', 52428800)  # 50MB
        self.supported_types = config.get('supported_types') or \
                              processing_config.get('supported_types', [
            'application/pdf',
            'text/plain',
            'text/markdown',
            'text/csv',
            'application/json',
            'text/html',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
            # Image types
            'image/png',
            'image/jpeg',
            'image/jpg',
            'image/gif',
            'image/bmp',
            'image/tiff',
            'image/webp',
        ])

        # Vision service configuration - follows same pattern as embeddings/inference
        # Priority: adapter config > global vision config > default
        # NOTE: Default vision provider is set here, but can be overridden per-file based on API key's adapter
        vision_config = config.get('vision', {})

        # Enable/disable vision processing
        # Priority: adapter config > global vision config > default True
        self.enable_vision = config.get('enable_vision', vision_config.get('enabled', True))

        # Get DEFAULT vision provider (can be overridden per-upload based on adapter)
        # Priority: adapter config > global vision config > default
        self.default_vision_provider = config.get('vision_provider', vision_config.get('provider', 'gemini'))

        # Get provider-specific configs from 'visions' section (plural, like 'embeddings', 'inferences')
        self.vision_config = config.get('visions', {})

        # Log default vision configuration
        if self.enable_vision:
            provider_config = self.vision_config.get(self.default_vision_provider, {})
            model = provider_config.get('model', 'default')
            self.logger.info(f"Default vision service configured: provider={self.default_vision_provider}, model={model}")
            self.logger.info("Vision provider can be overridden per-upload based on API key's adapter configuration")
    
    def _init_storage(self) -> FilesystemStorage:
        """Initialize storage backend."""
        # Get from adapter config first, then global files config, then default
        storage_root = self.config.get('storage_root') or \
                      self.config.get('files', {}).get('storage_root', './uploads')
        return FilesystemStorage(storage_root=storage_root)
    
    def _init_chunker(self):
        """Initialize chunking strategy."""
        # Get from adapter config first, then global files config, then defaults
        files_config = self.config.get('files', {})
        strategy = self.config.get('chunking_strategy') or \
                  files_config.get('default_chunking_strategy', 'fixed')
        chunk_size = self.config.get('chunk_size') or \
                    files_config.get('default_chunk_size', 1000)
        overlap = self.config.get('chunk_overlap') or \
                 files_config.get('default_chunk_overlap', 200)
        
        if strategy == 'semantic':
            return SemanticChunker(chunk_size=chunk_size, overlap=overlap)
        else:
            return FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)

    async def _get_vision_provider_for_api_key(self, api_key: str) -> str:
        """
        Get the vision provider for a given API key by looking up its adapter configuration.

        This enables adapter-specific vision provider overrides (e.g., adapter A uses OpenAI, adapter B uses Gemini).

        Args:
            api_key: The API key to lookup

        Returns:
            Vision provider name (e.g., 'openai', 'gemini', 'anthropic')
        """
        try:
            # Try to get adapter manager from app state
            if self.app_state and hasattr(self.app_state, 'dynamic_adapter_manager'):
                adapter_manager = self.app_state.dynamic_adapter_manager

                # Get API key service to lookup which adapter this API key uses
                if hasattr(self.app_state, 'api_key_service'):
                    api_key_service = self.app_state.api_key_service

                    # Get adapter name for this API key
                    adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key)

                    if adapter_name:
                        # Get adapter config from adapter manager
                        adapter_config = adapter_manager.get_adapter_config(adapter_name)

                        if adapter_config:
                            # Check if adapter has vision_provider override
                            vision_provider = adapter_config.get('vision_provider')

                            if vision_provider:
                                self.logger.info(f"Using adapter-specific vision provider '{vision_provider}' for adapter '{adapter_name}' (api_key: {api_key[:8]}...)")
                                return vision_provider

        except Exception as e:
            self.logger.warning(f"Could not lookup adapter-specific vision provider for API key: {e}")

        # Fall back to default vision provider
        self.logger.debug(f"Using default vision provider '{self.default_vision_provider}' for api_key: {api_key[:8]}...")
        return self.default_vision_provider

    async def quick_upload(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str
    ) -> str:
        """
        Quick file upload - stores file and returns file_id immediately.
        Content processing happens in background via process_file_content.
        
        Args:
            file_data: File contents as bytes
            filename: Original filename
            mime_type: MIME type
            api_key: API key of uploader
            
        Returns:
            file_id: Unique file identifier
        """
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        # Validate file
        if not self._validate_file(file_data, mime_type):
            raise ValueError(f"Unsupported file type: {mime_type}")
        
        # Store file
        storage_key = f"{api_key}/{file_id}/{filename}"
        metadata = {
            'filename': filename,
            'mime_type': mime_type,
            'file_size': len(file_data),
            'upload_time': datetime.now(UTC).isoformat(),
        }
        
        await self.storage.put_file(file_data, storage_key, metadata)
        
        # Record in metadata store with status 'processing'
        await self.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=filename,
            mime_type=mime_type,
            file_size=len(file_data),
            storage_key=storage_key,
            storage_type='vector',
            metadata=metadata,
        )
        
        # Set status to processing
        await self.metadata_store.update_processing_status(file_id, 'processing')
        
        return file_id
    
    async def process_file_content(
        self,
        file_id: str,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> None:
        """
        Process file content (extraction, chunking, indexing) in background.
        Called after quick_upload for async processing.
        
        Args:
            file_id: File identifier from quick_upload
            file_data: File contents as bytes
            filename: Original filename
            mime_type: MIME type
            api_key: API key of uploader
        """
        try:
            # Extract text and metadata
            extracted_text, file_metadata = await self._extract_content(
                file_data, filename, mime_type, api_key=api_key, vision_prompt=vision_prompt
            )

            # Chunk content
            chunks = await self._chunk_content(extracted_text, file_id, file_metadata)

            # Index chunks into vector store
            index_result = await self._index_chunks_in_vector_store(
                file_id=file_id,
                api_key=api_key,
                chunks=chunks
            )

            # Extract collection info
            collection_name = None
            embedding_provider = None
            embedding_dimensions = None
            if index_result:
                collection_name, embedding_provider, embedding_dimensions = index_result

            # Record chunks in metadata store (with collection name)
            for chunk in chunks:
                await self.metadata_store.record_chunk(
                    chunk_id=chunk.chunk_id,
                    file_id=file_id,
                    chunk_index=chunk.chunk_index,
                    vector_store_id=chunk.chunk_id,
                    collection_name=collection_name,
                    metadata=chunk.metadata
                )

            # Update metadata store with chunk count, collection name, and provider info
            await self.metadata_store.update_processing_status(
                file_id,
                'completed',
                chunk_count=len(chunks),
                collection_name=collection_name,
                embedding_provider=embedding_provider,
                embedding_dimensions=embedding_dimensions
            )
            
            self.logger.info(f"File content processed successfully: {file_id} ({len(chunks)} chunks)")
            
        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Error processing file content for {file_id}: {error_message}")

            # Update status to failed with error details
            await self.metadata_store.update_processing_status(
                file_id,
                'failed',
                chunk_count=0
            )

            # Store error message in file metadata for user feedback
            try:
                cursor = self.metadata_store.connection.cursor()
                cursor.execute(
                    "UPDATE uploaded_files SET metadata = ? WHERE file_id = ?",
                    (json.dumps({'error': error_message, 'failed_at': datetime.now(UTC).isoformat()}), file_id)
                )
                self.metadata_store.connection.commit()
            except Exception as meta_error:
                self.logger.warning(f"Failed to store error metadata for {file_id}: {meta_error}")

            # Don't raise - let background task complete gracefully
            # The file is now marked as "failed" so users can see the error
    
    async def process_file(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str
    ) -> Dict[str, Any]:
        """
        Process an uploaded file through the complete pipeline.
        
        Args:
            file_data: File contents as bytes
            filename: Original filename
            mime_type: MIME type
            api_key: API key of uploader
            
        Returns:
            Processing result with file_id and status
        """
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        try:
            # 1. Validate file
            if not self._validate_file(file_data, mime_type):
                raise ValueError(f"Unsupported file type: {mime_type}")
            
            # 2. Store file
            storage_key = f"{api_key}/{file_id}/{filename}"
            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'upload_time': datetime.now(UTC).isoformat(),
            }
            
            await self.storage.put_file(file_data, storage_key, metadata)
            
            # 3. Record in metadata store
            await self.metadata_store.record_file_upload(
                file_id=file_id,
                api_key=api_key,
                filename=filename,
                mime_type=mime_type,
                file_size=len(file_data),
                storage_key=storage_key,
                storage_type='vector',
                metadata=metadata,
            )
            
            # 4. Update status to processing
            await self.metadata_store.update_processing_status(file_id, 'processing')

            # 5. Extract text and metadata
            extracted_text, file_metadata = await self._extract_content(
                file_data, filename, mime_type, api_key=api_key
            )

            # 6. Chunk content
            chunks = await self._chunk_content(extracted_text, file_id, file_metadata)

            # 7. Index chunks into vector store
            index_result = await self._index_chunks_in_vector_store(
                file_id=file_id,
                api_key=api_key,
                chunks=chunks
            )

            # Extract collection info
            collection_name = None
            embedding_provider = None
            embedding_dimensions = None
            if index_result:
                collection_name, embedding_provider, embedding_dimensions = index_result

            # 8. Record chunks in metadata store (with collection name)
            for chunk in chunks:
                await self.metadata_store.record_chunk(
                    chunk_id=chunk.chunk_id,
                    file_id=file_id,
                    chunk_index=chunk.chunk_index,
                    vector_store_id=chunk.chunk_id,  # Use chunk_id as vector_store_id
                    collection_name=collection_name,
                    metadata=chunk.metadata
                )

            # 9. Update metadata store with chunk count, collection name, and provider info
            await self.metadata_store.update_processing_status(
                file_id,
                'completed',
                chunk_count=len(chunks),
                collection_name=collection_name,
                embedding_provider=embedding_provider,
                embedding_dimensions=embedding_dimensions
            )
            
            # 10. Prepare response
            return {
                'file_id': file_id,
                'status': 'completed',
                'chunk_count': len(chunks),
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'collection_name': collection_name,
                'chunks': chunks,
                'metadata': file_metadata,
            }
        
        except Exception as e:
            self.logger.error(f"Error processing file {filename}: {e}")
            
            # Update status to failed
            await self.metadata_store.update_processing_status(file_id, 'failed')
            
            raise
    
    def _validate_file(self, file_data: bytes, mime_type: str) -> bool:
        """Validate file size and type."""
        # Check size
        if len(file_data) > self.max_file_size:
            raise ValueError(f"File size exceeds maximum {self.max_file_size} bytes")
        
        # Check MIME type
        if mime_type not in self.supported_types:
            return False
        
        # Check if processor exists
        processor = self.processor_registry.get_processor(mime_type)
        return processor is not None
    
    async def _extract_content(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """Extract text and metadata from file."""
        # Check if this is an image file
        if self.enable_vision and mime_type.startswith('image/'):
            return await self._extract_image_content(
                file_data, filename, mime_type, api_key=api_key, vision_prompt=vision_prompt
            )

        processor = self.processor_registry.get_processor(mime_type)

        if not processor:
            raise ValueError(f"No processor available for MIME type: {mime_type}")

        text = await processor.extract_text(file_data, filename)
        metadata = await processor.extract_metadata(file_data, filename)

        return text, metadata
    
    async def _extract_image_content(
        self,
        file_data: bytes,
        filename: str,
        mime_type: str,
        api_key: str,
        vision_prompt: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """Extract content from image using vision services."""
        import asyncio
        from ai_services import AIServiceFactory, ServiceType

        try:
            # Get adapter-specific vision provider (or fallback to default)
            vision_provider = await self._get_vision_provider_for_api_key(api_key)

            # Get vision service
            vision_service = AIServiceFactory.create_service(
                ServiceType.VISION,
                vision_provider,
                {'vision': self.vision_config}
            )

            # Initialize if needed
            if not vision_service.initialized:
                await vision_service.initialize()

            # PERFORMANCE FIX: Make both API calls concurrently instead of sequentially
            # This reduces total processing time from ~120s to ~60s
            self.logger.info(f"Starting vision processing for {filename} (provider: {vision_provider})")

            # Use custom prompt if provided, otherwise use default describe_image
            try:
                if vision_prompt:
                    self.logger.info(f"Using custom prompt for vision analysis: {vision_prompt[:50]}...")
                    # Use analyze_image with custom prompt instead of describe_image
                    extracted_text, description = await asyncio.gather(
                        vision_service.extract_text_from_image(file_data),
                        vision_service.analyze_image(file_data, prompt=vision_prompt)
                    )
                else:
                    extracted_text, description = await asyncio.gather(
                        vision_service.extract_text_from_image(file_data),
                        vision_service.describe_image(file_data)
                    )
            except asyncio.TimeoutError as e:
                self.logger.error(f"Vision API timeout for {filename}: {e}")
                raise Exception(f"Vision API request timed out. The image may be too large or the API is experiencing latency. Please try again or contact support if the issue persists.")
            except Exception as e:
                self.logger.error(f"Vision API error for {filename}: {e}")
                raise Exception(f"Vision processing failed: {str(e)}")

            self.logger.info(f"Vision processing completed for {filename}")

            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'extraction_method': 'vision',
                'vision_provider': vision_provider,
                'image_description': description,
                'image_text': extracted_text,
            }

            # Combine description and extracted text
            text = f"Image Description:\n{description}\n\nExtracted Text:\n{extracted_text}"

            # Validate that we got meaningful content
            if not text.strip() or (not description and not extracted_text):
                self.logger.warning(f"Vision service returned empty content for {filename}")
                raise Exception("Vision service did not extract any content from the image")

            return text, metadata

        except Exception as e:
            # PRODUCTION FIX: Don't swallow exceptions - let them bubble up
            # This ensures files are marked as "failed" instead of "completed with 0 chunks"
            self.logger.error(f"Failed to process image {filename}: {e}")
            raise
    
    async def _chunk_content(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """Chunk text content."""
        return self.chunker.chunk_text(text, file_id, metadata)
    
    async def _get_adapter_config_for_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Get the adapter configuration for a given API key.

        This enables adapter-specific provider overrides (e.g., adapter A uses OpenAI, adapter B uses Ollama).

        Args:
            api_key: The API key to lookup

        Returns:
            Dict containing adapter config merged with global config, or just global config as fallback
        """
        try:
            # Try to get adapter manager from app state
            if self.app_state and hasattr(self.app_state, 'dynamic_adapter_manager'):
                adapter_manager = self.app_state.dynamic_adapter_manager

                # Get API key service to lookup which adapter this API key uses
                if hasattr(self.app_state, 'api_key_service'):
                    api_key_service = self.app_state.api_key_service

                    # Get adapter name for this API key
                    adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key)

                    if adapter_name:
                        # Get adapter config from adapter manager
                        adapter_config = adapter_manager.get_adapter_config(adapter_name)

                        if adapter_config:
                            self.logger.info(f"Using adapter-specific config for adapter '{adapter_name}' (api_key: {api_key[:8]}...)")

                            # Merge adapter config with global config
                            # Adapter config takes precedence for provider overrides
                            merged_config = self.config.copy()

                            # Override embedding provider if specified in adapter
                            if 'embedding_provider' in adapter_config:
                                if 'embedding' not in merged_config:
                                    merged_config['embedding'] = {}
                                merged_config['embedding']['provider'] = adapter_config['embedding_provider']
                                self.logger.info(f"Using adapter embedding provider: {adapter_config['embedding_provider']}")

                            # Pass adapter-specific config to retriever
                            merged_config['adapter_config'] = adapter_config.get('config', {})

                            return merged_config

        except Exception as e:
            self.logger.warning(f"Could not lookup adapter-specific config for API key: {e}")

        # Fall back to global config
        self.logger.debug(f"Using global config for api_key: {api_key[:8]}...")
        return self.config

    async def _index_chunks_in_vector_store(
        self,
        file_id: str,
        api_key: str,
        chunks: List[Chunk]
    ) -> Optional[tuple]:
        """
        Index chunks into vector store with provider-aware collection naming.

        Args:
            file_id: File identifier
            api_key: API key
            chunks: List of chunks to index

        Returns:
            Tuple of (collection_name, embedding_provider, embedding_dimensions) if successful, None otherwise
        """
        if not chunks:
            return None

        try:
            from retrievers.implementations.file.file_retriever import FileVectorRetriever

            # Get adapter-specific config for this API key (includes embedding provider override)
            adapter_aware_config = await self._get_adapter_config_for_api_key(api_key)

            # Initialize file retriever with adapter-aware config
            retriever = FileVectorRetriever(config=adapter_aware_config)
            await retriever.initialize()

            # Get embedding provider info for collection naming (now uses adapter-specific provider)
            embedding_provider = adapter_aware_config.get('embedding', {}).get('provider', 'ollama')

            # Get embedding dimensions
            try:
                if retriever.embeddings and hasattr(retriever.embeddings, 'get_dimensions'):
                    embedding_dimensions = await retriever.embeddings.get_dimensions()
                else:
                    # Fallback: try to get dimensions by embedding a test query
                    test_embedding = await retriever.embed_query("test")
                    embedding_dimensions = len(test_embedding)
            except Exception as e:
                self.logger.warning(f"Could not determine embedding dimensions: {e}. Using default 768")
                embedding_dimensions = 768

            # Generate collection name with provider and dimensions
            from datetime import datetime, UTC
            timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
            collection_prefix = adapter_aware_config.get('collection_prefix', 'files_')

            # Format: files_{provider}_{dimensions}_{apikey}_{timestamp}
            collection_name = f"{collection_prefix}{embedding_provider}_{embedding_dimensions}_{api_key}_{timestamp}"

            self.logger.info(f"Creating collection with provider-aware naming: {collection_name}")

            # Index chunks
            success = await retriever.index_file_chunks(
                file_id=file_id,
                chunks=chunks,
                collection_name=collection_name
            )

            if success:
                self.logger.info(f"Indexed {len(chunks)} chunks into collection {collection_name}")
                return (collection_name, embedding_provider, embedding_dimensions)
            else:
                self.logger.warning(f"Failed to index chunks for file {file_id}")
                return None

        except Exception as e:
            self.logger.error(f"Error indexing chunks into vector store: {e}")
            # Don't fail the upload if indexing fails
            return None
    
    async def get_file(self, file_id: str, api_key: str) -> bytes:
        """Retrieve file contents."""
        file_info = await self.metadata_store.get_file_info(file_id)
        
        if not file_info:
            raise FileNotFoundError(f"File not found: {file_id}")
        
        if file_info['api_key'] != api_key:
            raise PermissionError("Access denied")
        
        storage_key = file_info['storage_key']
        return await self.storage.get_file(storage_key)
    
    async def delete_file(self, file_id: str, api_key: str) -> bool:
        """Delete file and all associated chunks."""
        file_info = await self.metadata_store.get_file_info(file_id)
        
        if not file_info:
            return False
        
        if file_info['api_key'] != api_key:
            raise PermissionError("Access denied")
        
        # Delete from storage
        storage_key = file_info['storage_key']
        await self.storage.delete_file(storage_key)
        
        # Delete from metadata store
        return await self.metadata_store.delete_file(file_id)
    
    async def list_files(self, api_key: str) -> List[Dict[str, Any]]:
        """List all files for an API key."""
        return await self.metadata_store.list_files(api_key)
