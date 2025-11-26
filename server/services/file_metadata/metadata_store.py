"""
File Metadata Store
===================

Manages metadata for uploaded files and their processing status.
Uses the main backend database (SQLite or MongoDB) for persistence,
configured via internal_services.backend in config.yaml.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC

from services.database_service import create_database_service, DatabaseService

logger = logging.getLogger(__name__)


class FileMetadataStore:
    """
    Database-backed metadata store for file uploads and chunks.

    Uses the main application backend (SQLite or MongoDB) configured in
    internal_services.backend instead of a separate files.db database.

    Tracks:
    - Uploaded files metadata
    - Processing status
    - Chunk references
    - Vector store mappings
    """

    _instance: Optional['FileMetadataStore'] = None
    _db_service: Optional[DatabaseService] = None

    def __new__(cls, config: Dict[str, Any] = None):
        """Singleton pattern to share database connection."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None, config: Dict[str, Any] = None):
        """
        Initialize metadata store.

        Args:
            db_path: Deprecated - ignored, uses main backend instead
            config: Configuration dictionary (required for first initialization)
        """
        # Skip re-initialization for singleton
        if self._initialized:
            return

        if config is None:
            # Load config if not provided
            try:
                from config.config_manager import load_config
                config = load_config()
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                raise ValueError("Config must be provided for FileMetadataStore initialization")

        self.config = config
        self._db_service = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure the database service is initialized."""
        if self._db_service is None:
            self._db_service = create_database_service(self.config)
            await self._db_service.initialize()

            # Create indexes for uploaded_files and file_chunks
            await self._db_service.create_index('uploaded_files', 'api_key')
            await self._db_service.create_index('file_chunks', 'file_id')

            self._initialized = True
            logger.debug("FileMetadataStore initialized with main backend database")

    async def record_file_upload(
        self,
        file_id: str,
        api_key: str,
        filename: str,
        mime_type: str,
        file_size: int,
        storage_key: str,
        storage_type: str = 'vector',
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Record a new file upload.

        Args:
            file_id: Unique file identifier
            api_key: API key of uploader
            filename: Original filename
            mime_type: MIME type
            file_size: File size in bytes
            storage_key: Storage backend key
            storage_type: 'vector' or 'duckdb'
            metadata: Additional metadata

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            timestamp = datetime.now(UTC).isoformat()

            document = {
                '_id': file_id,
                'api_key': api_key,
                'filename': filename,
                'mime_type': mime_type,
                'file_size': file_size,
                'upload_timestamp': timestamp,
                'processing_status': 'pending',
                'storage_key': storage_key,
                'storage_type': storage_type,
                'metadata_json': json.dumps(metadata or {}),
                'chunk_count': 0,
                'created_at': timestamp,
            }

            result = await self._db_service.insert_one('uploaded_files', document)

            if result:
                logger.debug(f"Recorded file upload: {file_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error recording file upload: {e}")
            return False

    async def update_processing_status(
        self,
        file_id: str,
        status: str,
        chunk_count: int = None,
        vector_store: str = None,
        collection_name: str = None,
        embedding_provider: str = None,
        embedding_dimensions: int = None
    ) -> bool:
        """
        Update file processing status.

        Args:
            file_id: File identifier
            status: New status ('pending', 'processing', 'completed', 'failed')
            chunk_count: Number of chunks created
            vector_store: Vector store used
            collection_name: Collection name
            embedding_provider: Embedding provider used (e.g., 'openai', 'ollama')
            embedding_dimensions: Embedding vector dimensions (e.g., 768, 1536)

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            update_fields = {'processing_status': status}

            if chunk_count is not None:
                update_fields['chunk_count'] = chunk_count

            if vector_store:
                update_fields['vector_store'] = vector_store

            if collection_name:
                update_fields['collection_name'] = collection_name

            if embedding_provider:
                update_fields['embedding_provider'] = embedding_provider

            if embedding_dimensions is not None:
                update_fields['embedding_dimensions'] = embedding_dimensions

            result = await self._db_service.update_one(
                'uploaded_files',
                {'_id': file_id},
                {'$set': update_fields}
            )

            if result:
                logger.debug(f"Updated file {file_id} status to {status}")
            return result

        except Exception as e:
            logger.error(f"Error updating processing status: {e}")
            return False

    async def record_chunk(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        vector_store_id: str = None,
        collection_name: str = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Record a file chunk.

        Args:
            chunk_id: Unique chunk identifier
            file_id: Source file identifier
            chunk_index: Chunk position in file
            vector_store_id: Vector store entry ID
            collection_name: Collection name
            metadata: Chunk metadata

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            timestamp = datetime.now(UTC).isoformat()

            document = {
                '_id': chunk_id,
                'file_id': file_id,
                'chunk_index': chunk_index,
                'vector_store_id': vector_store_id,
                'collection_name': collection_name,
                'chunk_metadata': json.dumps(metadata or {}),
                'created_at': timestamp,
            }

            result = await self._db_service.insert_one('file_chunks', document)

            if result:
                logger.debug(f"Recorded chunk {chunk_id} for file {file_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error recording chunk: {e}")
            return False

    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file information.

        Args:
            file_id: File identifier

        Returns:
            File metadata dictionary or None
        """
        await self._ensure_initialized()

        try:
            result = await self._db_service.find_one('uploaded_files', {'_id': file_id})

            if result:
                file_info = self._convert_to_legacy_format(result)
                # Ensure file_size is an integer (handle None case)
                if file_info.get('file_size') is None:
                    file_info['file_size'] = 0
                return file_info
            return None

        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return None

    async def list_files(self, api_key: str) -> List[Dict[str, Any]]:
        """
        List all files for an API key.

        Args:
            api_key: API key to filter by

        Returns:
            List of file metadata dictionaries
        """
        await self._ensure_initialized()

        try:
            results = await self._db_service.find_many(
                'uploaded_files',
                {'api_key': api_key},
                limit=1000,
                sort=[('upload_timestamp', -1)]
            )

            return [self._convert_to_legacy_format(row) for row in results]

        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []

    async def delete_file(self, file_id: str, skip_chunks: bool = False) -> bool:
        """
        Delete file and all associated chunks.

        Args:
            file_id: File identifier
            skip_chunks: If True, skip deleting chunks (useful if already deleted)

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            # Delete chunks first (unless already deleted)
            if not skip_chunks:
                await self._db_service.delete_many('file_chunks', {'file_id': file_id})

            # Delete file
            result = await self._db_service.delete_one('uploaded_files', {'_id': file_id})

            if result:
                logger.debug(f"Deleted file {file_id} and chunks")
            return result

        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False

    async def get_file_chunks(self, file_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a file.

        Args:
            file_id: File identifier

        Returns:
            List of chunk metadata dictionaries
        """
        await self._ensure_initialized()

        try:
            results = await self._db_service.find_many(
                'file_chunks',
                {'file_id': file_id},
                limit=10000,
                sort=[('chunk_index', 1)]
            )

            return [self._convert_chunk_to_legacy_format(row) for row in results]

        except Exception as e:
            logger.error(f"Error getting file chunks: {e}")
            return []

    async def get_chunk_info(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get chunk information by chunk_id.

        Args:
            chunk_id: Chunk identifier

        Returns:
            Chunk metadata dictionary or None
        """
        await self._ensure_initialized()

        try:
            result = await self._db_service.find_one('file_chunks', {'_id': chunk_id})

            if result:
                chunk_info = self._convert_chunk_to_legacy_format(result)
                # Parse JSON metadata if present
                if 'chunk_metadata' in chunk_info and chunk_info['chunk_metadata']:
                    try:
                        if isinstance(chunk_info['chunk_metadata'], str):
                            chunk_info['chunk_metadata'] = json.loads(chunk_info['chunk_metadata'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                return chunk_info
            return None

        except Exception as e:
            logger.error(f"Error getting chunk info: {e}")
            return None

    async def delete_file_chunks(self, file_id: str) -> bool:
        """
        Delete all chunks for a file.

        Args:
            file_id: File identifier

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            deleted_count = await self._db_service.delete_many('file_chunks', {'file_id': file_id})
            logger.debug(f"Deleted {deleted_count} chunks for file {file_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting file chunks: {e}")
            return False

    async def update_file_metadata(self, file_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update file metadata JSON field.

        Args:
            file_id: File identifier
            metadata: Metadata dictionary to store

        Returns:
            True if successful
        """
        await self._ensure_initialized()

        try:
            result = await self._db_service.update_one(
                'uploaded_files',
                {'_id': file_id},
                {'$set': {'metadata_json': json.dumps(metadata)}}
            )
            return result
        except Exception as e:
            logger.error(f"Error updating file metadata: {e}")
            return False

    async def vacuum(self) -> bool:
        """
        Reclaim space in database after deletions.

        For SQLite backend, this runs VACUUM command.
        For MongoDB backend, this is a no-op.

        Returns:
            True if successful, False otherwise
        """
        await self._ensure_initialized()

        try:
            # Only SQLite needs vacuum
            if hasattr(self._db_service, 'connection'):
                from concurrent.futures import ThreadPoolExecutor
                import asyncio

                def _vacuum():
                    cursor = self._db_service.connection.cursor()
                    cursor.execute("VACUUM")
                    self._db_service.connection.commit()

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _vacuum)
                logger.info("Vacuumed database")
            return True
        except Exception as e:
            logger.error(f"Error vacuuming database: {e}")
            return False

    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the database.

        Returns:
            Dictionary with database statistics including size and record counts
        """
        await self._ensure_initialized()

        try:
            stats = {}

            # Count files
            files = await self._db_service.find_many('uploaded_files', {}, limit=100000)
            stats['file_count'] = len(files)

            # Count chunks
            chunks = await self._db_service.find_many('file_chunks', {}, limit=100000)
            stats['chunk_count'] = len(chunks)

            return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}

    def _convert_to_legacy_format(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert database document to legacy format expected by consumers.

        Handles the _id -> file_id conversion and metadata_json parsing.
        """
        result = dict(doc)

        # Convert _id to file_id for legacy compatibility
        if '_id' in result:
            result['file_id'] = result.pop('_id')

        # Parse metadata_json if present
        if 'metadata_json' in result and result['metadata_json']:
            try:
                if isinstance(result['metadata_json'], str):
                    result['metadata'] = json.loads(result['metadata_json'])
                else:
                    result['metadata'] = result['metadata_json']
            except (json.JSONDecodeError, TypeError):
                result['metadata'] = {}

        return result

    def _convert_chunk_to_legacy_format(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert chunk document to legacy format expected by consumers.

        Handles the _id -> chunk_id conversion.
        """
        result = dict(doc)

        # Convert _id to chunk_id for legacy compatibility
        if '_id' in result:
            result['chunk_id'] = result.pop('_id')

        return result

    def close(self):
        """Close database connection."""
        if self._db_service:
            self._db_service.close()
            self._db_service = None
            self._initialized = False

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance. Useful for testing."""
        if cls._instance and cls._instance._db_service:
            cls._instance._db_service.close()
        cls._instance = None
        cls._db_service = None
