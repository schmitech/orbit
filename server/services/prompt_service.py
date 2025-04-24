"""
Prompt Service
=============

This service manages system prompts stored in MongoDB.
It provides functionality to create, retrieve, and update system prompts
that can be associated with API keys.
"""

import logging
import motor.motor_asyncio
from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)

class PromptService:
    """Service for managing system prompts in MongoDB"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the prompt service with configuration"""
        self.config = config
        self.client = None
        self.database = None
        self.prompts_collection = None
        self._initialized = False
        self.verbose = config.get('general', {}).get('verbose', False)
        
    async def initialize(self) -> None:
        """Initialize connection to MongoDB"""
        if self._initialized:
            return
            
        mongodb_config = self.config.get('mongodb', {})
        try:
            # Log MongoDB configuration (without sensitive data)
            logger.info(f"Initializing MongoDB connection for Prompt Service with config: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}, database={mongodb_config.get('database')}")
            
            # Construct connection string
            connection_string = "mongodb://"
            if mongodb_config.get('username') and mongodb_config.get('password'):
                connection_string += f"{mongodb_config['username']}:****@"
                logger.info("Using authentication for MongoDB connection")
            
            connection_string += f"{mongodb_config['host']}:{mongodb_config['port']}"
            
            # Connect to MongoDB
            self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
            logger.info("MongoDB client created successfully for Prompt Service")
            
            # Test the connection
            await self.client.admin.command('ping')
            logger.info("MongoDB connection test successful for Prompt Service")
            
            self.database = self.client[mongodb_config['database']]
            prompts_collection_name = mongodb_config.get('prompts_collection', 'system_prompts')
            self.prompts_collection = self.database[prompts_collection_name]
            logger.info(f"Using database '{mongodb_config['database']}' and collection '{prompts_collection_name}'")
            
            # Create index on name field for faster lookups
            await self.prompts_collection.create_index("name", unique=True)
            logger.info("Created unique index on name field")
            
            logger.info("Prompt Service initialized successfully")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Prompt Service: {str(e)}")
            logger.error(f"MongoDB connection details: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize Prompt Service: {str(e)}")
    
    async def create_prompt(self, name: str, prompt_text: str, version: str = "1.0") -> ObjectId:
        """
        Create a new system prompt
        
        Args:
            name: A unique name for the prompt
            prompt_text: The prompt text
            version: Version string for the prompt
            
        Returns:
            ObjectId of the created prompt
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            now = datetime.utcnow()
            prompt_doc = {
                "name": name,
                "prompt": prompt_text,
                "version": version,
                "created_at": now,
                "updated_at": now
            }
            
            # Check if a prompt with this name already exists
            existing = await self.prompts_collection.find_one({"name": name})
            if existing:
                # Update the existing prompt instead of creating a new one
                result = await self.prompts_collection.update_one(
                    {"name": name},
                    {"$set": {
                        "prompt": prompt_text,
                        "version": version,
                        "updated_at": now
                    }}
                )
                logger.info(f"Updated existing prompt '{name}' to version {version}")
                return existing["_id"]
            
            # Create a new prompt
            result = await self.prompts_collection.insert_one(prompt_doc)
            prompt_id = result.inserted_id
            logger.info(f"Created new prompt '{name}' with ID: {prompt_id}")
            return prompt_id
        except Exception as e:
            logger.error(f"Error creating prompt: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error creating prompt: {str(e)}")
    
    async def get_prompt_by_id(self, prompt_id: ObjectId) -> Optional[Dict[str, Any]]:
        """
        Get a prompt by its ID
        
        Args:
            prompt_id: The ObjectId of the prompt
            
        Returns:
            The prompt document or None if not found
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            # Ensure prompt_id is an ObjectId
            if prompt_id is None:
                logger.info("No prompt_id provided to get_prompt_by_id")
                return None
                
            original_prompt_id = prompt_id
            if isinstance(prompt_id, str):
                try:
                    prompt_id = ObjectId(prompt_id)
                    if self.verbose:
                        logger.info(f"Converted string prompt ID '{original_prompt_id}' to ObjectId: {prompt_id}")
                except Exception as e:
                    logger.error(f"Failed to convert prompt ID '{original_prompt_id}' to ObjectId: {str(e)}")
                    return None
            
            if self.verbose:
                logger.info(f"Looking up prompt with ID: {prompt_id}")
            prompt = await self.prompts_collection.find_one({"_id": prompt_id})
            
            if prompt:
                if self.verbose:
                    logger.info(f"Found prompt: {prompt.get('name')} (version {prompt.get('version')})")
                    # Log a preview of the prompt content
                    prompt_text = prompt.get('prompt', '')
                    preview = prompt_text[:100] + '...' if len(prompt_text) > 100 else prompt_text
                    logger.info(f"Prompt content preview: {preview}")
            else:
                logger.warning(f"No prompt found for ID: {prompt_id}")
                
            return prompt
        except Exception as e:
            logger.error(f"Error retrieving prompt: {str(e)}")
            return None
    
    async def get_prompt_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a prompt by its name
        
        Args:
            name: The name of the prompt
            
        Returns:
            The prompt document or None if not found
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            prompt = await self.prompts_collection.find_one({"name": name})
            return prompt
        except Exception as e:
            logger.error(f"Error retrieving prompt by name: {str(e)}")
            return None
    
    async def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List all prompts
        
        Returns:
            List of all prompt documents
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            cursor = self.prompts_collection.find({})
            prompts = await cursor.to_list(length=100)  # Limit to 100 prompts
            
            # Convert _id to string representation
            for prompt in prompts:
                prompt["_id"] = str(prompt["_id"])
                
            return prompts
        except Exception as e:
            logger.error(f"Error listing prompts: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error listing prompts: {str(e)}")
    
    async def update_prompt(self, prompt_id: ObjectId, prompt_text: str, version: Optional[str] = None) -> bool:
        """
        Update an existing prompt
        
        Args:
            prompt_id: The ObjectId of the prompt to update
            prompt_text: The new prompt text
            version: Optional new version string
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            # Ensure prompt_id is an ObjectId
            if isinstance(prompt_id, str):
                prompt_id = ObjectId(prompt_id)
                
            # Get the current prompt to determine version update
            current_prompt = await self.prompts_collection.find_one({"_id": prompt_id})
            
            if not current_prompt:
                logger.warning(f"Prompt with ID {prompt_id} not found for update")
                return False
                
            # Prepare update document
            update_doc = {
                "prompt": prompt_text,
                "updated_at": datetime.utcnow()
            }
            
            # Update version if provided, otherwise increment minor version
            if version:
                update_doc["version"] = version
            elif "version" in current_prompt:
                # Try to increment minor version number
                try:
                    current_version = current_prompt["version"]
                    # Split on dot and try to increment the last part
                    parts = current_version.split(".")
                    if len(parts) > 1 and parts[-1].isdigit():
                        parts[-1] = str(int(parts[-1]) + 1)
                        update_doc["version"] = ".".join(parts)
                    else:
                        # Fallback to just appending .1
                        update_doc["version"] = f"{current_version}.1"
                except Exception:
                    # If version parsing fails, just add .1
                    update_doc["version"] = f"{current_prompt['version']}.1"
            
            # Perform the update
            result = await self.prompts_collection.update_one(
                {"_id": prompt_id},
                {"$set": update_doc}
            )
            
            success = result.modified_count > 0
            if success:
                logger.info(f"Updated prompt with ID {prompt_id} to version {update_doc.get('version')}")
            else:
                logger.warning(f"Prompt with ID {prompt_id} was not modified")
                
            return success
        except Exception as e:
            logger.error(f"Error updating prompt: {str(e)}")
            return False
    
    async def delete_prompt(self, prompt_id: ObjectId) -> bool:
        """
        Delete a prompt
        
        Args:
            prompt_id: The ObjectId of the prompt to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        try:
            # Ensure prompt_id is an ObjectId
            if isinstance(prompt_id, str):
                prompt_id = ObjectId(prompt_id)
                
            result = await self.prompts_collection.delete_one({"_id": prompt_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting prompt: {str(e)}")
            return False
    
    async def close(self) -> None:
        """Close the MongoDB connection"""
        if self.client:
            self.client.close()
            self._initialized = False