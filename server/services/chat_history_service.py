"""
Chat History Service
====================

This service manages chat conversation history and provides caching capabilities
for improved performance. It integrates with MongoDB for persistence and Redis
for caching, with graceful fallback if caching is unavailable.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import json
import hashlib
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

class ChatHistoryService:
    """Service for managing chat history and conversation caching"""
    
    def __init__(self, config: Dict[str, Any], mongodb_service=None, redis_service=None):
        """
        Initialize the Chat History Service
        
        Args:
            config: Application configuration
            mongodb_service: MongoDB service instance
            redis_service: Redis service instance (optional)
        """
        self.config = config
        self.mongodb_service = mongodb_service
        self.redis_service = redis_service
        
        # Extract chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self.enabled = self.chat_history_config.get('enabled', True)
        
        # Configuration parameters
        self.default_limit = self.chat_history_config.get('default_limit', 50)
        self.store_metadata = self.chat_history_config.get('store_metadata', True)
        self.retention_days = self.chat_history_config.get('retention_days', 90)
        
        # Session configuration
        self.session_config = self.chat_history_config.get('session', {})
        self.session_auto_generate = self.session_config.get('auto_generate', True)
        self.session_required = self.session_config.get('required', True)
        self.session_header = self.session_config.get('header_name', 'X-Session-ID')
        
        # User configuration
        self.user_config = self.chat_history_config.get('user', {})
        self.user_header = self.user_config.get('header_name', 'X-User-ID')
        self.user_required = self.user_config.get('required', False)
        
        # Cache configuration
        self.cache_config = self.chat_history_config.get('cache', {})
        self.max_cached_messages = self.cache_config.get('max_cached_messages', 100)
        self.max_cached_sessions = self.cache_config.get('max_cached_sessions', 1000)
        self.cache_ttl = self.cache_config.get('ttl_seconds', 3600)  # Use configured TTL
        
        # Redis configuration
        self.redis_config = self.chat_history_config.get('redis', {})
        self.redis_enabled = self.redis_config.get('enabled', False)
        
        # MongoDB collection name
        self.collection_name = self.chat_history_config.get('collection_name', 'chat_history')
        
        # In-memory cache for active sessions (fallback if Redis unavailable)
        self._memory_cache = {}
        self._cache_order = []  # Track insertion order for LRU
        
        self.verbose = config.get('general', {}).get('verbose', False)
        self._initialized = False
        
        # Log initialization status
        logger.info(f"Chat History Service initialized with Redis {'enabled' if self.redis_enabled else 'disabled'}")
        if self.redis_enabled and self.redis_service:
            logger.info(f"Redis configuration: host={self.redis_config.get('host')}, port={self.redis_config.get('port')}, db={self.redis_config.get('db')}")
            logger.info(f"Cache settings: TTL={self.cache_ttl}s, max_messages={self.max_cached_messages}, max_sessions={self.max_cached_sessions}")
        
    async def initialize(self) -> None:
        """Initialize the chat history service"""
        if self._initialized:
            return
            
        if not self.enabled:
            logger.info("Chat history service is disabled")
            return
            
        try:
            # Ensure MongoDB is available
            if not self.mongodb_service:
                raise ValueError("MongoDB service is required for chat history")
                
            # Create indexes for efficient querying
            await self._create_indexes()
            
            # Schedule cleanup task for old conversations
            if self.retention_days > 0:
                asyncio.create_task(self._cleanup_old_conversations())
                
            self._initialized = True
            logger.info("Chat history service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize chat history service: {str(e)}")
            raise
    
    async def _create_indexes(self) -> None:
        """Create MongoDB indexes for efficient querying"""
        try:
            # Create compound index for session queries
            await self.mongodb_service.create_index(
                self.collection_name,
                [("session_id", 1), ("timestamp", -1)]
            )
            
            # Create index for user queries
            await self.mongodb_service.create_index(
                self.collection_name,
                [("user_id", 1), ("timestamp", -1)]
            )
            
            # Create index for cleanup queries
            await self.mongodb_service.create_index(
                self.collection_name,
                "timestamp"
            )
            
            # Create index for API key queries
            await self.mongodb_service.create_index(
                self.collection_name,
                "api_key"
            )
            
            if self.verbose:
                logger.info("Created indexes for chat history collection")
                
        except Exception as e:
            logger.error(f"Error creating indexes: {str(e)}")
            raise
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ObjectId]:
        """
        Add a message to chat history
        
        Args:
            session_id: Session identifier
            role: Message role (user/assistant/system)
            content: Message content
            user_id: Optional user identifier
            api_key: Optional API key
            metadata: Optional metadata to store
            
        Returns:
            ObjectId of the inserted message, or None if disabled
        """
        if not self.enabled:
            return None
            
        try:
            # Prepare message document
            message_doc = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            }
            
            # Add optional fields
            if user_id:
                message_doc["user_id"] = user_id
                
            if api_key:
                message_doc["api_key"] = api_key
                
            if metadata and self.store_metadata:
                message_doc["metadata"] = metadata
            
            # Insert into MongoDB
            message_id = await self.mongodb_service.insert_one(
                self.collection_name,
                message_doc
            )
            
            if self.verbose:
                logger.debug(f"Added message to history: session={session_id}, role={role}")
            
            # Update cache
            await self._update_cache(session_id, message_doc)
            
            return message_id
            
        except Exception as e:
            logger.error(f"Error adding message to history: {str(e)}")
            return None
    
    async def add_conversation_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[ObjectId], Optional[ObjectId]]:
        """
        Add a complete conversation turn (user message + assistant response)
        
        Args:
            session_id: Session identifier
            user_message: User's message
            assistant_response: Assistant's response
            user_id: Optional user identifier
            api_key: Optional API key
            metadata: Optional metadata to store
            
        Returns:
            Tuple of (user_message_id, assistant_message_id)
        """
        if not self.enabled:
            return None, None
            
        # Add user message
        user_msg_id = await self.add_message(
            session_id=session_id,
            role="user",
            content=user_message,
            user_id=user_id,
            api_key=api_key,
            metadata=metadata
        )
        
        # Add assistant response
        assistant_msg_id = await self.add_message(
            session_id=session_id,
            role="assistant",
            content=assistant_response,
            user_id=user_id,
            api_key=api_key,
            metadata=metadata
        )
        
        return user_msg_id, assistant_msg_id
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
        include_metadata: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return
            include_metadata: Whether to include metadata
            
        Returns:
            List of messages in chronological order
        """
        if not self.enabled:
            return []
            
        try:
            # Try to get from cache first
            cached_messages = await self._get_from_cache(session_id)
            if cached_messages:
                # Apply limit if specified
                if limit:
                    cached_messages = cached_messages[-limit:]
                    
                # Remove metadata if not requested
                if not include_metadata:
                    for msg in cached_messages:
                        msg.pop('metadata', None)
                        
                return cached_messages
            
            # Fallback to MongoDB
            query = {"session_id": session_id}
            try:
                messages = await self.mongodb_service.find_many(
                    self.collection_name,
                    query,
                    limit=limit or self.default_limit
                )
            except ServerSelectionTimeoutError:
                logger.error("Failed to connect to MongoDB server")
                return []
            except OperationFailure as e:
                logger.error(f"MongoDB operation failed: {str(e)}")
                return []
            
            # Sort by timestamp
            messages.sort(key=lambda x: x.get('timestamp', datetime.min))
            
            # Process messages
            processed_messages = []
            for msg in messages:
                processed_msg = {
                    "role": msg.get("role"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("timestamp")
                }
                
                if include_metadata and "metadata" in msg:
                    processed_msg["metadata"] = msg["metadata"]
                    
                processed_messages.append(processed_msg)
            
            # Update cache with fetched messages
            if processed_messages:
                await self._update_cache(session_id, processed_messages, replace=True)
            
            return processed_messages
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            return []
    
    async def get_user_sessions(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get list of sessions for a user
        
        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            
        Returns:
            List of session summaries
        """
        if not self.enabled:
            return []
            
        try:
            # Aggregate to get unique sessions with last activity
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$sort": {"timestamp": -1}},
                {"$group": {
                    "_id": "$session_id",
                    "last_activity": {"$first": "$timestamp"},
                    "message_count": {"$sum": 1}
                }},
                {"$sort": {"last_activity": -1}},
                {"$skip": offset},
                {"$limit": limit}
            ]
            
            collection = self.mongodb_service.get_collection(self.collection_name)
            cursor = collection.aggregate(pipeline)
            sessions = await cursor.to_list(length=None)
            
            # Format results
            return [
                {
                    "session_id": session["_id"],
                    "last_activity": session["last_activity"],
                    "message_count": session["message_count"]
                }
                for session in sessions
            ]
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {str(e)}")
            return []
    
    async def clear_session_history(self, session_id: str) -> bool:
        """
        Clear all history for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            # Delete from MongoDB
            collection = self.mongodb_service.get_collection(self.collection_name)
            result = await collection.delete_many({"session_id": session_id})
            
            # Clear from cache
            await self._clear_cache(session_id)
            
            if self.verbose:
                logger.info(f"Cleared history for session {session_id}: {result.deleted_count} messages")
                
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error clearing session history: {str(e)}")
            return False
    
    async def _update_cache(
        self,
        session_id: str,
        message_or_messages: Any,
        replace: bool = False
    ) -> None:
        """Update cache with new message(s)"""
        if not session_id:
            return
            
        try:
            # Prepare cache key
            cache_key = f"chat_history:{session_id}"
            
            # Use Redis if available
            if self.redis_service and self.redis_service.enabled:
                logger.debug(f"Updating Redis cache for session {session_id}")
                if replace:
                    # Replace entire conversation
                    logger.debug(f"Replacing entire conversation in Redis for session {session_id}")
                    await self.redis_service.store_list_json(
                        cache_key,
                        message_or_messages,
                        ttl=self.cache_ttl
                    )
                    logger.debug(f"Successfully replaced conversation in Redis for session {session_id}")
                else:
                    # Append single message
                    if isinstance(message_or_messages, dict):
                        # Convert datetime to string for JSON serialization
                        msg_copy = message_or_messages.copy()
                        if 'timestamp' in msg_copy and isinstance(msg_copy['timestamp'], datetime):
                            msg_copy['timestamp'] = msg_copy['timestamp'].isoformat()
                        
                        json_msg = json.dumps(msg_copy)
                        logger.debug(f"Appending message to Redis for session {session_id}")
                        await self.redis_service.rpush(cache_key, json_msg)
                        await self.redis_service.expire(cache_key, self.cache_ttl)
                        logger.debug(f"Successfully appended message to Redis for session {session_id}")
            else:
                logger.debug(f"Redis not available, using in-memory cache for session {session_id}")
                # Use in-memory cache as fallback
                if replace:
                    self._memory_cache[session_id] = message_or_messages
                    logger.debug(f"Replaced conversation in memory cache for session {session_id}")
                else:
                    if session_id not in self._memory_cache:
                        self._memory_cache[session_id] = []
                    
                    if isinstance(message_or_messages, dict):
                        self._memory_cache[session_id].append(message_or_messages)
                        logger.debug(f"Appended message to memory cache for session {session_id}")
                
                # Update LRU order
                if session_id in self._cache_order:
                    self._cache_order.remove(session_id)
                self._cache_order.append(session_id)
                
                # Enforce cache size limit
                while len(self._cache_order) > self.max_cached_sessions:
                    oldest_session = self._cache_order.pop(0)
                    del self._memory_cache[oldest_session]
                    logger.debug(f"Removed oldest session {oldest_session} from memory cache due to size limit")
                    
        except Exception as e:
            logger.error(f"Error updating cache: {str(e)}", exc_info=True)
    
    async def _get_from_cache(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get conversation from cache"""
        if not session_id:
            return None
            
        try:
            cache_key = f"chat_history:{session_id}"
            
            # Try Redis first
            if self.redis_service and self.redis_service.enabled:
                logger.debug(f"Attempting to get conversation from Redis for session {session_id}")
                messages = await self.redis_service.get_list_json(cache_key)
                if messages:
                    logger.debug(f"Successfully retrieved {len(messages)} messages from Redis for session {session_id}")
                    # Convert ISO strings back to datetime
                    for msg in messages:
                        if 'timestamp' in msg and isinstance(msg['timestamp'], str):
                            msg['timestamp'] = datetime.fromisoformat(msg['timestamp'])
                    return messages
                else:
                    logger.debug(f"No messages found in Redis for session {session_id}")
            
            # Fallback to in-memory cache
            logger.debug(f"Falling back to in-memory cache for session {session_id}")
            messages = self._memory_cache.get(session_id)
            if messages:
                logger.debug(f"Found {len(messages)} messages in memory cache for session {session_id}")
            else:
                logger.debug(f"No messages found in memory cache for session {session_id}")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting from cache: {str(e)}", exc_info=True)
            return None
    
    async def _clear_cache(self, session_id: str) -> None:
        """Clear cache for a session"""
        if not session_id:
            return
            
        try:
            cache_key = f"chat_history:{session_id}"
            
            # Clear from Redis
            if self.redis_service and self.redis_service.enabled:
                logger.debug(f"Clearing Redis cache for session {session_id}")
                await self.redis_service.delete(cache_key)
                logger.debug(f"Successfully cleared Redis cache for session {session_id}")
            
            # Clear from in-memory cache
            if session_id in self._memory_cache:
                logger.debug(f"Clearing memory cache for session {session_id}")
                del self._memory_cache[session_id]
                if session_id in self._cache_order:
                    self._cache_order.remove(session_id)
                logger.debug(f"Successfully cleared memory cache for session {session_id}")
                    
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}", exc_info=True)
    
    async def _cleanup_old_conversations(self) -> None:
        """Background task to clean up old conversations"""
        while True:
            try:
                if self.retention_days > 0:
                    cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
                    
                    collection = self.mongodb_service.get_collection(self.collection_name)
                    result = await collection.delete_many({
                        "timestamp": {"$lt": cutoff_date}
                    })
                    
                    if result.deleted_count > 0:
                        logger.info(f"Cleaned up {result.deleted_count} old messages")
                
                # Run cleanup once per day
                await asyncio.sleep(86400)
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(3600)  # Retry in 1 hour on error
    
    async def get_context_messages(
        self,
        session_id: str,
        max_messages: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation messages formatted for LLM context
        
        Args:
            session_id: Session identifier
            max_messages: Maximum number of messages to include
            
        Returns:
            List of messages formatted for LLM context
        """
        if not self.enabled:
            return []
            
        # Get conversation history
        messages = await self.get_conversation_history(
            session_id=session_id,
            limit=max_messages or self.max_cached_messages,
            include_metadata=False
        )
        
        # Format for LLM context
        context_messages = []
        for msg in messages:
            if msg.get("role") in ["user", "assistant", "system"]:
                context_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        return context_messages
    
    async def close(self) -> None:
        """Clean up resources"""
        # Clear in-memory cache
        self._memory_cache.clear()
        self._cache_order.clear()
        logger.info("Chat history service closed")