"""
MongoDB Service
==============

This service provides a reusable MongoDB connection and database access layer.
It handles connection initialization, maintenance, and provides helper methods
for common database operations across multiple services.
"""

import logging
import motor.motor_asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
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
            
            # Construct connection string for MongoDB Atlas
            if "mongodb.net" in mongodb_config.get('host', ''):
                # MongoDB Atlas connection string format
                connection_string = f"mongodb+srv://{mongodb_config['username']}:{mongodb_config['password']}@{mongodb_config['host']}/{mongodb_config['database']}?retryWrites=true&w=majority"
                logger.info("Using MongoDB Atlas connection string format")
            else:
                # Standard MongoDB connection string format
                connection_string = f"mongodb://{mongodb_config['username']}:{mongodb_config['password']}@{mongodb_config['host']}:{mongodb_config['port']}/{mongodb_config['database']}"
                logger.info("Using standard MongoDB connection string format")
            
            logger.info(f"Attempting to connect to MongoDB at {mongodb_config['host']}")
            
            # Connect to MongoDB
            self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
            logger.info("MongoDB client created successfully")
            
            # Test the connection
            await self.client.admin.command('ping')
            logger.info("MongoDB connection test successful")
            
            self.database = self.client[mongodb_config['database']]
            logger.info(f"Using database '{mongodb_config['database']}'")
            
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
    
    async def create_index(self, collection_name: str, field_name: str, unique: bool = False) -> str:
        """
        Create an index on a collection field
        
        Args:
            collection_name: Name of the collection
            field_name: Field to index
            unique: Whether the index should enforce uniqueness
            
        Returns:
            Name of the created index
        """
        if not self._initialized:
            await self.initialize()
            
        collection = self.get_collection(collection_name)
        index_name = await collection.create_index(field_name, unique=unique)
        if self.verbose:
            logger.info(f"Created {'unique ' if unique else ''}index on {collection_name}.{field_name}")
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
    
    async def find_many(self, collection_name: str, query: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """
        Find multiple documents in a collection
        
        Args:
            collection_name: Name of the collection
            query: MongoDB query
            limit: Maximum number of documents to return
            
        Returns:
            List of matching documents
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            collection = self.get_collection(collection_name)
            cursor = collection.find(query)
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