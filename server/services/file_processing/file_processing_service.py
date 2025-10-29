"""
File Processing Service

Main service for processing uploaded files: extraction, chunking, and storage preparation.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

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
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize file processing service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize components
        self.storage = self._init_storage()
        self.metadata_store = FileMetadataStore()
        self.processor_registry = FileProcessorRegistry()
        self.chunker = self._init_chunker()
        
        # Configuration
        self.max_file_size = config.get('max_file_size', 52428800)  # 50MB
        self.supported_types = config.get('supported_types', [
            'application/pdf',
            'text/plain',
            'text/markdown',
            'text/csv',
            'application/json',
            'text/html',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            # Image types
            'image/png',
            'image/jpeg',
            'image/jpg',
            'image/gif',
            'image/bmp',
            'image/tiff',
            'image/webp',
        ])
        
        # Vision service configuration
        self.enable_vision = config.get('enable_vision', True)
        self.vision_provider = config.get('vision_provider', 'openai')
        self.vision_config = config.get('vision', {})
    
    def _init_storage(self) -> FilesystemStorage:
        """Initialize storage backend."""
        storage_root = self.config.get('storage_root', './uploads')
        return FilesystemStorage(storage_root=storage_root)
    
    def _init_chunker(self):
        """Initialize chunking strategy."""
        strategy = self.config.get('chunking_strategy', 'fixed')
        chunk_size = self.config.get('chunk_size', 1000)
        overlap = self.config.get('chunk_overlap', 200)
        
        if strategy == 'semantic':
            return SemanticChunker(chunk_size=chunk_size, overlap=overlap)
        else:
            return FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)
    
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
                'upload_time': datetime.utcnow().isoformat(),
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
            extracted_text, file_metadata = await self._extract_content(file_data, filename, mime_type)
            
            # 6. Chunk content
            chunks = await self._chunk_content(extracted_text, file_id, file_metadata)
            
            # 7. Update metadata store with chunk count
            await self.metadata_store.update_processing_status(
                file_id,
                'completed',
                chunk_count=len(chunks),
            )
            
            # 8. Prepare response
            return {
                'file_id': file_id,
                'status': 'completed',
                'chunk_count': len(chunks),
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
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
    
    async def _extract_content(self, file_data: bytes, filename: str, mime_type: str) -> tuple[str, Dict[str, Any]]:
        """Extract text and metadata from file."""
        # Check if this is an image file
        if self.enable_vision and mime_type.startswith('image/'):
            return await self._extract_image_content(file_data, filename, mime_type)
        
        processor = self.processor_registry.get_processor(mime_type)
        
        if not processor:
            raise ValueError(f"No processor available for MIME type: {mime_type}")
        
        text = await processor.extract_text(file_data, filename)
        metadata = await processor.extract_metadata(file_data, filename)
        
        return text, metadata
    
    async def _extract_image_content(self, file_data: bytes, filename: str, mime_type: str) -> tuple[str, Dict[str, Any]]:
        """Extract content from image using vision services."""
        try:
            from ai_services import AIServiceFactory, ServiceType
            
            # Get vision service
            vision_service = AIServiceFactory.create_service(
                ServiceType.VISION,
                self.vision_provider,
                {'vision': self.vision_config}
            )
            
            # Initialize if needed
            if not vision_service.initialized:
                await vision_service.initialize()
            
            # Extract text from image
            extracted_text = await vision_service.extract_text_from_image(file_data)
            
            # Generate description
            description = await vision_service.describe_image(file_data)
            
            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'extraction_method': 'vision',
                'vision_provider': self.vision_provider,
                'image_description': description,
                'image_text': extracted_text,
            }
            
            # Combine description and extracted text
            text = f"{description}\n\nExtracted text:\n{extracted_text}"
            
            return text, metadata
            
        except Exception as e:
            self.logger.error(f"Error extracting image content: {e}")
            # Return empty content if vision processing fails
            metadata = {
                'filename': filename,
                'mime_type': mime_type,
                'file_size': len(file_data),
                'extraction_method': 'none',
            }
            return "", metadata
    
    async def _chunk_content(self, text: str, file_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """Chunk text content."""
        return self.chunker.chunk_text(text, file_id, metadata)
    
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
