"""
Prompt Service
=============

This service manages system prompts stored in MongoDB.
It provides functionality to create, retrieve, and update system prompts
that can be associated with API keys.
"""

import json
import logging
from typing import Dict, Any, Optional, List, Union
from fastapi import HTTPException
from datetime import datetime, UTC
from bson import ObjectId
import re

from services.database_service import DatabaseService

try:  # Optional Redis dependency
    from services.redis_service import RedisService
except Exception:  # pragma: no cover - Redis optional, fallback to disabled caching
    RedisService = None  # type: ignore

logger = logging.getLogger(__name__)

class PromptService:
    """Service for managing system prompts"""

    def __init__(
        self,
        config: Dict[str, Any],
        database_service: Optional[DatabaseService] = None,
        redis_service: Optional[RedisService] = None,
    ):
        """Initialize the prompt service with configuration"""
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)

        # Use provided database service or create a new one using factory
        if database_service is None:
            from services.database_service import create_database_service
            database_service = create_database_service(config)
        self.database = database_service
        
        # MongoDB collection name for prompts
        self.collection_name = config.get('mongodb', {}).get('prompts_collection', 'system_prompts')

        # Redis caching support
        self.redis_service = redis_service
        self.prompt_cache_ttl = (
            config.get('prompt_service', {})
            .get('cache', {})
            .get('ttl_seconds')
        )

        # Fall back to Redis default TTL if not specified, or use 1 hour as default
        if self.prompt_cache_ttl is None:
            redis_config = config.get('internal_services', {}).get('redis', {})
            self.prompt_cache_ttl = redis_config.get('ttl', 3600)  # Default: 1 hour

        if self.redis_service is None and RedisService is not None:
            redis_config = config.get('internal_services', {}).get('redis', {})
            if redis_config.get('enabled'):
                try:
                    self.redis_service = RedisService(config)
                    if self.verbose:
                        logger.info("Redis service instance created for prompt caching")
                except Exception as exc:  # pragma: no cover - defensive guard if Redis unavailable
                    logger.warning(f"Failed to initialize RedisService for prompt caching: {exc}")
                    self.redis_service = None
                    if self.verbose:
                        logger.info("  → Continuing without Redis cache support")
            elif self.verbose:
                logger.info("Redis caching disabled in configuration (internal_services.redis.enabled=false)")
        elif self.redis_service is None and self.verbose:
            logger.info("Redis caching unavailable (Redis module not installed)")
        
    async def initialize(self) -> None:
        """Initialize the service"""
        await self.database.initialize()
        
        # Create index on name field for faster lookups
        await self.database.create_index(self.collection_name, "name", unique=True)
        logger.info("Created unique index on name field")
        
        logger.info("Prompt Service initialized successfully")

        if self.redis_service:
            try:
                await self.redis_service.initialize()
                if self.verbose:
                    logger.info("✓ Prompt caching via Redis ENABLED")
                    if self.prompt_cache_ttl:
                        logger.info(f"  → Cache TTL: {self.prompt_cache_ttl} seconds ({self.prompt_cache_ttl/60:.1f} minutes)")
                    else:
                        logger.info(f"  → Cache TTL: No expiration (persistent cache)")
                    logger.info(f"  → Cache keys format: prompt:<ObjectId>")
            except Exception as exc:
                logger.warning(f"✗ Disabling prompt caching due to Redis initialization error: {exc}")
                self.redis_service = None
                if self.verbose:
                    logger.info("  → Prompts will be fetched from MongoDB on every request")

    def _get_cache_key(self, prompt_id: Union[ObjectId, str]) -> str:
        """Build a cache key for the given prompt identifier."""
        return f"prompt:{str(prompt_id)}"
    
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
            existing = await self.database.find_one(self.collection_name, {"name": name})
            if existing:
                # Update the existing prompt instead of creating a new one
                result = await self.database.update_one(
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
            prompt_id = await self.database.insert_one(self.collection_name, prompt_doc)
            if self.verbose:
                logger.info(f"Created new prompt '{name}' with ID: {prompt_id}")
            return prompt_id
        except Exception as e:
            logger.error(f"Error creating prompt: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error creating prompt: {str(e)}")
    
    async def get_prompt_by_id(self, prompt_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """
        Get a prompt by its ID

        Args:
            prompt_id: The ID of the prompt (ObjectId or UUID string)

        Returns:
            The prompt document or None if not found
        """
        try:
            # Handle None input
            if prompt_id is None:
                logger.info("No prompt_id provided to get_prompt_by_id")
                return None

            # Convert to string for consistency across backends
            prompt_id_str = str(prompt_id)
            cache_key = self._get_cache_key(prompt_id_str)

            # Redis cache lookup
            if self.redis_service:
                if self.verbose:
                    logger.info(f"Checking Redis cache for prompt {cache_key} (ID: {prompt_id_str})")
                cached_value = await self.redis_service.get(cache_key)
                if cached_value:
                    try:
                        cached_prompt = json.loads(cached_value)
                        # Keep _id as string for consistency
                        if '_id' in cached_prompt and not isinstance(cached_prompt['_id'], str):
                            cached_prompt['_id'] = str(cached_prompt['_id'])
                        # Convert ISO datetime strings back to datetime objects
                        for key, value in list(cached_prompt.items()):
                            if isinstance(value, str) and key in ['created_at', 'updated_at']:
                                try:
                                    # Try to parse as ISO datetime
                                    cached_prompt[key] = datetime.fromisoformat(value)
                                except (ValueError, TypeError):
                                    # Keep as string if parsing fails
                                    pass
                        if self.verbose:
                            logger.info(f"✓ Cache HIT for prompt {cache_key} - returning cached prompt '{cached_prompt.get('name')}' version {cached_prompt.get('version')}")
                            # Calculate and log cache savings
                            prompt_size = len(cached_value)
                            logger.info(f"  → Saved MongoDB query, returned {prompt_size} bytes from cache")
                        return cached_prompt
                    except Exception as exc:
                        logger.warning(f"Failed to parse cached prompt for key {cache_key}: {exc}")
                        if self.verbose:
                            logger.info(f"  → Cache entry corrupted, will fetch from MongoDB")
                else:
                    if self.verbose:
                        logger.info(f"✗ Cache MISS for prompt {cache_key} - fetching from MongoDB")

            if self.verbose:
                logger.info(f"Looking up prompt with ID: {prompt_id_str}")

            # Query with original ID (database service handles backend-specific format)
            prompt = await self.database.find_one(self.collection_name, {"_id": prompt_id})

            if prompt:
                if self.verbose:
                    logger.info(f"Found prompt: {prompt.get('name')} (version {prompt.get('version')})")
                    # Log a preview of the prompt content
                    prompt_text = prompt.get('prompt', '')
                    preview = prompt_text[:100] + '...' if len(prompt_text) > 100 else prompt_text
                    logger.info(f"Prompt content preview: {preview}")

                if self.redis_service and prompt:
                    try:
                        serializable_prompt = dict(prompt)
                        # Convert ObjectId to string
                        if '_id' in serializable_prompt:
                            serializable_prompt['_id'] = str(serializable_prompt['_id'])
                        # Convert datetime objects to ISO format strings
                        for key, value in serializable_prompt.items():
                            if isinstance(value, datetime):
                                serializable_prompt[key] = value.isoformat()
                        cache_data = json.dumps(serializable_prompt)
                        cache_result = await self.redis_service.set(
                            cache_key,
                            cache_data,
                            ttl=self.prompt_cache_ttl,
                        )
                        if self.verbose:
                            if cache_result:
                                ttl_msg = f"TTL: {self.prompt_cache_ttl}s" if self.prompt_cache_ttl else "no expiry"
                                logger.info(f"✓ Cached prompt {cache_key} to Redis ({len(cache_data)} bytes, {ttl_msg})")
                                logger.info(f"  → Prompt '{prompt.get('name')}' v{prompt.get('version')} now available in cache")
                            else:
                                logger.warning(f"✗ Failed to cache prompt {cache_key} - Redis set returned False")
                    except Exception as exc:
                        logger.warning(f"Failed to cache prompt {cache_key}: {exc}")
                        if self.verbose:
                            logger.info(f"  → Cache write failed, but prompt still returned from MongoDB")
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
            return await self.database.find_one(self.collection_name, {"name": name})
        except Exception as e:
            logger.error(f"Error retrieving prompt by name: {str(e)}")
            return None
    
    async def list_prompts(self, name_filter: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all prompts with optional filtering and pagination
        
        Args:
            name_filter: Optional name filter (case-insensitive partial match)
            limit: Maximum number of prompts to return
            offset: Number of prompts to skip for pagination
            
        Returns:
            List of all prompt documents
        """
        try:
            # Build filter query
            filter_query = {}
            if name_filter:
                # Case-insensitive partial match using regex
                filter_query["name"] = {"$regex": re.escape(name_filter), "$options": "i"}
            
            # Apply pagination
            prompts = await self.database.find_many(
                self.collection_name, 
                filter_query,
                limit=limit,
                skip=offset
            )
            
            # Convert _id to string representation
            for prompt in prompts:
                prompt["_id"] = str(prompt["_id"])
                
            return prompts
        except Exception as e:
            logger.error(f"Error listing prompts: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error listing prompts: {str(e)}")
    
    async def update_prompt(self, prompt_id: Union[str, ObjectId], prompt_text: str, version: Optional[str] = None) -> bool:
        """
        Update an existing prompt

        Args:
            prompt_id: The ID of the prompt to update (ObjectId or UUID string)
            prompt_text: The new prompt text
            version: Optional new version string

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to string for consistency across backends
            prompt_id_str = str(prompt_id)

            # Clear from cache if Redis is enabled (invalidate on update)
            if self.redis_service:
                cache_key = self._get_cache_key(prompt_id_str)
                cache_deleted = await self.redis_service.delete(cache_key)
                if self.verbose:
                    if cache_deleted:
                        logger.info(f"✓ Invalidated cache for prompt {cache_key} due to update")
                    else:
                        logger.info(f"  → Prompt {cache_key} was not cached")

            # Get the current prompt to determine version update
            current_prompt = await self.database.find_one(self.collection_name, {"_id": prompt_id})

            if not current_prompt:
                logger.warning(f"Prompt with ID {prompt_id_str} not found for update")
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

            # Perform the update (use original prompt_id, database service handles format)
            success = await self.database.update_one(
                self.collection_name,
                {"_id": prompt_id},
                {"$set": update_doc}
            )

            if success:
                logger.info(f"Updated prompt with ID {prompt_id_str} to version {update_doc.get('version')}")
            else:
                logger.warning(f"Prompt with ID {prompt_id_str} was not modified")
                
            return success
        except Exception as e:
            logger.error(f"Error updating prompt: {str(e)}")
            return False
    
    async def delete_prompt(self, prompt_id: Union[str, ObjectId]) -> bool:
        """
        Delete a prompt

        Args:
            prompt_id: The ID of the prompt to delete (ObjectId or UUID string)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to string for logging/caching
            prompt_id_str = str(prompt_id)

            # Clear from cache if Redis is enabled
            if self.redis_service:
                cache_key = self._get_cache_key(prompt_id_str)
                cache_deleted = await self.redis_service.delete(cache_key)
                if self.verbose and cache_deleted:
                    logger.info(f"✓ Cleared prompt {cache_key} from Redis cache")

            # Use original prompt_id (database service handles backend-specific format)
            return await self.database.delete_one(self.collection_name, {"_id": prompt_id})
        except Exception as e:
            logger.error(f"Error deleting prompt: {str(e)}")
            return False

    async def get_cache_stats(self, prompt_id: Optional[Union[ObjectId, str]] = None) -> Dict[str, Any]:
        """
        Get cache statistics for prompts

        Args:
            prompt_id: Optional specific prompt to check cache status for

        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "redis_enabled": self.redis_service is not None,
            "cache_ttl": self.prompt_cache_ttl,
        }

        if self.redis_service and prompt_id:
            cache_key = self._get_cache_key(prompt_id)
            stats["cache_key"] = cache_key
            stats["is_cached"] = await self.redis_service.exists(cache_key)
            if stats["is_cached"]:
                ttl = await self.redis_service.ttl(cache_key)
                stats["ttl_remaining"] = ttl if ttl > 0 else "no expiry"
                cached_value = await self.redis_service.get(cache_key)
                if cached_value:
                    stats["cache_size_bytes"] = len(cached_value)
                    try:
                        cached_data = json.loads(cached_value)
                        stats["cached_prompt_name"] = cached_data.get("name")
                        stats["cached_prompt_version"] = cached_data.get("version")
                    except:
                        pass

        return stats

    async def clear_prompt_cache(self, prompt_id: Optional[Union[ObjectId, str]] = None) -> bool:
        """
        Clear prompt(s) from Redis cache

        Args:
            prompt_id: Optional specific prompt to clear, or None to clear all

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_service:
            if self.verbose:
                logger.info("Redis cache not available - nothing to clear")
            return False

        try:
            if prompt_id:
                cache_key = self._get_cache_key(prompt_id)
                deleted = await self.redis_service.delete(cache_key)
                if self.verbose:
                    if deleted:
                        logger.info(f"✓ Cleared prompt {cache_key} from cache")
                    else:
                        logger.info(f"Prompt {cache_key} was not in cache")
                return deleted > 0
            else:
                # Clear all prompt caches (would need to track keys or use pattern matching)
                if self.verbose:
                    logger.info("Bulk cache clear not implemented - clear specific prompts instead")
                return False
        except Exception as e:
            logger.error(f"Error clearing prompt cache: {str(e)}")
            return False
