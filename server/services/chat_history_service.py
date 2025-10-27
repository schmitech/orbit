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
from datetime import datetime, timedelta, UTC
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

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the Chat History Service

        Args:
            config: Application configuration
            database_service: Database service instance
        """
        self.config = config
        # Use provided database service or create a new one using factory
        if database_service is None:
            from services.database_service import create_database_service
            database_service = create_database_service(config)
        self.database_service = database_service
        self.api_key_service = None
        
        # Initialize verbose first since it's used in calculation methods
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Extract chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self.enabled = self.chat_history_config.get('enabled', True)
        
        # Configuration parameters
        self.default_limit = self.chat_history_config.get('default_limit', 50)
        # Dynamic max_conversation_messages - will be calculated based on inference provider
        self.max_conversation_messages = self._calculate_max_conversation_messages()
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
        
        self._initialized = False
        
        # Cleanup task handle
        self._cleanup_task = None
        
        logger.info(f"Chat History Service initialized with max_conversation_messages={self.max_conversation_messages} (inference-only mode)")
        
    def _calculate_max_conversation_messages(self) -> int:
        """
        Calculate the maximum conversation messages based on the active inference provider's context window.
        
        This method dynamically determines the conversation limit by:
        1. Getting the active inference provider configuration
        2. Extracting the context window size
        3. Estimating average message length in tokens
        4. Reserving space for system prompts and current query
        5. Converting available context to message count
        
        Returns:
            Maximum number of conversation messages to store
        """
        try:
            # Get the active inference provider
            inference_provider = self.config.get('general', {}).get('inference_provider', 'ollama')
            inference_config = self.config.get('inference', {}).get(inference_provider, {})
            
            # Extract context window size based on provider
            context_window = self._get_context_window_size(inference_provider, inference_config)
            
            # Estimate average tokens per message (including role labels and formatting)
            # This is a conservative estimate: typical message ~50-100 tokens + overhead
            avg_tokens_per_message = 100
            
            # Reserve space for system prompts, current query, and response generation
            # System prompt: ~200 tokens, current query: ~50 tokens, response buffer: ~100 tokens
            reserved_tokens = 350
            
            # Calculate available tokens for conversation history
            available_tokens = max(0, context_window - reserved_tokens)
            
            # Convert to message count (minimum 10, maximum 1000 for safety)
            max_messages = max(10, min(1000, available_tokens // avg_tokens_per_message))
            
            if self.verbose:
                logger.info(f"Context window calculation: provider={inference_provider}, "
                          f"context_window={context_window}, available_tokens={available_tokens}, "
                          f"max_messages={max_messages}")
            
            return max_messages
            
        except Exception as e:
            logger.warning(f"Error calculating max conversation messages: {str(e)}. Using fallback value.")
            # Fallback to a reasonable default if calculation fails
            return 100

    def _get_context_window_size(self, provider: str, provider_config: Dict[str, Any]) -> int:
        """
        Extract context window size from provider configuration.
        
        This method reads the actual configuration parameters used by each provider
        to determine context window size, falling back to reasonable defaults only
        when the parameter isn't configured.
        
        Args:
            provider: The inference provider name
            provider_config: The provider-specific configuration
            
        Returns:
            Context window size in tokens
        """
        # Provider-specific context window parameter names
        # These map to the actual config parameters each provider uses
        context_params = {
            'ollama': 'num_ctx',           # Ollama context window size
            'llama_cpp': 'n_ctx',          # llama.cpp context window size
            'openai': 'context_window',    # User-configurable context window override
            'anthropic': 'context_window', # User-configurable context window override
            'gemini': 'context_window',    # User-configurable context window override
            'groq': 'context_window',      # User-configurable context window override
            'deepseek': 'context_window',  # User-configurable context window override
            'together': 'context_window',  # User-configurable context window override
            'xai': 'context_window',       # User-configurable context window override
            'vllm': 'context_window',      # User-configurable context window override
            'azure': 'context_window',     # User-configurable context window override
            'vertex': 'context_window',    # User-configurable context window override
            'aws': 'context_window',       # User-configurable context window override
            'huggingface': 'max_length',   # HuggingFace uses max_length for context
            'mistral': 'context_window',   # User-configurable context window override
            'openrouter': 'context_window' # User-configurable context window override
        }
        
        # Alternative parameter names that might indicate context window size
        # These are fallback parameters if the primary one isn't found
        alternative_params = {
            'openai': ['max_context_length', 'context_length'],
            'anthropic': ['max_context_length', 'context_length'], 
            'gemini': ['max_context_length', 'context_length'],
            'groq': ['max_context_length', 'context_length'],
            'deepseek': ['max_context_length', 'context_length'],
            'together': ['max_context_length', 'context_length'],
            'xai': ['max_context_length', 'context_length'],
            'vllm': ['max_context_length', 'context_length'],
            'azure': ['max_context_length', 'context_length'],
            'vertex': ['max_context_length', 'context_length'],
            'aws': ['max_context_length', 'context_length'],
            'mistral': ['max_context_length', 'context_length'],
            'openrouter': ['max_context_length', 'context_length']
        }
        
        # Default context window sizes for providers (conservative estimates)
        # Used only when no configuration parameter is found
        default_context_windows = {
            'ollama': 8192,      # Typical Ollama default
            'llama_cpp': 4096,   # Typical llama.cpp default
            'openai': 32768,     # GPT-4 range (varies by model)
            'anthropic': 200000, # Claude 3 range (varies by model)
            'gemini': 32768,     # Gemini Pro range (varies by model)
            'groq': 8192,        # Typical Llama models on Groq
            'deepseek': 32768,   # DeepSeek models range
            'together': 8192,    # Varies by model, conservative estimate
            'xai': 8192,         # Grok models range
            'vllm': 8192,        # Varies by model, conservative estimate
            'azure': 32768,      # Azure OpenAI GPT-4 range
            'vertex': 32768,     # Google Vertex AI Gemini range
            'aws': 8192,         # AWS Bedrock varies by model
            'huggingface': 2048, # Conservative for local HF models
            'mistral': 8192,     # Mistral models range
            'openrouter': 8192   # Varies by routed model
        }
        
        # First, try to read the primary context window parameter
        param_name = context_params.get(provider)
        if param_name and param_name in provider_config:
            context_window = provider_config[param_name]
            if isinstance(context_window, int) and context_window > 0:
                if self.verbose:
                    logger.info(f"Using configured {param_name}={context_window} for provider {provider}")
                return context_window
        
        # Second, try alternative parameter names
        alternatives = alternative_params.get(provider, [])
        for alt_param in alternatives:
            if alt_param in provider_config:
                context_window = provider_config[alt_param]
                if isinstance(context_window, int) and context_window > 0:
                    if self.verbose:
                        logger.info(f"Using configured {alt_param}={context_window} for provider {provider}")
                    return context_window
        
        # Finally, fall back to provider-specific defaults
        default_window = default_context_windows.get(provider, 4096)
        
        if self.verbose:
            logger.info(f"No context window configured for {provider}, using default: {default_window} tokens")
            
        return default_window
        
    async def initialize(self) -> None:
        """Initialize the chat history service"""
        if self._initialized:
            return
            
        if not self.enabled:
            logger.info("Chat history service is disabled")
            return
            
        try:
            # Ensure MongoDB is available
            if not self.database_service:
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
            await self.database_service.create_index(
                self.collection_name,
                [("session_id", 1), ("timestamp", -1)]
            )
            
            # Create index for user queries
            await self.database_service.create_index(
                self.collection_name,
                [("user_id", 1), ("timestamp", -1)]
            )
            
            # Create index for cleanup queries
            await self.database_service.create_index(
                self.collection_name,
                "timestamp"
            )
            
            # Create index for API key queries
            await self.database_service.create_index(
                self.collection_name,
                "api_key"
            )
            
            # Create unique index for message deduplication
            await self.database_service.create_index(
                self.collection_name,
                [("session_id", 1), ("message_hash", 1)],
                unique=True,
                sparse=True  # Allow null values
            )
            
            # Create archive collection indexes
            archive_collection = f"{self.collection_name}_archive"
            await self.database_service.create_index(
                archive_collection,
                [("session_id", 1), ("timestamp", -1)]
            )
            
            # Create index for archive cleanup queries
            await self.database_service.create_index(
                archive_collection,
                "timestamp"
            )
            
            # Create index for archive user queries
            await self.database_service.create_index(
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
            # Prepare message document
            timestamp = datetime.now(UTC)
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
                message_id = await self.database_service.insert_one(
                    self.collection_name,
                    message_doc
                )
                
                # Update session tracking
                self._active_sessions[session_id] = timestamp
                self._session_message_counts[session_id] = \
                    self._session_message_counts.get(session_id, 0) + 1
                
                # Add useful progress logging
                if self.verbose:
                    current_count = self._session_message_counts[session_id]
                    logger.info(f"Session {session_id}: {current_count}/{self.max_conversation_messages} messages used ({role})")
                
                # Check if we need to clean up inactive sessions
                if len(self._active_sessions) > self.max_tracked_sessions:
                    await self._cleanup_inactive_sessions()
                
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
        timestamp = datetime.now(UTC)
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
            
            # Remove noisy fetch logging - only debug level
            if self.verbose:
                logger.debug(f"Fetching chat history for session {session_id} with limit {effective_limit}")
            
            # Fetch messages sorted by timestamp descending to get most recent first
            messages = await self.database_service.find_many(
                self.collection_name,
                query,
                sort=[("timestamp", -1)],  # Descending to get latest messages first
                limit=effective_limit
            )
            
            # Reverse to get chronological order
            messages.reverse()
            
            # Remove noisy retrieval logging - only debug level  
            if self.verbose:
                logger.debug(f"Retrieved {len(messages)} messages for session {session_id}")
            
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
            
            collection = self.database_service.get_collection(self.collection_name)
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
            collection = self.database_service.get_collection(self.collection_name)
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

    async def clear_conversation_history(
        self,
        session_id: str,
        api_key: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clear conversation history for a specific session with mandatory API key validation.

        Args:
            session_id: Session identifier to clear (required)
            api_key: API key for validation and authorization (required)
            user_id: Optional user ID for additional validation

        Returns:
            Dictionary containing operation result and statistics
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "Chat history service is disabled",
                "deleted_count": 0
            }

        if not session_id:
            return {
                "success": False,
                "error": "Session ID is required",
                "deleted_count": 0
            }

        if not api_key:
            return {
                "success": False,
                "error": "API key is required",
                "deleted_count": 0
            }

        try:
            if hasattr(self, "api_key_service") and self.api_key_service:
                is_valid, adapter_name, _ = await self.api_key_service.validate_api_key(api_key)
                if not is_valid:
                    return {
                        "success": False,
                        "error": "Invalid API key",
                        "deleted_count": 0
                    }
            else:
                return {
                    "success": False,
                    "error": "API key service not available",
                    "deleted_count": 0
                }

            collection = self.database_service.get_collection(self.collection_name)
            result = await collection.delete_many({"session_id": session_id})

            self._active_sessions.pop(session_id, None)
            self._session_message_counts.pop(session_id, None)

            if self.verbose:
                logger.info(
                    "Cleared conversation history for session %s: %s messages deleted",
                    session_id,
                    result.deleted_count
                )

            return {
                "success": True,
                "session_id": session_id,
                "deleted_count": result.deleted_count,
                "api_key_validated": True,
                "adapter_name": adapter_name,
                "timestamp": datetime.now(UTC).isoformat()
            }

        except Exception as exc:
            logger.error(
                "Error clearing conversation history for session %s: %s",
                session_id,
                str(exc)
            )
            return {
                "success": False,
                "error": str(exc),
                "deleted_count": 0
            }
    
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
            collection = self.database_service.get_collection(self.collection_name)
            
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
            collection = self.database_service.get_collection(self.collection_name)
            
            # Use aggregation to get count atomically
            pipeline = [
                {"$match": {"session_id": session_id}},
                {"$count": "total"}
            ]
            result = await collection.aggregate(pipeline).to_list(1)
            message_count = result[0]["total"] if result else 0
            
            # Update cache
            self._session_message_counts[session_id] = message_count
            
            if self.verbose:
                logger.info(f"Session {session_id}: Current message count = {message_count}, Limit = {self.max_conversation_messages}")
            
            if message_count >= self.max_conversation_messages:
                # Calculate how many messages to archive (keep 90% instead of 80%)
                keep_count = int(self.max_conversation_messages * 0.9)
                archive_count = message_count - keep_count
                
                if self.verbose:
                    logger.info(f"Session {session_id}: ARCHIVING TRIGGERED - Need to archive {archive_count} messages, keeping {keep_count} most recent")
                
                if archive_count > 0:
                    # Simplified archive operation without transactions
                    # since $merge cannot be used in transactions
                    try:
                        collection = self.database_service.get_collection(self.collection_name)
                        archive_collection = self.database_service.get_collection(f"{self.collection_name}_archive")
                        
                        # Find oldest messages to archive
                        messages_to_archive = await collection.find(
                            {"session_id": session_id}
                        ).sort("timestamp", 1).limit(archive_count).to_list(length=None)
                        
                        if messages_to_archive:
                            if self.verbose:
                                # Show details of messages being archived
                                logger.info(f"Session {session_id}: Found {len(messages_to_archive)} messages to archive:")
                                for i, msg in enumerate(messages_to_archive):
                                    timestamp_str = msg.get('timestamp', 'unknown').strftime('%Y-%m-%d %H:%M:%S') if msg.get('timestamp') else 'unknown'
                                    role = msg.get('role', 'unknown')
                                    content_preview = msg.get('content', '')[:50] + "..." if len(msg.get('content', '')) > 50 else msg.get('content', '')
                                    logger.info(f"  [{i+1}] {timestamp_str} - {role}: {content_preview}")
                            
                            # Insert into archive collection
                            await archive_collection.insert_many(messages_to_archive)
                            
                            if self.verbose:
                                logger.info(f"Session {session_id}: Successfully moved {len(messages_to_archive)} messages to archive collection")
                            
                            # Delete from main collection
                            message_ids = [msg["_id"] for msg in messages_to_archive]
                            delete_result = await collection.delete_many({"_id": {"$in": message_ids}})
                            
                            if self.verbose:
                                logger.info(f"Session {session_id}: Deleted {delete_result.deleted_count} messages from main collection")
                            
                            # Update cache
                            self._session_message_counts[session_id] = keep_count
                            
                            # Verify final state
                            if self.verbose:
                                final_count = await collection.count_documents({"session_id": session_id})
                                logger.info(f"Session {session_id}: ARCHIVING COMPLETE - Final message count: {final_count}/{self.max_conversation_messages}")
                                logger.info(f"Session {session_id}: Sliding window now contains most recent {final_count} messages")
                                
                    except Exception as e:
                        logger.error(f"Session {session_id}: Error during archive operation: {str(e)}")
                        # Continue without archiving to prevent blocking new messages
                        pass
            else:
                if self.verbose:
                    remaining_capacity = self.max_conversation_messages - message_count
                    logger.debug(f"Session {session_id}: No archiving needed - {remaining_capacity} messages remaining before limit")
                
        except Exception as e:
            logger.error(f"Error checking conversation limits: {str(e)}")
            raise
    
    async def _cleanup_old_conversations(self) -> None:
        """Background task to clean up old conversations"""
        while True:
            try:
                if self.retention_days > 0:
                    cutoff_date = datetime.now(UTC) - timedelta(days=self.retention_days)

                    # Find old messages
                    old_messages = await self.database_service.find_many(
                        self.collection_name,
                        {"timestamp": {"$lt": cutoff_date}},
                        limit=10000  # Process in batches
                    )

                    # Extract unique session IDs
                    sessions_to_clean = set()
                    for msg in old_messages:
                        if "session_id" in msg:
                            sessions_to_clean.add(msg["session_id"])

                    total_deleted = 0
                    for session_id in sessions_to_clean:
                        # Delete old messages for this session
                        deleted = await self.database_service.delete_many(
                            self.collection_name,
                            {
                                "session_id": session_id,
                                "timestamp": {"$lt": cutoff_date}
                            }
                        )
                        total_deleted += deleted

                        # Check if any messages remain for this session
                        remaining = await self.database_service.find_many(
                            self.collection_name,
                            {"session_id": session_id},
                            limit=1
                        )
                        if not remaining:
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
            
        # Use the actual conversation limit, not default_limit (which is for API pagination)
        # This ensures we get all available conversation messages after archiving
        effective_limit = max_messages or self.max_conversation_messages
        
        # Get conversation history
        messages = await self.get_conversation_history(
            session_id=session_id,
            limit=effective_limit,
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
            # Test database connection by doing a simple query
            await self.database_service.find_one(self.collection_name, {})

            return {
                "status": "healthy",
                "database": "connected",
                "enabled": self.enabled,
                "active_sessions": len(self._active_sessions),
                "tracked_sessions": len(self._session_message_counts)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "database": "disconnected",
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
            collection = self.database_service.get_collection(self.collection_name)
            
            # Get today's message count
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await collection.count_documents({"timestamp": {"$gte": today_start}})
            
            # Get archive collection metrics
            archive_collection = self.database_service.get_collection(f"{self.collection_name}_archive")
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
            cutoff = datetime.now(UTC) - timedelta(hours=24)
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
