"""
MongoDB Audit Storage Strategy
==============================

Implementation of AuditStorageStrategy for MongoDB backend.
Uses the existing MongoDBService/DatabaseService interface for storage operations.
"""

import logging
from typing import Dict, Any, List

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, decompress_text

logger = logging.getLogger(__name__)


class MongoDBDAuditStrategy(AuditStorageStrategy):
    """
    MongoDB implementation of audit storage.

    Uses the DatabaseService abstraction to store audit records in the
    audit_logs collection with nested document structure.
    """

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the MongoDB audit strategy.

        Args:
            config: Application configuration dictionary
            database_service: Optional pre-initialized DatabaseService instance.
                             If not provided, will create one during initialize().
        """
        super().__init__(config)
        self._database_service = database_service
        self._owns_database_service = False
        self._collection_name = config.get('internal_services', {}).get('audit', {}).get(
            'collection_name', 'audit_logs'
        )
        self._indexes_created = False
        # Compression setting
        self._compress_responses = config.get('internal_services', {}).get('audit', {}).get(
            'compress_responses', False
        )

    async def initialize(self) -> None:
        """
        Initialize the MongoDB storage backend.

        Creates the database service if not provided, ensures connection,
        and creates required indexes on the audit_logs collection.
        """
        if self._initialized:
            return

        try:
            # Create database service if not provided
            if self._database_service is None:
                from services.database_service import create_database_service
                self._database_service = create_database_service(self.config)
                self._owns_database_service = True

            # Ensure database is initialized
            if not self._database_service._initialized:
                await self._database_service.initialize()

            # Create indexes for efficient querying
            await self._create_indexes()

            logger.info(f"MongoDB audit storage initialized with collection: {self._collection_name}")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB audit storage: {e}")
            raise

    async def _create_indexes(self) -> None:
        """Create indexes on the audit_logs collection for efficient querying."""
        if self._indexes_created:
            return

        try:
            # Index on timestamp (descending for recent-first queries)
            await self._database_service.create_index(
                self._collection_name,
                [('timestamp', -1)]
            )

            # Index on session_id for session-based queries
            await self._database_service.create_index(
                self._collection_name,
                'session_id'
            )

            # Index on user_id for user-based queries
            await self._database_service.create_index(
                self._collection_name,
                'user_id'
            )

            # Index on blocked for filtering blocked requests
            await self._database_service.create_index(
                self._collection_name,
                'blocked'
            )

            # Index on backend for provider-based queries
            await self._database_service.create_index(
                self._collection_name,
                'backend'
            )

            # Index on adapter_name for adapter-based queries
            await self._database_service.create_index(
                self._collection_name,
                'adapter_name'
            )

            # Compound index for common query patterns
            await self._database_service.create_index(
                self._collection_name,
                [('session_id', 1), ('timestamp', -1)]
            )

            self._indexes_created = True
            logger.debug(f"Created indexes on {self._collection_name} collection")

        except Exception as e:
            logger.warning(f"Error creating indexes on {self._collection_name}: {e}")
            # Don't fail initialization if index creation fails
            # MongoDB will still work, just potentially slower

    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record in MongoDB.

        Args:
            record: The audit record to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert record to dictionary (preserving nested structure)
            # Pass compress flag to optionally compress the response
            doc = record.to_dict(compress=self._compress_responses)

            # Insert into database
            result = await self._database_service.insert_one(self._collection_name, doc)

            if result:
                logger.debug(f"Stored audit record with ID: {result} (compressed: {self._compress_responses})")
                return True
            else:
                logger.warning("Failed to store audit record - no ID returned")
                return False

        except Exception as e:
            logger.error(f"Error storing audit record in MongoDB: {e}")
            return False

    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Query audit records from MongoDB.

        Args:
            filters: Query criteria (e.g., {'session_id': 'abc', 'blocked': True})
            limit: Maximum number of records to return
            offset: Number of records to skip
            sort_by: Field to sort by (default: 'timestamp')
            sort_order: Sort direction (1=ascending, -1=descending)

        Returns:
            List of matching audit records as dictionaries
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Query the database
            results = await self._database_service.find_many(
                collection_name=self._collection_name,
                query=filters,
                limit=limit,
                skip=offset,
                sort=[(sort_by, sort_order)]
            )

            # Decompress queries and responses if needed
            for record in results:
                if record.get('response_compressed'):
                    if record.get('query'):
                        try:
                            record['query'] = decompress_text(record['query'])
                        except Exception as e:
                            logger.warning(f"Failed to decompress query: {e}")
                            # Keep compressed query if decompression fails
                    if record.get('response'):
                        try:
                            record['response'] = decompress_text(record['response'])
                        except Exception as e:
                            logger.warning(f"Failed to decompress response: {e}")
                            # Keep compressed response if decompression fails

            return results

        except Exception as e:
            logger.error(f"Error querying audit records from MongoDB: {e}")
            return []

    async def close(self) -> None:
        """Close MongoDB audit storage resources."""
        if self._database_service and self._owns_database_service:
            try:
                self._database_service.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB audit database service: {e}")

        self._initialized = False

    async def clear(self) -> bool:
        """
        Clear all audit records from the MongoDB audit_logs collection.

        Returns:
            True if cleared successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Use clear_collection to delete all records
            deleted_count = await self._database_service.clear_collection(
                self._collection_name
            )
            logger.info(f"Cleared {deleted_count} audit records from MongoDB collection '{self._collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error clearing MongoDB audit records: {e}")
            return False
