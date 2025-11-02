"""
API Key Service
==============

This service handles API key authentication and retrieval of associated collection names
(supports MongoDB and SQLite backends). It provides functionality to validate API keys
and fetch the corresponding adapter configuration and system prompt for a given API key.

Updated to support adapter-based API keys per the adapter migration strategy.
"""

import logging
import secrets
import string
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, UTC
from fastapi import HTTPException
from bson import ObjectId
import threading
import hashlib

from utils.text_utils import mask_api_key
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

class ApiKeyService:
    """Service for handling API key authentication and adapter/collection mapping"""

    # Singleton pattern implementation
    _instances: Dict[str, 'ApiKeyService'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any], database_service: Optional[DatabaseService] = None):
        """Create or return existing API key service instance based on configuration"""
        cache_key = cls._create_cache_key(config, database_service)
        
        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new API key service instance for: {cache_key}")
            else:
                logger.debug(f"Reusing existing API key service instance for: {cache_key}")
            return cls._instances[cache_key]
    
    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any], database_service: Optional[DatabaseService] = None) -> str:
        """Create a cache key based on database configuration and collection name"""
        # Use database configuration for the cache key
        backend_config = config.get('internal_services', {}).get('backend', {})
        backend_type = backend_config.get('type', 'mongodb')

        # Get collection name based on backend type
        if backend_type == 'mongodb':
            # First try to get collection from internal_services.mongodb
            internal_mongodb_config = config.get('internal_services', {}).get('mongodb', {})
            # Also try top-level mongodb config for collection name
            top_level_mongodb_config = config.get('mongodb', {})
            
            # Collection name can be in either location
            collection_name = (
                internal_mongodb_config.get('apikey_collection') or
                top_level_mongodb_config.get('apikey_collection') or
                'api_keys'
            )
        else:
            collection_name = 'api_keys'

        # Create key based on backend type
        if backend_type == 'mongodb':
            # Get MongoDB config for connection info (with fallback)
            mongodb_config = config.get('internal_services', {}).get('mongodb', {})
            if not mongodb_config:
                mongodb_config = config.get('mongodb', {})
            
            key_parts = [
                'mongodb',
                mongodb_config.get('host', 'localhost'),
                str(mongodb_config.get('port', 27017)),
                mongodb_config.get('database', 'orbit'),
                collection_name
            ]
        else:  # sqlite
            sqlite_config = backend_config.get('sqlite', {})
            key_parts = [
                'sqlite',
                sqlite_config.get('database_path', 'orbit.db'),
                collection_name
            ]

        # Create hash of the key parts for consistency
        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached API key service instances"""
        with cls._lock:
            return {
                'total_cached_instances': len(cls._instances),
                'cached_configurations': list(cls._instances.keys()),
                'memory_info': f"{len(cls._instances)} API key service instances cached"
            }
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached API key service instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("Cleared API key service cache")
    
    def __init__(self, config: Dict[str, Any], database_service: Optional[DatabaseService] = None):
        """Initialize the API key service with configuration"""
        # Avoid re-initialization if this instance was already initialized
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)

        # Use provided database service or create a new one using factory
        if database_service is None:
            from services.database_service import create_database_service
            database_service = create_database_service(config)
        self.database = database_service

        # Collection/table name for API keys - read from backend-specific config
        backend_type = config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')

        if backend_type == 'mongodb':
            # MongoDB: read collection name from mongodb config
            # Check both internal_services.mongodb and top-level mongodb config
            internal_mongodb_config = config.get('internal_services', {}).get('mongodb', {})
            top_level_mongodb_config = config.get('mongodb', {})
            
            # Collection name can be in either location
            self.collection_name = (
                internal_mongodb_config.get('apikey_collection') or
                top_level_mongodb_config.get('apikey_collection') or
                'api_keys'
            )
        else:
            # SQLite or other backends: use default table name
            self.collection_name = 'api_keys'
        
        # Initialize state
        self._initialized = False
        self.api_keys_collection = None
        
        # Mark as initialized to prevent re-initialization
        self._singleton_initialized = True
        
    async def initialize(self) -> None:
        """Initialize the service"""
        # Check if already initialized to prevent duplicate initialization
        if self._initialized:
            if self.verbose:
                logger.debug("API Key Service already initialized, skipping")
            return

        await self.database.initialize()

        # Set up the API keys collection
        self.api_keys_collection = self.database.get_collection(self.collection_name)

        # Create index on api_key field for faster lookups
        await self.database.create_index(self.collection_name, "api_key", unique=True)
        logger.info("Created unique index on api_key field")
        
        # Set initialized flag
        self._initialized = True
        
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
    
    def _get_adapter_config(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """
        Get adapter configuration by name (only if enabled)
        
        Args:
            adapter_name: Name of the adapter to find
            
        Returns:
            Adapter configuration dict or None if not found or disabled
        """
        adapters = self.config.get('adapters', [])
        adapter = next((cfg for cfg in adapters if cfg.get('name') == adapter_name), None)
        
        # Check if adapter exists and is enabled
        if adapter and adapter.get('enabled', True):
            return adapter
        return None
    
    async def get_api_key_status(self, api_key: str) -> Dict[str, Any]:
        """
        Get the full status of an API key
        
        Args:
            api_key: The API key to check
            
        Returns:
            Dictionary with API key status information
        """
        try:
            key_doc = await self.database.find_one(self.collection_name, {"api_key": api_key})
            
            if not key_doc:
                return {
                    "exists": False,
                    "active": False,
                    "adapter_name": None,
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
            
            # For adapter-based keys, prefer adapter_name
            adapter_name = key_doc.get("adapter_name")
            
            return {
                "exists": True,
                "active": bool(key_doc.get("active")),  # Convert to boolean
                "adapter_name": adapter_name,
                "client_name": key_doc.get("client_name"),
                "created_at": key_doc.get("created_at"),
                "system_prompt": system_prompt_info
            }
            
        except Exception as e:
            logger.error(f"Error getting API key status: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error checking API key status: {str(e)}")
    
    async def validate_api_key(self, api_key: str) -> Tuple[bool, Optional[str], Optional[ObjectId]]:
        """
        Validate the API key and return the associated adapter name and system prompt ID
        
        Args:
            api_key: The API key to validate
            
        Returns:
            Tuple of (is_valid, adapter_name, system_prompt_id)
        """
        # Check if default API key behavior is allowed
        if not api_key:
            allow_default = self.config.get('api_keys', {}).get('allow_default', False)
            if allow_default:
                # Return the first available enabled adapter as default
                available_adapters = self.config.get('adapters', [])
                enabled_adapters = [adapter for adapter in available_adapters if adapter.get('enabled', True)]
                default_adapter = enabled_adapters[0].get('name', 'qa-vector-chroma') if enabled_adapters else 'qa-vector-chroma'
                if self.verbose:
                    logger.info(f"No API key provided, using default adapter: {default_adapter}")
                return True, default_adapter, None
            else:
                logger.warning("API key required but not provided")
                return False, None, None
            
        try:
            # Find the API key in the database
            key_doc = await self.database.find_one(self.collection_name, {"api_key": api_key})
            
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
            
            # Try new adapter-based approach first
            adapter_name = key_doc.get("adapter_name")
            if adapter_name:
                # Validate that the adapter exists in configuration
                adapter_config = self._get_adapter_config(adapter_name)
                if not adapter_config:
                    logger.warning(f"API key {masked_key} references non-existent adapter: {adapter_name}")
                    return False, None, None
                
                # Get the system prompt ID if it exists
                system_prompt_id = key_doc.get("system_prompt_id")
                    
                if self.verbose:
                    logger.info(f"Valid API key ({masked_key}). Using adapter: {adapter_name}")
                    if system_prompt_id:
                        logger.info(f"API key {masked_key} has associated system prompt ID: {system_prompt_id}")
                        
                return True, adapter_name, system_prompt_id
            
            # No adapter found
            logger.warning(f"API key {masked_key} has no associated adapter")
            return False, None, None
            
        except Exception as e:
            logger.error(f"Error validating API key: {str(e)}")
            return False, None, None
    
    async def get_adapter_for_api_key(self, api_key: str) -> Tuple[str, Optional[ObjectId]]:
        """
        Get the adapter name and system prompt ID for a given API key
        
        Args:
            api_key: The API key to look up
            
        Returns:
            Tuple of (adapter_name, system_prompt_id)
            
        Raises:
            HTTPException: If the API key is invalid or has no associated adapter
        """
        is_valid, adapter_name, system_prompt_id = await self.validate_api_key(api_key)
        
        if not is_valid:
            # Check if this is an empty API key and defaults are allowed
            if not api_key and self.config.get('api_keys', {}).get('allow_default', False):
                available_adapters = self.config.get('adapters', [])
                enabled_adapters = [adapter for adapter in available_adapters if adapter.get('enabled', True)]
                default_adapter = enabled_adapters[0].get('name', 'qa-vector-chroma') if enabled_adapters else 'qa-vector-chroma'
                return default_adapter, None
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        
        if not adapter_name:
            raise HTTPException(status_code=401, detail="No adapter associated with API key")
            
        return adapter_name, system_prompt_id
    
    async def create_api_key(
        self, 
        client_name: str, 
        notes: Optional[str] = None,
        system_prompt_id: Optional[ObjectId] = None,
        adapter_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a specific adapter
        
        Args:
            client_name: Name of the client/organization
            notes: Optional notes about this API key
            system_prompt_id: Optional ID of the system prompt to associate
            adapter_name: Name of the adapter this key will access (required)
            
        Returns:
            Dictionary containing the new API key and metadata
        """
        try:
            # Validate that adapter_name is provided
            if not adapter_name:
                raise HTTPException(status_code=400, detail="adapter_name must be provided")
            
            # Validate adapter exists
            adapter_config = self._get_adapter_config(adapter_name)
            if not adapter_config:
                raise HTTPException(status_code=400, detail=f"Adapter '{adapter_name}' not found in configuration")
            
            # Generate a new API key
            api_key = self._generate_api_key()
            
            # Get current time with UTC timezone
            now = datetime.now(UTC)
            
            # Create the document
            key_doc = {
                "api_key": api_key,
                "client_name": client_name,
                "notes": notes,
                "active": True,
                "created_at": now,
                "adapter_name": adapter_name
            }
            
            # Add system prompt ID if provided
            if system_prompt_id:
                # Convert to string to ensure consistency across backends
                # The database service will handle the appropriate format internally
                key_doc["system_prompt_id"] = str(system_prompt_id)
            
            # Insert into database
            await self.database.insert_one(self.collection_name, key_doc)
            
            if self.verbose:
                logger.info(f"Created new API key for adapter: {adapter_name}")
                if system_prompt_id:
                    logger.info(f"Associated with system prompt ID: {system_prompt_id}")
            
            # Return the API key and metadata
            result = {
                "api_key": api_key,
                "client_name": client_name,
                "notes": notes,
                "active": True,
                "created_at": now.timestamp(),  # Convert datetime to timestamp
                "system_prompt_id": str(system_prompt_id) if system_prompt_id else None,
                "adapter_name": adapter_name
            }
            
            return result
            
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error creating API key: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create API key: {str(e)}")
    
    async def update_api_key_system_prompt(self, api_key: str, system_prompt_id: ObjectId) -> bool:
        """
        Update the system prompt associated with an API key
        
        Args:
            api_key: The API key to update
            system_prompt_id: ID of the system prompt to associate
            
        Returns:
            True if the update was successful, False otherwise
        """
        try:
            # First verify the API key exists
            key_doc = await self.database.find_one(self.collection_name, {"api_key": api_key})
            if not key_doc:
                logger.warning(f"Attempted to update non-existent API key: {mask_api_key(api_key)}")
                return False
                
            # Convert to string for storing (both backends store as string for consistency)
            system_prompt_id_str = str(system_prompt_id)

            # Verify the system prompt exists (use original ID for query, database handles format)
            prompt_doc = await self.database.find_one('system_prompts', {"_id": system_prompt_id})
            if not prompt_doc:
                logger.warning(f"Attempted to associate non-existent system prompt: {system_prompt_id}")
                return False

            # Update the API key document (store as string for consistency)
            result = await self.database.update_one(
                self.collection_name,
                {"api_key": api_key},
                {"$set": {"system_prompt_id": system_prompt_id_str}}
            )

            if self.verbose:
                logger.info(f"Updated system prompt for API key {mask_api_key(api_key)} to {system_prompt_id_str}")
                
            return result
            
        except Exception as e:
            logger.error(f"Error updating API key system prompt: {str(e)}")
            return False
    
    async def rename_api_key(self, old_api_key: str, new_api_key: str) -> bool:
        """
        Rename an API key by updating its api_key value

        Args:
            old_api_key: The current API key to rename
            new_api_key: The new API key value

        Returns:
            True if successful, False otherwise

        Raises:
            HTTPException: If the new key already exists or the old key doesn't exist
        """
        try:
            # First check if the old API key exists
            old_key_doc = await self.database.find_one(self.collection_name, {"api_key": old_api_key})
            if not old_key_doc:
                masked_old_key = mask_api_key(old_api_key)
                logger.warning(f"Attempted to rename non-existent API key: {masked_old_key}")
                raise HTTPException(status_code=404, detail="Old API key not found")

            # Check if the new API key already exists
            new_key_doc = await self.database.find_one(self.collection_name, {"api_key": new_api_key})
            if new_key_doc:
                masked_new_key = mask_api_key(new_api_key)
                logger.warning(f"Attempted to rename to existing API key: {masked_new_key}")
                raise HTTPException(status_code=409, detail="New API key already exists")

            # Update the API key
            result = await self.database.update_one(
                self.collection_name,
                {"api_key": old_api_key},
                {"$set": {"api_key": new_api_key}}
            )

            if self.verbose and result:
                masked_old_key = mask_api_key(old_api_key)
                masked_new_key = mask_api_key(new_api_key)
                logger.info(f"Renamed API key from {masked_old_key} to {masked_new_key}")

            return result

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error renaming API key: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error renaming API key: {str(e)}")

    async def deactivate_api_key(self, api_key: str) -> bool:
        """
        Deactivate an API key

        Args:
            api_key: The API key to deactivate

        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.database.update_one(
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
            return await self.database.delete_one(self.collection_name, {"api_key": api_key})
        except Exception as e:
            logger.error(f"Error deleting API key: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deleting API key: {str(e)}")
    
    async def close(self) -> None:
        """Close the API key service (does not close shared database service)"""
        # Since database service might be shared, we don't close it
        # The service itself doesn't maintain any persistent connections beyond the database
        self._initialized = False
        self.api_keys_collection = None
