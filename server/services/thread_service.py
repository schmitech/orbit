"""
Thread Service
==============

This service manages conversation threads for intent/QA adapters.
Handles thread creation, lifecycle, and dataset linking.
"""

import logging
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, UTC
from utils.id_utils import generate_id, id_to_string

from services.database_service import create_database_service
from services.thread_dataset_service import ThreadDatasetService

logger = logging.getLogger(__name__)


class ThreadService:
    """Service for managing conversation threads"""

    def __init__(self, config: Dict[str, Any], database_service=None, dataset_service=None):
        """
        Initialize the thread service.

        Args:
            config: Application configuration
            database_service: Optional database service instance
            dataset_service: Optional thread dataset service instance
        """
        self.config = config
        
        # Threading configuration
        threading_config = config.get('conversation_threading', {})
        self.enabled = threading_config.get('enabled', True)
        self.dataset_ttl_hours = threading_config.get('dataset_ttl_hours', 24)
        
        # Initialize database service
        if database_service is None:
            self.database_service = create_database_service(config)
        else:
            self.database_service = database_service
        
        # Initialize dataset service
        if dataset_service is None:
            self.dataset_service = ThreadDatasetService(config)
        else:
            self.dataset_service = dataset_service
        
        # Collection/table name
        self.collection_name = 'conversation_threads'
        
        self._initialized = False
        
        logger.debug(f"ThreadService initialized (enabled={self.enabled})")

    async def initialize(self) -> None:
        """Initialize the service and its dependencies."""
        if not self.enabled:
            return
        
        if not self._initialized:
            await self.database_service.initialize()
            await self.dataset_service.initialize()
            self._initialized = True

    def _generate_thread_session_id(self) -> str:
        """Generate a unique session ID for a thread."""
        # Get backend type from config to generate appropriate ID format
        backend_config = self.config.get('internal_services', {}).get('backend', {})
        backend_type = backend_config.get('type', 'mongodb')
        # For session IDs, we always want string format, so use sqlite format (UUID string)
        # regardless of backend, or use the backend's format
        if backend_type == 'sqlite':
            return generate_id('sqlite')
        else:
            # For MongoDB, generate ObjectId but convert to string for session ID
            from bson import ObjectId
            return str(ObjectId())

    async def create_thread(
        self,
        parent_message_id: str,
        parent_session_id: str,
        adapter_name: str,
        query_context: Dict[str, Any],
        raw_results: list
    ) -> Dict[str, Any]:
        """
        Create a new conversation thread from a parent message.

        Args:
            parent_message_id: ID of the parent message
            parent_session_id: Session ID of the parent conversation
            adapter_name: Name of the adapter that generated the response
            query_context: Query context (original query, parameters, template_id)
            raw_results: Raw results from the retriever

        Returns:
            Thread information dictionary with thread_id and thread_session_id
        """
        if not self.enabled:
            raise RuntimeError("Thread service is not enabled")

        if not self._initialized:
            await self.initialize()

        # Validate that we have results to store
        if not raw_results or len(raw_results) == 0:
            raise ValueError("Cannot create thread: no retrieved documents to cache")

        # Generate thread ID and session ID using the configured backend type
        backend_config = self.config.get('internal_services', {}).get('backend', {})
        backend_type = backend_config.get('type', 'mongodb')
        thread_id = generate_id(backend_type)
        # Convert to string immediately for consistent handling
        thread_id_str = id_to_string(thread_id)
        thread_session_id = self._generate_thread_session_id()

        # Calculate expiration time
        expires_at = datetime.now(UTC) + timedelta(hours=self.dataset_ttl_hours)

        try:
            # Store dataset (will use Redis if configured, otherwise database)
            dataset_key = await self.dataset_service.store_dataset(
                thread_id=thread_id_str,
                query_context=query_context,
                raw_results=raw_results
            )

            # Log dataset storage confirmation
            logger.debug(f"Dataset stored with key: {dataset_key} for thread {thread_id_str} ({len(raw_results)} results)")

            # Create thread document
            thread_doc = {
                'id': thread_id_str,
                'parent_message_id': parent_message_id,
                'parent_session_id': parent_session_id,
                'thread_session_id': thread_session_id,
                'adapter_name': adapter_name,
                'query_context': json.dumps(query_context, default=str),
                'dataset_key': dataset_key,
                'created_at': datetime.now(UTC).isoformat(),
                'expires_at': expires_at.isoformat(),
                'metadata_json': json.dumps({}, default=str)
            }

            # Store thread metadata
            await self.database_service.insert_one(self.collection_name, thread_doc)

            logger.debug(f"Created thread {thread_id_str} for message {parent_message_id} (session: {thread_session_id})")

            return {
                'thread_id': thread_id_str,
                'thread_session_id': thread_session_id,
                'parent_message_id': parent_message_id,
                'parent_session_id': parent_session_id,
                'adapter_name': adapter_name,
                'created_at': thread_doc['created_at'],
                'expires_at': thread_doc['expires_at']
            }

        except Exception as e:
            logger.error(f"Failed to create thread: {e}")
            raise

    async def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get thread information by thread ID.

        Args:
            thread_id: Thread identifier

        Returns:
            Thread information dictionary or None if not found/expired
        """
        if not self.enabled:
            return None

        if not self._initialized:
            await self.initialize()

        try:
            # Get thread from database
            thread_doc = await self.database_service.find_one(
                self.collection_name,
                {'id': thread_id}
            )

            if not thread_doc:
                logger.debug(f"Thread {thread_id} not found")
                return None

            # Note: We don't auto-delete expired threads here - that's handled by cleanup_expired_threads()
            # This allows callers to inspect expired threads if needed

            # Parse query context
            query_context_str = thread_doc.get('query_context', '{}')
            try:
                query_context = json.loads(query_context_str)
            except:
                query_context = {}

            return {
                'thread_id': thread_doc.get('_id') or thread_doc.get('id'),
                'thread_session_id': thread_doc.get('thread_session_id'),
                'parent_message_id': thread_doc.get('parent_message_id'),
                'parent_session_id': thread_doc.get('parent_session_id'),
                'adapter_name': thread_doc.get('adapter_name'),
                'query_context': query_context,
                'dataset_key': thread_doc.get('dataset_key'),
                'created_at': thread_doc.get('created_at'),
                'expires_at': thread_doc.get('expires_at')
            }

        except Exception as e:
            logger.error(f"Failed to get thread {thread_id}: {e}")
            return None

    async def get_thread_dataset(self, thread_id: str) -> Optional[Tuple[Dict[str, Any], list]]:
        """
        Get the stored dataset for a thread.

        Args:
            thread_id: Thread identifier

        Returns:
            Tuple of (query_context, raw_results) or None if not found
        """
        if not self.enabled:
            return None

        if not self._initialized:
            await self.initialize()

        try:
            # Get thread to find dataset key
            thread = await self.get_thread(thread_id)
            if not thread:
                return None

            dataset_key = thread.get('dataset_key')
            if not dataset_key:
                return None

            # Get dataset from dataset service
            return await self.dataset_service.get_dataset(dataset_key)

        except Exception as e:
            logger.error(f"Failed to get thread dataset for {thread_id}: {e}")
            return None

    async def delete_thread(self, thread_id: str) -> Dict[str, Any]:
        """
        Delete a thread and its associated dataset.

        Args:
            thread_id: Thread identifier

        Returns:
            Dict with 'status' key ('success' or 'error') and optional 'message'
        """
        if not self.enabled:
            return {'status': 'error', 'message': 'Thread service not enabled'}

        if not self._initialized:
            await self.initialize()

        try:
            # Get thread to find dataset key
            thread_doc = await self.database_service.find_one(
                self.collection_name,
                {'id': thread_id}
            )

            if thread_doc:
                # Delete dataset
                dataset_key = thread_doc.get('dataset_key')
                if dataset_key:
                    await self.dataset_service.delete_dataset(dataset_key)

            # Delete thread metadata
            result = await self.database_service.delete_one(
                self.collection_name,
                {'id': thread_id}
            )

            if result:
                return {'status': 'success', 'thread_id': thread_id}
            else:
                return {'status': 'error', 'message': 'Thread not found'}

        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def cleanup_expired_threads(self) -> int:
        """
        Clean up expired threads and their datasets.

        Returns:
            Number of threads deleted
        """
        if not self.enabled or not self._initialized:
            return 0

        try:
            now = datetime.now(UTC).isoformat()

            # Find expired threads
            expired = await self.database_service.find_many(
                self.collection_name,
                {'expires_at': {'$lt': now}},
                limit=1000
            )
            
            if not expired:
                return 0
            
            # Delete expired threads (this will also delete datasets)
            deleted_count = 0
            for thread_doc in expired:
                thread_id = thread_doc.get('_id') or thread_doc.get('id')
                if thread_id:
                    result = await self.delete_thread(thread_id)
                    if result.get('status') == 'success':
                        deleted_count += 1
            
            if deleted_count > 0:
                logger.debug(f"Cleaned up {deleted_count} expired threads")
            
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired threads: {e}")
            return 0

    async def close(self) -> None:
        """Close the service and its dependencies."""
        if self.dataset_service:
            await self.dataset_service.close()
        
        # Database service cleanup is handled by the service itself
