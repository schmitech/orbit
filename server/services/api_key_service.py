"""
API Key Service
==============

This service handles API key authentication and retrieval of associated collection names.
It provides functionality to validate API keys and fetch the corresponding Chroma collection
and system prompt for a given API key.
"""

import logging
import secrets
import string
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from fastapi import HTTPException
from bson import ObjectId

from utils.text_utils import mask_api_key
from services.mongodb_service import MongoDBService

logger = logging.getLogger(__name__)

class ApiKeyService:
    """Service for handling API key authentication and collection mapping"""
    
    def __init__(self, config: Dict[str, Any], mongodb_service: Optional[MongoDBService] = None):
        """Initialize the API key service with configuration"""
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Use provided MongoDB service or create a new one
        self.mongodb = mongodb_service or MongoDBService(config)
        
        # MongoDB collection name for API keys
        self.collection_name = config.get('mongodb', {}).get('apikey_collection', 'api_keys')
        
    async def initialize(self) -> None:
        """Initialize the service"""
        await self.mongodb.initialize()
        
        # Create index on api_key field for faster lookups
        await self.mongodb.create_index(self.collection_name, "api_key", unique=True)
        logger.info("Created unique index on api_key field")
        
        logger.info("API Key Service initialized successfully")
    
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
        try:
            key_doc = await self.mongodb.find_one(self.collection_name, {"api_key": api_key})
            
            if not key_doc:
                return {
                    "exists": False,
                    "active": False,
                    "collection": None,
                    "message": "API key does not exist"
                }
            
            # Get system prompt info if associated
            system_prompt_info = None
            if key_doc.get("system_prompt_id"):
                # Include basic info about the system prompt if it exists
                system_prompt_info = {
                    "id": str(key_doc["system_prompt_id"]),
                    "exists": True  # Mark as existing, details can be fetched separately
                }
                
            return {
                "exists": True,
                "active": bool(key_doc.get("active")),  # Convert to boolean
                "collection": key_doc.get("collection") or key_doc.get("collection_name"),
                "client_name": key_doc.get("client_name"),
                "created_at": key_doc.get("created_at"),
                "system_prompt": system_prompt_info
            }
            
        except Exception as e:
            logger.error(f"Error getting API key status: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error checking API key status: {str(e)}")
    
    async def validate_api_key(self, api_key: str) -> Tuple[bool, Optional[str], Optional[ObjectId]]:
        """
        Validate the API key and return the associated collection name and system prompt ID
        
        Args:
            api_key: The API key to validate
            
        Returns:
            Tuple of (is_valid, collection_name, system_prompt_id)
        """
        # Get default behavior from config
        allow_default = self.config.get('api_keys', {}).get('allow_default', False)
        default_collection = self.config.get('chroma', {}).get('collection')
        
        # API key is required unless allow_default is True
        if not api_key:
            if allow_default and default_collection:
                if self.verbose:
                    logger.info(f"No API key provided, using default collection: {default_collection}")
                return True, default_collection, None
            else:
                logger.warning("API key required but not provided")
                return False, None, None
            
        try:
            # Find the API key in the database
            key_doc = await self.mongodb.find_one(self.collection_name, {"api_key": api_key})
            
            # Create a masked version of the API key for logging
            masked_key = mask_api_key(api_key)
            
            # Check if the key exists
            if not key_doc:
                logger.warning(f"Invalid API key: {masked_key}")
                return False, None, None
                
            # Check if the key is active - explicitly look for False
            active = key_doc.get("active")
            if active is False:  # Only check for explicit False, not falsy values like None
                logger.warning(f"API key is disabled: {masked_key}")
                return False, None, None
            
            # Get the collection name
            collection_name = key_doc.get("collection_name")
            if not collection_name:
                logger.warning(f"API key {masked_key} has no associated collection")
                return False, None, None
            
            # Get the system prompt ID if it exists
            system_prompt_id = key_doc.get("system_prompt_id")
                
            if self.verbose:
                logger.info(f"Valid API key ({masked_key}). Using collection: {collection_name}")
                if system_prompt_id:
                    logger.info(f"API key {masked_key} has associated system prompt ID: {system_prompt_id}")
                    
            return True, collection_name, system_prompt_id
            
        except Exception as e:
            logger.error(f"Error validating API key: {str(e)}")
            return False, None, None
    
    async def get_collection_for_api_key(self, api_key: str) -> Tuple[str, Optional[ObjectId]]:
        """
        Get the collection name and system prompt ID for a given API key
        
        Args:
            api_key: The API key to look up
            
        Returns:
            Tuple of (collection_name, system_prompt_id)
            
        Raises:
            HTTPException: If the API key is invalid or has no associated collection
        """
        is_valid, collection_name, system_prompt_id = await self.validate_api_key(api_key)
        
        if not is_valid or not collection_name:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
            
        return collection_name, system_prompt_id
    
    async def create_api_key(
        self, 
        collection_name: str, 
        client_name: str, 
        notes: Optional[str] = None,
        system_prompt_id: Optional[ObjectId] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a specific collection
        
        Args:
            collection_name: Collection name to associate with the key
            client_name: Name of the client
            notes: Optional notes about this API key
            system_prompt_id: Optional ObjectId of a system prompt to associate
            
        Returns:
            Dictionary with the created API key details
        """
        # Generate a new API key
        api_key = self._generate_api_key()
        
        # Store the API key in MongoDB
        try:
            created_at = datetime.utcnow()
            key_doc = {
                "api_key": api_key,
                "collection_name": collection_name,
                "client_name": client_name,
                "notes": notes,
                "created_at": created_at,
                "active": True
            }
            
            # Add system prompt ID if provided
            if system_prompt_id:
                key_doc["system_prompt_id"] = system_prompt_id
                
            await self.mongodb.insert_one(self.collection_name, key_doc)
            
            result = {
                "api_key": api_key,
                "collection": collection_name,  # Match schema expected field name
                "client_name": client_name,
                "notes": notes,
                "created_at": created_at.timestamp(),  # Convert to timestamp as expected by model
                "active": True
            }
            
            # Include system prompt ID in the result if provided
            if system_prompt_id:
                result["system_prompt_id"] = str(system_prompt_id)
                
            return result
        except Exception as e:
            logger.error(f"Error creating API key: {str(e)}")
            raise HTTPException(status_code=500, detail="Error creating API key")
    
    async def update_api_key_system_prompt(self, api_key: str, system_prompt_id: ObjectId) -> bool:
        """
        Update the system prompt associated with an API key
        
        Args:
            api_key: The API key to update
            system_prompt_id: The ObjectId of the system prompt
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure system_prompt_id is an ObjectId
            if isinstance(system_prompt_id, str):
                system_prompt_id = await self.mongodb.ensure_id_is_object_id(system_prompt_id)
                
            success = await self.mongodb.update_one(
                self.collection_name,
                {"api_key": api_key},
                {"$set": {"system_prompt_id": system_prompt_id}}
            )
            
            if success:
                masked_key = mask_api_key(api_key)
                logger.info(f"Updated API key {masked_key} with system prompt ID: {system_prompt_id}")
            else:
                masked_key = mask_api_key(api_key)
                logger.warning(f"API key {masked_key} was not found or not modified")
                
            return success
        except Exception as e:
            logger.error(f"Error updating API key system prompt: {str(e)}")
            return False
    
    async def deactivate_api_key(self, api_key: str) -> bool:
        """
        Deactivate an API key
        
        Args:
            api_key: The API key to deactivate
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.mongodb.update_one(
                self.collection_name,
                {"api_key": api_key},
                {"$set": {"active": False}}
            )
        except Exception as e:
            logger.error(f"Error deactivating API key: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deactivating API key: {str(e)}")
    
    async def delete_api_key(self, api_key: str) -> bool:
        """
        Delete an API key
        
        Args:
            api_key: The API key to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.mongodb.delete_one(self.collection_name, {"api_key": api_key})
        except Exception as e:
            logger.error(f"Error deleting API key: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deleting API key: {str(e)}")