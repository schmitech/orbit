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
        self.default_collection = config.get('chroma', {}).get('collection')
    
    async def initialize(self) -> None:
        """Initialize connection to MongoDB"""
        if self._initialized:
            return
            
        mongodb_config = self.config.get('mongodb', {})
        if not mongodb_config.get('enabled', False):
            logger.warning("MongoDB is not enabled. API key service will use default collection only.")
            self._initialized = True
            return
            
        try:
            # Construct connection string
            connection_string = "mongodb://"
            if mongodb_config.get('username') and mongodb_config.get('password'):
                connection_string += f"{mongodb_config['username']}:{mongodb_config['password']}@"
            
            connection_string += f"{mongodb_config['host']}:{mongodb_config['port']}"
            
            # Connect to MongoDB
            self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
            self.database = self.client[mongodb_config['database']]
            self.api_keys_collection = self.database["api_keys"]
            
            # Create index on api_key field for faster lookups
            await self.api_keys_collection.create_index("api_key", unique=True)
            
            logger.info("API Key Service initialized successfully")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize API Key Service: {str(e)}")
            raise
    
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
            
        # If MongoDB is not enabled, use default collection
        if self.api_keys_collection is None:
            logger.info("Using default collection due to MongoDB being disabled")
            return True, self.default_collection
            
        # If no API key provided, use default collection if allowed
        if not api_key and self.config.get('api_keys', {}).get('allow_default', True):
            logger.info("No API key provided, using default collection")
            return True, self.default_collection
            
        # If no API key provided and default not allowed
        if not api_key:
            logger.warning("API key required but not provided")
            return False, None
            
        try:
            # Find the API key in the database
            key_doc = await self.api_keys_collection.find_one({"api_key": api_key})
            
            if not key_doc:
                logger.warning(f"Invalid API key: {api_key[:5]}...")
                return False, None
                
            # Check if the key is active
            if not key_doc.get("active", True):
                logger.warning(f"API key is disabled: {api_key[:5]}...")
                return False, None
                
            collection_name = key_doc.get("collection")
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
            HTTPException: If the API key is invalid
        """
        is_valid, collection_name = await self.validate_api_key(api_key)
        
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
            
        if not collection_name:
            # Fallback to default collection if needed
            collection_name = self.default_collection
            
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
            
        if self.api_keys_collection is None:
            raise HTTPException(status_code=500, detail="MongoDB not enabled for API key management")
    
    async def close(self) -> None:
        """Close the MongoDB connection"""
        if self.client:
            self.client.close()
            self._initialized = False