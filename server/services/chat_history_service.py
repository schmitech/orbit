"""
Chat History Service
====================

This service manages chat conversation history using MongoDB for persistence.
Simplified version without Redis caching for better maintainability.
"""

import logging
import asyncio
import hashlib
from typing import Dict, Any, Optional, List, Tuple, Callable, TypeVar, Awaitable
from datetime import datetime, timedelta
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure, DuplicateKeyError

logger = logging.getLogger(__name__)

T = TypeVar('T')

def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    retry_on: tuple = (ServerSelectionTimeoutError, OperationFailure)
):
    """
    Decorator that adds retry logic with exponential backoff
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff in seconds
        max_delay: Maximum delay between retries in seconds
        retry_on: Tuple of exceptions to retry on
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        # Calculate delay with exponential backoff and jitter
                        delay = min(base_delay * (2 ** attempt) + (asyncio.get_event_loop().time() % 1), max_delay)
                        logger.warning(f"Retry attempt {attempt + 1}/{max_attempts} for {func.__name__} after {delay:.2f}s due to {type(e).__name__}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} retry attempts failed for {func.__name__}")
                        raise last_exception
            raise last_exception  # This should never be reached due to the raise in the loop
        return wrapper
    return decorator

class ChatHistoryService:
    """Service for managing chat history and conversations"""
    
    def __init__(self, config: Dict[str, Any], mongodb_service=None):
        """
        Initialize the Chat History Service
        
        Args:
            config: Application configuration
            mongodb_service: MongoDB service instance
        """
        self.config = config
        self.mongodb_service = mongodb_service
        
        # Extract chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self.enabled = self.chat_history_config.get('enabled', True)
        
        # Configuration parameters
        self.default_limit = self.chat_history_config.get('default_limit', 50)
        self.max_conversation_messages = self.chat_history_config.get('max_conversation_messages', 1000)
        self.store_metadata = self.chat_history_config.get('store_metadata', True)
        self.retention_days = self.chat_history_config.get('retention_days', 90)
        self.max_tracked_sessions = self.chat_history_config.get('max_tracked_sessions', 10000)
        
        # Session configuration
        self.session_config = self.chat_history_config.get('session', {})
        self.session_auto_generate = self.session_config.get('auto_generate', True)
        self.session_required = self.session_config.get('required', True)
        self.session_header = self.session_config.get('header_name', 'X-Session-ID')
        
        # User configuration
        self.user_config = self.chat_history_config.get('user', {})
        self.user_header = self.user_config.get('header_name', 'X-User-ID')
        self.user_required = self.user_config.get('required', False)
        
        # MongoDB collection name
        self.collection_name = self.chat_history_config.get('collection_name', 'chat_history')
        
        # In-memory cache for active sessions (lightweight, temporary)
        self._active_sessions = {}  # session_id -> last_activity timestamp
        self._session_message_counts = {}  # session_id -> message count
        
        self.verbose = config.get('general', {}).get('verbose', False)
        self._initialized = False
        
        # Cleanup task handle
        self._cleanup_task = None
        
        logger.info("Chat History Service initialized (inference-only mode)")
        
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
            
            # Schedule cleanup tasks
            if self.retention_days > 0:
                self._cleanup_task = asyncio.create_task(self._cleanup_old_conversations())
                self._inactive_cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions_periodic())
                
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
            
            # Create unique index for message deduplication
            await self.mongodb_service.create_index(
                self.collection_name,
                [("session_id", 1), ("message_hash", 1)],
                unique=True,
                sparse=True  # Allow null values
            )
            
            # Create archive collection indexes
            archive_collection = f"{self.collection_name}_archive"
            await self.mongodb_service.create_index(
                archive_collection,
                [("session_id", 1), ("timestamp", -1)]
            )
            
            # Create index for archive cleanup queries
            await self.mongodb_service.create_index(
                archive_collection,
                "timestamp"
            )
            
            # Create index for archive user queries
            await self.mongodb_service.create_index(
                archive_collection,
                [("user_id", 1), ("timestamp", -1)]
            )
            
            if self.verbose:
                logger.info("Created indexes for chat history and archive collections")
                
        except Exception as e:
            logger.error(f"Error creating indexes: {str(e)}")
            raise
    
    def _generate_message_hash(self, session_id: str, role: str, content: str, timestamp: datetime) -> str:
        """Generate a hash for message deduplication"""
        # Create a unique hash based on session, role, content, and timestamp
        hash_input = f"{session_id}:{role}:{content}:{timestamp.isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    @with_retry()
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None
    ) -> Optional[ObjectId]:
        """
        Add a message to chat history with retry logic
        
        Args:
            session_id: Session identifier
            role: Message role (user/assistant/system)
            content: Message content
            user_id: Optional user identifier
            api_key: Optional API key
            metadata: Optional metadata to store
            idempotency_key: Optional key for deduplication
            
        Returns:
            ObjectId of the inserted message, or None if disabled/failed
        """
        if not self.enabled:
            return None
            
        try:
            # Check if we've exceeded max messages for this conversation
            await self._check_conversation_limits(session_id)
            
            # Prepare message document
            timestamp = datetime.utcnow()
            message_doc = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": timestamp
            }
            
            # Add optional fields
            if user_id:
                message_doc["user_id"] = user_id
                
            if api_key:
                message_doc["api_key"] = api_key
                
            if metadata and self.store_metadata:
                message_doc["metadata"] = metadata
            
            # Add deduplication hash
            if idempotency_key:
                message_doc["message_hash"] = idempotency_key
            else:
                message_doc["message_hash"] = self._generate_message_hash(
                    session_id, role, content, timestamp
                )
            
            # Insert into MongoDB with duplicate handling
            try:
                message_id = await self.mongodb_service.insert_one(
                    self.collection_name,
                    message_doc
                )
                
                # Update session tracking
                self._active_sessions[session_id] = timestamp
                self._session_message_counts[session_id] = \
                    self._session_message_counts.get(session_id, 0) + 1
                
                # Check if we need to clean up inactive sessions
                if len(self._active_sessions) > self.max_tracked_sessions:
                    await self._cleanup_inactive_sessions()
                
                if self.verbose:
                    logger.debug(f"Added message to history: session={session_id}, role={role}")
                
                return message_id
                
            except DuplicateKeyError:
                logger.warning(f"Duplicate message detected for session {session_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error adding message to history: {str(e)}")
            raise
    
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
        
        # Generate idempotency keys for both messages
        timestamp = datetime.utcnow()
        user_key = f"{session_id}:user:{timestamp.isoformat()}"
        assistant_key = f"{session_id}:assistant:{timestamp.isoformat()}"
        
        # Add user message
        user_msg_id = await self.add_message(
            session_id=session_id,
            role="user",
            content=user_message,
            user_id=user_id,
            api_key=api_key,
            metadata=metadata,
            idempotency_key=user_key
        )
        
        # Only add assistant response if user message was added successfully
        assistant_msg_id = None
        if user_msg_id:
            assistant_msg_id = await self.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_response,
                user_id=user_id,
                api_key=api_key,
                metadata=metadata,
                idempotency_key=assistant_key
            )
        
        return user_msg_id, assistant_msg_id
    
    @with_retry()
    async def get_conversation_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
        include_metadata: bool = False,
        before_timestamp: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session with retry logic
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return
            include_metadata: Whether to include metadata
            before_timestamp: Only get messages before this timestamp
            
        Returns:
            List of messages in chronological order
        """
        if not self.enabled:
            return []
            
        try:
            # Build query
            query = {"session_id": session_id}
            if before_timestamp:
                query["timestamp"] = {"$lt": before_timestamp}
            
            # Determine limit
            effective_limit = limit or self.default_limit
            
            if self.verbose:
                logger.info(f"Fetching chat history for session {session_id} with limit {effective_limit}")
            
            # Fetch messages sorted by timestamp descending to get most recent first
            messages = await self.mongodb_service.find_many(
                self.collection_name,
                query,
                sort=[("timestamp", -1)],  # Descending to get latest messages first
                limit=effective_limit
            )
            
            # Reverse to get chronological order
            messages.reverse()
            
            if self.verbose:
                logger.info(f"Retrieved {len(messages)} messages for session {session_id}")
            
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
            
            return processed_messages
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            raise
    
    async def get_user_sessions(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0,
        include_summary: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get list of sessions for a user
        
        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            include_summary: Include first/last message preview
            
        Returns:
            List of session summaries
        """
        if not self.enabled:
            return []
            
        try:
            # Base aggregation pipeline
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$sort": {"timestamp": -1}},
                {"$group": {
                    "_id": "$session_id",
                    "last_activity": {"$first": "$timestamp"},
                    "first_activity": {"$last": "$timestamp"},
                    "message_count": {"$sum": 1},
                    "last_message": {"$first": "$content"},
                    "last_role": {"$first": "$role"}
                }},
                {"$sort": {"last_activity": -1}},
                {"$skip": offset},
                {"$limit": limit}
            ]
            
            collection = self.mongodb_service.get_collection(self.collection_name)
            cursor = collection.aggregate(pipeline)
            sessions = await cursor.to_list(length=None)
            
            # Format results
            results = []
            for session in sessions:
                session_data = {
                    "session_id": session["_id"],
                    "last_activity": session["last_activity"],
                    "first_activity": session["first_activity"],
                    "message_count": session["message_count"],
                    "duration_seconds": (
                        session["last_activity"] - session["first_activity"]
                    ).total_seconds()
                }
                
                if include_summary:
                    # Truncate message preview
                    preview = session.get("last_message", "")[:100]
                    if len(session.get("last_message", "")) > 100:
                        preview += "..."
                    session_data["last_message_preview"] = preview
                    session_data["last_message_role"] = session.get("last_role")
                
                results.append(session_data)
            
            return results
            
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
            
            # Clear from tracking
            self._active_sessions.pop(session_id, None)
            self._session_message_counts.pop(session_id, None)
            
            if self.verbose:
                logger.info(f"Cleared history for session {session_id}: {result.deleted_count} messages")
                
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error clearing session history: {str(e)}")
            return False
    
    async def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """
        Get statistics for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session statistics
        """
        if not self.enabled:
            return {}
            
        try:
            collection = self.mongodb_service.get_collection(self.collection_name)
            
            # Aggregation for session stats
            pipeline = [
                {"$match": {"session_id": session_id}},
                {"$group": {
                    "_id": None,
                    "message_count": {"$sum": 1},
                    "user_messages": {
                        "$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}
                    },
                    "assistant_messages": {
                        "$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}
                    },
                    "first_message": {"$min": "$timestamp"},
                    "last_message": {"$max": "$timestamp"},
                    "total_chars": {"$sum": {"$strLenCP": "$content"}}
                }}
            ]
            
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)
            
            if not results:
                return {"session_id": session_id, "message_count": 0}
            
            stats = results[0]
            return {
                "session_id": session_id,
                "message_count": stats["message_count"],
                "user_messages": stats["user_messages"],
                "assistant_messages": stats["assistant_messages"],
                "first_message": stats["first_message"],
                "last_message": stats["last_message"],
                "duration_seconds": (
                    stats["last_message"] - stats["first_message"]
                ).total_seconds() if stats["last_message"] else 0,
                "total_characters": stats["total_chars"],
                "avg_message_length": stats["total_chars"] // stats["message_count"] 
                    if stats["message_count"] > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting session stats: {str(e)}")
            return {"session_id": session_id, "error": str(e)}
    
    @with_retry()
    async def _check_conversation_limits(self, session_id: str) -> None:
        """
        Check and handle conversation size limits atomically with retry logic
        
        Args:
            session_id: Session identifier
        """
        try:
            collection = self.mongodb_service.get_collection(self.collection_name)
            
            # Use aggregation to get count atomically
            pipeline = [
                {"$match": {"session_id": session_id}},
                {"$count": "total"}
            ]
            result = await collection.aggregate(pipeline).to_list(1)
            message_count = result[0]["total"] if result else 0
            
            # Update cache
            self._session_message_counts[session_id] = message_count
            
            if message_count >= self.max_conversation_messages:
                # Calculate how many messages to archive
                keep_count = int(self.max_conversation_messages * 0.8)
                archive_count = message_count - keep_count
                
                if archive_count > 0:
                    # Define transaction operations
                    async def archive_operation(session):
                        # Use aggregation pipeline to archive directly
                        archive_pipeline = [
                            {"$match": {"session_id": session_id}},
                            {"$sort": {"timestamp": 1}},
                            {"$limit": archive_count},
                            {"$merge": {
                                "into": f"{self.collection_name}_archive",
                                "whenMatched": "keepExisting"
                            }}
                        ]
                        
                        # Execute the archive pipeline
                        await self.mongodb_service.aggregate_with_transaction(
                            self.collection_name,
                            archive_pipeline,
                            session
                        )
                        
                        # Get the IDs of messages that were archived
                        find_pipeline = [
                            {"$match": {"session_id": session_id}},
                            {"$sort": {"timestamp": 1}},
                            {"$limit": archive_count},
                            {"$project": {"_id": 1}}
                        ]
                        archived_messages = await self.mongodb_service.aggregate_with_transaction(
                            self.collection_name,
                            find_pipeline,
                            session
                        )
                        
                        if archived_messages:
                            # Delete the archived messages
                            message_ids = [msg["_id"] for msg in archived_messages]
                            await self.mongodb_service.delete_many_with_transaction(
                                self.collection_name,
                                {"_id": {"$in": message_ids}},
                                session
                            )
                            
                            # Update cache
                            self._session_message_counts[session_id] = keep_count
                            
                            if self.verbose:
                                logger.info(f"Archived {len(message_ids)} messages from session {session_id}")
                    
                    # Execute the transaction
                    await self.mongodb_service.execute_transaction(archive_operation)
                    
        except Exception as e:
            logger.error(f"Error checking conversation limits: {str(e)}")
            raise
    
    async def _cleanup_old_conversations(self) -> None:
        """Background task to clean up old conversations"""
        while True:
            try:
                if self.retention_days > 0:
                    cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
                    
                    collection = self.mongodb_service.get_collection(self.collection_name)
                    
                    # Find sessions to clean up
                    sessions_to_clean = await collection.distinct(
                        "session_id",
                        {"timestamp": {"$lt": cutoff_date}}
                    )
                    
                    total_deleted = 0
                    for session_id in sessions_to_clean:
                        result = await collection.delete_many({
                            "session_id": session_id,
                            "timestamp": {"$lt": cutoff_date}
                        })
                        total_deleted += result.deleted_count
                        
                        # Clean from tracking if all messages deleted
                        remaining = await collection.count_documents({"session_id": session_id})
                        if remaining == 0:
                            self._active_sessions.pop(session_id, None)
                            self._session_message_counts.pop(session_id, None)
                    
                    if total_deleted > 0:
                        logger.info(f"Cleaned up {total_deleted} old messages from {len(sessions_to_clean)} sessions")
                
                # Run cleanup once per day
                await asyncio.sleep(86400)
                
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
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
            limit=max_messages or self.default_limit,
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
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of the service
        
        Returns:
            Dictionary with health status
        """
        try:
            # Test MongoDB connection
            collection = self.mongodb_service.get_collection(self.collection_name)
            await collection.find_one({})
            
            return {
                "status": "healthy",
                "mongodb": "connected",
                "enabled": self.enabled,
                "active_sessions": len(self._active_sessions),
                "tracked_sessions": len(self._session_message_counts)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "mongodb": "disconnected",
                "error": str(e)
            }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get service metrics for monitoring
        
        Returns:
            Dictionary with service metrics including:
            - active_sessions: Number of currently active sessions
            - tracked_sessions: Number of sessions being tracked
            - messages_today: Number of messages received today
            - oldest_tracked_session: Timestamp of the oldest tracked session
        """
        try:
            collection = self.mongodb_service.get_collection(self.collection_name)
            
            # Get today's message count
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await collection.count_documents({"timestamp": {"$gte": today_start}})
            
            # Get archive collection metrics
            archive_collection = self.mongodb_service.get_collection(f"{self.collection_name}_archive")
            archive_count = await archive_collection.count_documents({})
            
            return {
                "active_sessions": len(self._active_sessions),
                "tracked_sessions": len(self._session_message_counts),
                "messages_today": today_count,
                "oldest_tracked_session": min(self._active_sessions.values()).isoformat() if self._active_sessions else None,
                "archived_messages": archive_count,
                "max_tracked_sessions": self.max_tracked_sessions,
                "retention_days": self.retention_days
            }
        except Exception as e:
            logger.error(f"Error getting metrics: {str(e)}")
            return {
                "error": str(e),
                "active_sessions": len(self._active_sessions),
                "tracked_sessions": len(self._session_message_counts)
            }
    
    async def _cleanup_inactive_sessions(self) -> None:
        """
        Remove inactive sessions from memory tracking
        
        This method removes sessions that have been inactive for more than 24 hours
        from the in-memory tracking caches.
        """
        try:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            inactive = [
                sid for sid, last_activity in self._active_sessions.items()
                if last_activity < cutoff
            ]
            
            for sid in inactive:
                self._active_sessions.pop(sid, None)
                self._session_message_counts.pop(sid, None)
                
            if inactive and self.verbose:
                logger.info(f"Cleaned up {len(inactive)} inactive sessions from memory tracking")
                
        except Exception as e:
            logger.error(f"Error cleaning up inactive sessions: {str(e)}")

    async def _cleanup_inactive_sessions_periodic(self) -> None:
        """
        Periodic task to clean up inactive sessions from memory tracking
        
        Runs every hour to prevent memory leaks from inactive session tracking.
        """
        while True:
            try:
                await self._cleanup_inactive_sessions()
                # Run cleanup every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                logger.info("Inactive sessions cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in inactive sessions cleanup task: {str(e)}")
                # Retry in 5 minutes on error
                await asyncio.sleep(300)

    async def close(self) -> None:
        """Clean up resources"""
        # Cancel cleanup tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        if hasattr(self, '_inactive_cleanup_task') and self._inactive_cleanup_task:
            self._inactive_cleanup_task.cancel()
            try:
                await self._inactive_cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clear tracking
        self._active_sessions.clear()
        self._session_message_counts.clear()
        
        logger.info("Chat history service closed")