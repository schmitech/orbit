"""
Database Service Abstraction Layer
===================================

This module provides an abstract base class for database operations and a factory
method to create backend-specific implementations. This allows the application to
work with either MongoDB or SQLite without changing the service layer code.

The abstraction layer ensures that all database operations have a consistent
interface regardless of the underlying database technology.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Tuple, Callable, Awaitable

logger = logging.getLogger(__name__)


class DatabaseService(ABC):
    """
    Abstract base class for database operations.

    This class defines the interface that all database implementations must follow.
    It provides methods for common CRUD operations, indexing, and transactions.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the database service with configuration.

        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the database connection and set up required collections/tables.

        This method should be called before any database operations.
        Implementations should set self._initialized = True when complete.
        """
        pass

    @abstractmethod
    def get_collection(self, collection_name: str):
        """
        Get a collection/table reference by name.

        Args:
            collection_name: Name of the collection/table

        Returns:
            Collection/table reference (type depends on implementation)
        """
        pass

    @abstractmethod
    async def create_index(
        self,
        collection_name: str,
        field_name: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        sparse: bool = False,
        ttl_seconds: Optional[int] = None
    ) -> str:
        """
        Create an index on a collection/table field.

        Args:
            collection_name: Name of the collection/table
            field_name: Field to index (string) or list of (field, direction) tuples
            unique: Whether the index should enforce uniqueness
            sparse: Whether the index should be sparse (only include documents with the field)
            ttl_seconds: TTL in seconds for automatic document expiration (MongoDB only)

        Returns:
            Name of the created index
        """
        pass

    @abstractmethod
    async def find_one(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single document/record in a collection/table.

        Args:
            collection_name: Name of the collection/table
            query: Query criteria

        Returns:
            The document/record if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_many(
        self,
        collection_name: str,
        query: Dict[str, Any],
        limit: int = 100,
        sort: Optional[List[Tuple[str, int]]] = None,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find multiple documents/records in a collection/table.

        Args:
            collection_name: Name of the collection/table
            query: Query criteria
            limit: Maximum number of documents/records to return
            sort: List of (field, direction) tuples for sorting (1=asc, -1=desc)
            skip: Number of documents/records to skip

        Returns:
            List of matching documents/records
        """
        pass

    @abstractmethod
    async def insert_one(
        self,
        collection_name: str,
        document: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Insert a document/record into a collection/table.

        Args:
            collection_name: Name of the collection/table
            document: Document/record to insert

        Returns:
            ID of the inserted document/record, or None if insertion failed
        """
        pass

    @abstractmethod
    async def update_one(
        self,
        collection_name: str,
        query: Dict[str, Any],
        update: Dict[str, Any]
    ) -> bool:
        """
        Update a document/record in a collection/table.

        Args:
            collection_name: Name of the collection/table
            query: Query criteria to find the document/record
            update: Update operation (MongoDB-style $set, $inc, etc.)

        Returns:
            True if a document/record was updated, False otherwise
        """
        pass

    @abstractmethod
    async def delete_one(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> bool:
        """
        Delete a document/record from a collection/table.

        Args:
            collection_name: Name of the collection/table
            query: Query criteria to find the document/record

        Returns:
            True if a document/record was deleted, False otherwise
        """
        pass

    @abstractmethod
    async def delete_many(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> int:
        """
        Delete multiple documents/records from a collection/table.

        Args:
            collection_name: Name of the collection/table
            query: Query criteria to find the documents/records

        Returns:
            Number of documents/records deleted
        """
        pass

    @abstractmethod
    async def execute_transaction(
        self,
        operations: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """
        Execute operations within a transaction.

        Args:
            operations: Async function that takes a session and performs operations

        Returns:
            Result of the operations
        """
        pass

    @abstractmethod
    async def ensure_id_is_object_id(self, id_value: Union[str, Any]) -> Any:
        """
        Ensure that an ID is in the correct format for the database.

        Args:
            id_value: ID value, either as string or native type

        Returns:
            The ID in the correct format for this database
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the database connection and clean up resources."""
        pass


def create_database_service(config: Dict[str, Any]) -> DatabaseService:
    """
    Factory method to create the appropriate database service based on configuration.

    This function reads the backend type from the configuration and instantiates
    the corresponding database service implementation.

    Args:
        config: Application configuration dictionary

    Returns:
        DatabaseService instance (either MongoDBService or SQLiteService)

    Raises:
        ValueError: If the backend type is not supported or not configured
    """
    # Get backend configuration
    backend_config = config.get('internal_services', {}).get('backend', {})
    backend_type = backend_config.get('type', 'mongodb')  # Default to MongoDB for backward compatibility

    if backend_type == 'mongodb':
        from services.mongodb_service import MongoDBService
        logger.info("Using MongoDB as database backend")
        return MongoDBService(config)
    elif backend_type == 'sqlite':
        from services.sqlite_service import SQLiteService
        logger.info("Using SQLite as database backend")
        return SQLiteService(config)
    else:
        raise ValueError(f"Unsupported database backend type: {backend_type}")
