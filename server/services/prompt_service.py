"""
Prompt Service
=============

This service manages system prompts stored in MongoDB.
It provides functionality to create, retrieve, and update system prompts
that can be associated with API keys.
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from datetime import datetime, UTC
from bson import ObjectId

from services.mongodb_service import MongoDBService

logger = logging.getLogger(__name__)

class PromptService:
    """Service for managing system prompts in MongoDB"""
    
    def __init__(self, config: Dict[str, Any], mongodb_service: Optional[MongoDBService] = None):
        """Initialize the prompt service with configuration"""
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Use provided MongoDB service or create a new one
        self.mongodb = mongodb_service or MongoDBService(config)
        
        # MongoDB collection name for prompts
        self.collection_name = config.get('mongodb', {}).get('prompts_collection', 'system_prompts')
        
    async def initialize(self) -> None:
        """Initialize the service"""
        await self.mongodb.initialize()
        
        # Create index on name field for faster lookups
        await self.mongodb.create_index(self.collection_name, "name", unique=True)
        logger.info("Created unique index on name field")
        
        logger.info("Prompt Service initialized successfully")
    
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
        try:
            now = datetime.now(UTC)
            prompt_doc = {
                "name": name,
                "prompt": prompt_text,
                "version": version,
                "created_at": now,
                "updated_at": now
            }
            
            # Check if a prompt with this name already exists
            existing = await self.mongodb.find_one(self.collection_name, {"name": name})
            if existing:
                # Update the existing prompt instead of creating a new one
                result = await self.mongodb.update_one(
                    self.collection_name,
                    {"name": name},
                    {"$set": {
                        "prompt": prompt_text,
                        "version": version,
                        "updated_at": now
                    }}
                )
                if self.verbose:
                    logger.info(f"Updated existing prompt '{name}' to version {version}")
                return existing["_id"]
            
            # Create a new prompt
            prompt_id = await self.mongodb.insert_one(self.collection_name, prompt_doc)
            if self.verbose:
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
        try:
            # Handle None input
            if prompt_id is None:
                logger.info("No prompt_id provided to get_prompt_by_id")
                return None
                
            # Ensure prompt_id is an ObjectId
            original_prompt_id = prompt_id
            if isinstance(prompt_id, str):
                try:
                    prompt_id = await self.mongodb.ensure_id_is_object_id(prompt_id)
                    if self.verbose:
                        logger.info(f"Converted string prompt ID '{original_prompt_id}' to ObjectId: {prompt_id}")
                except Exception as e:
                    logger.error(f"Failed to convert prompt ID '{original_prompt_id}' to ObjectId: {str(e)}")
                    return None
            
            if self.verbose:
                logger.info(f"Looking up prompt with ID: {prompt_id}")
                
            prompt = await self.mongodb.find_one(self.collection_name, {"_id": prompt_id})
            
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
        try:
            return await self.mongodb.find_one(self.collection_name, {"name": name})
        except Exception as e:
            logger.error(f"Error retrieving prompt by name: {str(e)}")
            return None
    
    async def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List all prompts
        
        Returns:
            List of all prompt documents
        """
        try:
            prompts = await self.mongodb.find_many(self.collection_name, {})
            
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
        try:
            # Ensure prompt_id is an ObjectId
            if isinstance(prompt_id, str):
                prompt_id = await self.mongodb.ensure_id_is_object_id(prompt_id)
                
            # Get the current prompt to determine version update
            current_prompt = await self.mongodb.find_one(self.collection_name, {"_id": prompt_id})
            
            if not current_prompt:
                logger.warning(f"Prompt with ID {prompt_id} not found for update")
                return False
                
            # Prepare update document
            update_doc = {
                "prompt": prompt_text,
                "updated_at": datetime.now(UTC)
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
            success = await self.mongodb.update_one(
                self.collection_name,
                {"_id": prompt_id},
                {"$set": update_doc}
            )
            
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
        try:
            # Ensure prompt_id is an ObjectId
            if isinstance(prompt_id, str):
                prompt_id = await self.mongodb.ensure_id_is_object_id(prompt_id)
                
            return await self.mongodb.delete_one(self.collection_name, {"_id": prompt_id})
        except Exception as e:
            logger.error(f"Error deleting prompt: {str(e)}")
            return False