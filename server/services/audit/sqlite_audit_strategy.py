"""
SQLite Audit Storage Strategy
=============================

Implementation of AuditStorageStrategy for SQLite backend.
Uses the existing SQLiteService/DatabaseService interface for storage operations.
"""

import logging
from typing import Dict, Any, Optional, List

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, decompress_text
from utils.id_utils import generate_id

logger = logging.getLogger(__name__)


class SQLiteAuditStrategy(AuditStorageStrategy):
    """
    SQLite implementation of audit storage.

    Uses the DatabaseService abstraction to store audit records in the
    audit_logs table with flattened structure for nested objects.
    """

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the SQLite audit strategy.

        Args:
            config: Application configuration dictionary
            database_service: Optional pre-initialized DatabaseService instance.
                             If not provided, will create one during initialize().
        """
        super().__init__(config)
        self._database_service = database_service
        self._collection_name = config.get('internal_services', {}).get('audit', {}).get(
            'collection_name', 'audit_logs'
        )
        # Compression setting
        self._compress_responses = config.get('internal_services', {}).get('audit', {}).get(
            'compress_responses', False
        )

    async def initialize(self) -> None:
        """
        Initialize the SQLite storage backend.

        Creates the database service if not provided and ensures
        the audit_logs table and indexes exist.
        """
        if self._initialized:
            return

        try:
            # Create database service if not provided
            if self._database_service is None:
                from services.database_service import create_database_service
                self._database_service = create_database_service(self.config)

            # Ensure database is initialized
            if not self._database_service._initialized:
                await self._database_service.initialize()

            # The audit_logs table and indexes are now part of SQLiteService schema
            # They will be created automatically during database initialization

            logger.info(f"SQLite audit storage initialized with collection: {self._collection_name}")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize SQLite audit storage: {e}")
            raise

    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record in SQLite.

        Args:
            record: The audit record to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert record to flat dictionary for SQLite storage
            # Pass compress flag to optionally compress the response
            doc = record.to_flat_dict(compress=self._compress_responses)

            # Add ID
            doc['id'] = generate_id('sqlite')

            # Insert into database
            result = await self._database_service.insert_one(self._collection_name, doc)

            if result:
                logger.debug(f"Stored audit record with ID: {result} (compressed: {self._compress_responses})")
                return True
            else:
                logger.warning("Failed to store audit record - no ID returned")
                return False

        except Exception as e:
            logger.error(f"Error storing audit record in SQLite: {e}")
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
        Query audit records from SQLite.

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
            # Convert boolean filters to SQLite integer format
            converted_filters = {}
            for key, value in filters.items():
                if isinstance(value, bool):
                    converted_filters[key] = 1 if value else 0
                else:
                    converted_filters[key] = value

            # Query the database
            results = await self._database_service.find_many(
                collection_name=self._collection_name,
                query=converted_filters,
                limit=limit,
                skip=offset,
                sort=[(sort_by, sort_order)]
            )

            # Convert results back to nested format for consistency
            return [self._unflatten_record(record) for record in results]

        except Exception as e:
            logger.error(f"Error querying audit records from SQLite: {e}")
            return []

    def _unflatten_record(self, flat_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a flat SQLite record back to nested format.

        Args:
            flat_record: Record with flattened fields

        Returns:
            Record with nested ip_metadata and api_key structures
        """
        # Get response and check if it needs decompression
        response = flat_record.get('response', '')
        is_compressed = bool(flat_record.get('response_compressed', 0))

        if is_compressed and response:
            try:
                response = decompress_text(response)
            except Exception as e:
                logger.warning(f"Failed to decompress response: {e}")
                # Return compressed response as-is if decompression fails

        result = {
            'timestamp': flat_record.get('timestamp'),
            'query': flat_record.get('query'),
            'response': response,
            'response_compressed': is_compressed,
            'backend': flat_record.get('backend'),
            'blocked': bool(flat_record.get('blocked', 0)),
            'ip': flat_record.get('ip'),
            'ip_metadata': {
                'type': flat_record.get('ip_type', 'unknown'),
                'isLocal': bool(flat_record.get('ip_is_local', 0)),
                'source': flat_record.get('ip_source', 'unknown'),
                'originalValue': flat_record.get('ip_original_value', '')
            }
        }

        # Add api_key if present
        if flat_record.get('api_key_value'):
            result['api_key'] = {
                'key': flat_record.get('api_key_value'),
                'timestamp': flat_record.get('api_key_timestamp')
            }

        # Add optional fields
        if flat_record.get('session_id'):
            result['session_id'] = flat_record.get('session_id')
        if flat_record.get('user_id'):
            result['user_id'] = flat_record.get('user_id')
        if flat_record.get('adapter_name'):
            result['adapter_name'] = flat_record.get('adapter_name')
        if flat_record.get('_id'):
            result['_id'] = flat_record.get('_id')

        return result

    async def clear(self) -> bool:
        """
        Clear all audit records from the SQLite audit_logs table.

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
            logger.info(f"Cleared {deleted_count} audit records from SQLite table '{self._collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error clearing audit records from SQLite: {e}")
            return False

    async def close(self) -> None:
        """
        Close the SQLite storage backend.

        Note: We don't close the database service here as it may be shared
        with other parts of the application.
        """
        self._initialized = False
        logger.debug("SQLite audit storage closed")
