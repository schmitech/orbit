"""
MongoDB Service
==============

This service provides a reusable MongoDB connection and database access layer.
It handles connection initialization, maintenance, and provides helper methods
for common database operations across multiple services.
"""

import logging
import motor.motor_asyncio
from typing import Dict, Any, Optional, List, Union, Tuple, Callable, Awaitable
from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)

class MongoDBService:
    """Service for handling MongoDB connections and operations"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the MongoDB service with configuration"""
        self.config = config
        self.client = None
        self.database = None
        self._initialized = False
        self.verbose = config.get('general', {}).get('verbose', False)
        self._collections = {}
        
    async def initialize(self) -> None:
        """Initialize connection to MongoDB"""
        if self._initialized:
            return
            
        mongodb_config = self.config.get('internal_services', {}).get('mongodb', {})
        try:
            # Log MongoDB configuration (without sensitive data)
            logger.info(f"Initializing MongoDB connection with config: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}, database={mongodb_config.get('database')}")

            host = mongodb_config.get('host', '')
            port = mongodb_config.get('port', '')
            database = mongodb_config.get('database', '')
            username = mongodb_config.get('username', '')
            password = mongodb_config.get('password', '')

            if "mongodb.net" in host and username and password:
                # MongoDB Atlas with authentication
                connection_string = f"mongodb+srv://{username}:{password}@{host}/{database}?retryWrites=true&w=majority"
                logger.info("Using MongoDB Atlas connection string format")
            elif username and password:
                # Local or remote MongoDB with authentication
                connection_string = f"mongodb://{username}:{password}@{host}:{port}/{database}"
                logger.info("Using standard MongoDB connection string format with authentication")
            else:
                # Local MongoDB without authentication
                connection_string = f"mongodb://{host}:{port}/{database}"
                logger.info("Using standard MongoDB connection string format without authentication")

            logger.info(f"Attempting to connect to MongoDB at {host}")

            # Connect to MongoDB
            self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
            logger.info("MongoDB client created successfully")

            # Test the connection
            await self.client.admin.command('ping')
            logger.info("MongoDB connection test successful")

            self.database = self.client[database]
            logger.info(f"Using database '{database}'")

            logger.info("MongoDB Service initialized successfully")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB Service: {str(e)}")
            logger.error(f"MongoDB connection details: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize MongoDB Service: {str(e)}")
    
    def get_collection(self, collection_name: str):
        """
        Get a MongoDB collection by name
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            The MongoDB collection
        """
        if collection_name in self._collections:
            return self._collections[collection_name]
            
        if not self._initialized:
            raise ValueError("MongoDB Service not initialized. Call initialize() first.")
            
        collection = self.database[collection_name]
        self._collections[collection_name] = collection
        return collection
    
    async def create_index(self, collection_name: str, field_name: Union[str, List[Tuple[str, int]]], unique: bool = False, sparse: bool = False, ttl_seconds: Optional[int] = None) -> str:
        """
        Create an index on a collection field
        
        Args:
            collection_name: Name of the collection
            field_name: Field to index (string) or list of (field, direction) tuples for compound indexes
            unique: Whether the index should enforce uniqueness
            sparse: Whether the index should be sparse (only include documents with the field)
            ttl_seconds: TTL (Time To Live) in seconds for automatic document expiration (only for date fields)
            
        Returns:
            Name of the created index
        """
        if not self._initialized:
            await self.initialize()
            
        collection = self.get_collection(collection_name)
        
        # Build index options
        index_options = {}
        if unique:
            index_options['unique'] = unique
        if sparse:
            index_options['sparse'] = sparse
        if ttl_seconds is not None:
            index_options['expireAfterSeconds'] = ttl_seconds
        
        # Handle compound indexes
        if isinstance(field_name, list):
            index_name = await collection.create_index(field_name, **index_options)
        else:
            index_name = await collection.create_index(field_name, **index_options)
            
        if self.verbose:
            index_type_desc = []
            if unique:
                index_type_desc.append('unique')
            if sparse:
                index_type_desc.append('sparse')
            if ttl_seconds is not None:
                index_type_desc.append(f'TTL ({ttl_seconds}s)')
            
            desc = ' '.join(index_type_desc) + ' ' if index_type_desc else ''
            logger.info(f"Created {desc}index on {collection_name}.{field_name}")
        return index_name
    
    async def find_one(self, collection_name: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find a single document in a collection
        
        Args:
            collection_name: Name of the collection
            query: MongoDB query
            
        Returns:
            The document if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            return await collection.find_one(query)
        except Exception as e:
            logger.error(f"Error finding document in {collection_name}: {str(e)}")
            return None
    
    async def find_many(
        self, 
        collection_name: str, 
        query: Dict[str, Any], 
        limit: int = 100,
        sort: Optional[List[Tuple[str, int]]] = None,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find multiple documents in a collection
        
        Args:
            collection_name: Name of the collection
            query: MongoDB query
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting
            skip: Number of documents to skip
            
        Returns:
            List of matching documents
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            cursor = collection.find(query)
            
            # Apply sorting if specified
            if sort:
                cursor = cursor.sort(sort)
            
            # Apply skip and limit
            cursor = cursor.skip(skip).limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error finding documents in {collection_name}: {str(e)}")
            return []
    
    async def insert_one(self, collection_name: str, document: Dict[str, Any]) -> Optional[ObjectId]:
        """
        Insert a document into a collection
        
        Args:
            collection_name: Name of the collection
            document: Document to insert
            
        Returns:
            ObjectId of the inserted document, or None if insertion failed
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            result = await collection.insert_one(document)
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error inserting document into {collection_name}: {str(e)}")
            return None
    
    async def update_one(self, collection_name: str, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """
        Update a document in a collection
        
        Args:
            collection_name: Name of the collection
            query: MongoDB query to find the document
            update: MongoDB update operation
            
        Returns:
            True if a document was updated, False otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            result = await collection.update_one(query, update)
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating document in {collection_name}: {str(e)}")
            return False
    
    async def delete_one(self, collection_name: str, query: Dict[str, Any]) -> bool:
        """
        Delete a document from a collection
        
        Args:
            collection_name: Name of the collection
            query: MongoDB query to find the document
            
        Returns:
            True if a document was deleted, False otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            result = await collection.delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting document from {collection_name}: {str(e)}")
            return False
    
    async def delete_many(self, collection_name: str, query: Dict[str, Any]) -> int:
        """
        Delete multiple documents from a collection
        
        Args:
            collection_name: Name of the collection
            query: MongoDB query to find the documents
            
        Returns:
            Number of documents deleted
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            result = await collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting documents from {collection_name}: {str(e)}")
            return 0
    
    async def ensure_id_is_object_id(self, id_value: Union[str, ObjectId]) -> ObjectId:
        """
        Ensure that an ID is an ObjectId
        
        Args:
            id_value: ID value, either as string or ObjectId
            
        Returns:
            The ID as an ObjectId
        """
        if isinstance(id_value, str):
            try:
                return ObjectId(id_value)
            except Exception as e:
                logger.error(f"Failed to convert ID '{id_value}' to ObjectId: {str(e)}")
                raise ValueError(f"Invalid ObjectId format: {id_value}")
        return id_value
    
    def close(self) -> None:
        """Close the MongoDB connection"""
        if self.client:
            self.client.close()
            self._initialized = False
            self._collections = {}

    async def execute_transaction(self, operations: Callable[[Any], Awaitable[Any]]) -> Any:
        """
        Execute operations within a MongoDB transaction
        
        Args:
            operations: Async function that takes a session and performs operations
            
        Returns:
            Result of the operations
            
        Raises:
            Exception: If transaction fails or MongoDB is not initialized
        """
        if not self._initialized:
            await self.initialize()
            
        if not self.client:
            raise ValueError("MongoDB client not initialized")
            
        async with await self.client.start_session() as session:
            async with session.start_transaction():
                return await operations(session)

    async def aggregate_with_transaction(
        self,
        collection_name: str,
        pipeline: List[Dict[str, Any]],
        session: Any
    ) -> List[Dict[str, Any]]:
        """
        Execute an aggregation pipeline within a transaction
        
        Args:
            collection_name: Name of the collection
            pipeline: Aggregation pipeline
            session: MongoDB session from transaction
            
        Returns:
            List of documents from aggregation
        """
        if not self._initialized:
            await self.initialize()
            
        collection = self.get_collection(collection_name)
        cursor = collection.aggregate(pipeline, session=session)
        return await cursor.to_list(length=None)

    async def delete_many_with_transaction(
        self,
        collection_name: str,
        query: Dict[str, Any],
        session: Any
    ) -> int:
        """
        Delete multiple documents within a transaction
        
        Args:
            collection_name: Name of the collection
            query: Query to match documents
            session: MongoDB session from transaction
            
        Returns:
            Number of documents deleted
        """
        if not self._initialized:
            await self.initialize()
            
        collection = self.get_collection(collection_name)
        result = await collection.delete_many(query, session=session)
        return result.deleted_count