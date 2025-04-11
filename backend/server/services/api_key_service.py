"""
API Key Service
==============

This service handles API key authentication and retrieval of associated collection names.
It provides functionality to validate API keys and fetch the corresponding Chroma collection
for a given API key.
"""

import logging
import motor.motor_asyncio
from typing import Dict, Any, Optional, Tuple
from fastapi import HTTPException
from datetime import datetime
import secrets
import string

logger = logging.getLogger(__name__)

class ApiKeyService:
    """Service for handling API key authentication and collection mapping"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the API key service with configuration"""
        self.config = config
        self.client = None
        self.database = None
        self.api_keys_collection = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize connection to MongoDB"""
        if self._initialized:
            return
            
        mongodb_config = self.config.get('mongodb', {})
        try:
            # Log MongoDB configuration (without sensitive data)
            logger.info(f"Initializing MongoDB connection with config: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}, database={mongodb_config.get('database')}")
            
            # Construct connection string
            connection_string = "mongodb://"
            if mongodb_config.get('username') and mongodb_config.get('password'):
                connection_string += f"{mongodb_config['username']}:****@"
                logger.info("Using authentication for MongoDB connection")
            
            connection_string += f"{mongodb_config['host']}:{mongodb_config['port']}"
            logger.info(f"Attempting to connect to MongoDB at {mongodb_config['host']}:{mongodb_config['port']}")
            
            # Connect to MongoDB
            self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
            logger.info("MongoDB client created successfully")
            
            # Test the connection
            await self.client.admin.command('ping')
            logger.info("MongoDB connection test successful")
            
            self.database = self.client[mongodb_config['database']]
            self.api_keys_collection = self.database[mongodb_config['apikey_collection']]
            logger.info(f"Using database '{mongodb_config['database']}' and collection '{mongodb_config['apikey_collection']}'")
            
            # Create index on api_key field for faster lookups
            await self.api_keys_collection.create_index("api_key", unique=True)
            logger.info("Created unique index on api_key field")
            
            logger.info("API Key Service initialized successfully")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize API Key Service: {str(e)}")
            logger.error(f"MongoDB connection details: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize API Key Service: {str(e)}")
    
    def _generate_api_key(self, length: int = 32) -> str:
        """
        Generate a random API key
        
        Args:
            length: Length of the API key to generate
            
        Returns:
            A randomly generated API key
        """
        # Use combination of letters and digits for API key
        alphabet = string.ascii_letters + string.digits
        # Generate a random string of specified length
        api_key = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # Add a prefix for easier identification
        prefix = self.config.get('api_keys', {}).get('prefix', 'api_')
        return f"{prefix}{api_key}"
    
    async def get_api_key_status(self, api_key: str) -> Dict[str, Any]:
        """
        Get the full status of an API key
        
        Args:
            api_key: The API key to check
            
        Returns:
            Dictionary with API key status information
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            key_doc = await self.api_keys_collection.find_one({"api_key": api_key})
            
            if not key_doc:
                return {
                    "exists": False,
                    "active": False,
                    "collection": None,
                    "message": "API key does not exist"
                }
                
            return {
                "exists": True,
                "active": bool(key_doc.get("active")),  # Convert to boolean
                "collection": key_doc.get("collection") or key_doc.get("collection_name"),
                "client_name": key_doc.get("client_name"),
                "created_at": key_doc.get("created_at")
            }
            
        except Exception as e:
            logger.error(f"Error getting API key status: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error checking API key status: {str(e)}")
    
    async def validate_api_key(self, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the API key and return the associated collection name
        
        Args:
            api_key: The API key to validate
            
        Returns:
            Tuple of (is_valid, collection_name)
        """
        if not self._initialized:
            await self.initialize()
            
        # Get default behavior from config
        allow_default = self.config.get('api_keys', {}).get('allow_default', False)
        default_collection = self.config.get('chroma', {}).get('collection')
        
        # API key is required unless allow_default is True
        if not api_key:
            if allow_default and default_collection:
                logger.info(f"No API key provided, using default collection: {default_collection}")
                return True, default_collection
            else:
                logger.warning("API key required but not provided")
                return False, None
            
        try:
            # Find the API key in the database
            key_doc = await self.api_keys_collection.find_one({"api_key": api_key})
            
            # Check if the key exists
            if not key_doc:
                logger.warning(f"Invalid API key: {api_key[:5]}...")
                return False, None
                
            # Check if the key is active - explicitly look for False
            active = key_doc.get("active")
            if active is False:  # Only check for explicit False, not falsy values like None
                logger.warning(f"API key is disabled: {api_key[:5]}...")
                return False, None
            
            # Get the collection name
            collection_name = key_doc.get("collection") or key_doc.get("collection_name")
            if not collection_name:
                logger.warning(f"API key {api_key[:5]}... has no associated collection")
                return False, None
                
            logger.info(f"Valid API key. Using collection: {collection_name}")
            return True, collection_name
            
        except Exception as e:
            logger.error(f"Error validating API key: {str(e)}")
            return False, None
    
    async def get_collection_for_api_key(self, api_key: str) -> str:
        """
        Get the collection name for a given API key
        
        Args:
            api_key: The API key to look up
            
        Returns:
            The collection name associated with the API key
            
        Raises:
            HTTPException: If the API key is invalid or has no associated collection
        """
        is_valid, collection_name = await self.validate_api_key(api_key)
        
        if not is_valid or not collection_name:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
            
        return collection_name
    
    async def create_api_key(self, collection_name: str, client_name: str, notes: Optional[str] = None) -> Dict[str, str]:
        """Create a new API key for a specific collection"""
        if self.api_keys_collection is None:
            raise HTTPException(status_code=500, detail="API key service not initialized")
    
    async def create_api_key(self, collection_name: str, client_name: str, notes: Optional[str] = None) -> Dict[str, str]:
        """Create a new API key for a specific collection"""
        if self.api_keys_collection is None:
            raise HTTPException(status_code=500, detail="API key service not initialized")
            
        if not self._initialized:
            await self.initialize()
            
        # Generate a new API key
        api_key = self._generate_api_key()
        
        # Store the API key in MongoDB
        try:
            created_at = datetime.utcnow()
            await self.api_keys_collection.insert_one({
                "api_key": api_key,
                "collection_name": collection_name,
                "collection": collection_name,  # Add collection field for consistency
                "client_name": client_name,
                "notes": notes,
                "created_at": created_at,
                "active": True  # Changed from is_active to active for consistency
            })
            
            return {
                "api_key": api_key,
                "collection": collection_name,  # Match schema expected field name
                "client_name": client_name,
                "notes": notes,
                "created_at": created_at.timestamp(),  # Convert to timestamp as expected by model
                "active": True
            }
        except Exception as e:
            logger.error(f"Error creating API key: {str(e)}")
            raise HTTPException(status_code=500, detail="Error creating API key")
    
    async def deactivate_api_key(self, api_key: str) -> bool:
        """
        Deactivate an API key
        
        Args:
            api_key: The API key to deactivate
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            result = await self.api_keys_collection.update_one(
                {"api_key": api_key},
                {"$set": {"active": False}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deactivating API key: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deactivating API key: {str(e)}")
    
    async def close(self) -> None:
        """Close the MongoDB connection"""
        if self.client:
            self.client.close()
            self._initialized = False