"""
Chat History Service
====================

This service manages chat conversation history with database persistence
(supports both MongoDB and SQLite backends).
Simplified version without Redis caching for better maintainability.
"""

import logging
import asyncio
import hashlib
from typing import Dict, Any, Optional, List, Tuple, Callable, TypeVar, Awaitable
from datetime import datetime, timedelta, UTC

from services.database_service import (
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseDuplicateKeyError,
    DatabaseTimeoutError
)
from utils.text_utils import mask_api_key

# Import tokenizer utilities for token counting
try:
    from services.file_processing.chunking.utils import get_tokenizer
except ImportError:
    # Fallback if tokenizer utilities not available
    def get_tokenizer(tokenizer=None):
        class SimpleTokenizer:
            def count_tokens(self, text: str) -> int:
                # Conservative estimate: ~3 characters per token
                return len(text) // 3
        return SimpleTokenizer()

logger = logging.getLogger(__name__)

T = TypeVar('T')

def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    retry_on: tuple = (DatabaseConnectionError, DatabaseTimeoutError, DatabaseOperationError)
):
    """
    Decorator that adds retry logic with exponential backoff

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff in seconds
        max_delay: Maximum delay between retries in seconds
        retry_on: Tuple of database exceptions to retry on
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

    def __init__(self, config: Dict[str, Any], database_service=None, thread_dataset_service=None):
        """
        Initialize the Chat History Service

        Args:
            config: Application configuration
            database_service: Database service instance
            thread_dataset_service: Thread dataset service instance (optional)
        """
        self.config = config
        # Use provided database service or create a new one using factory
        if database_service is None:
            from services.database_service import create_database_service
            database_service = create_database_service(config)
        self.database_service = database_service
        self.api_key_service = None

        # Initialize thread dataset service for proper dataset deletion
        if thread_dataset_service is None:
            from services.thread_dataset_service import ThreadDatasetService
            thread_dataset_service = ThreadDatasetService(config)
        self.thread_dataset_service = thread_dataset_service
        
        # Extract chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self.enabled = self.chat_history_config.get('enabled', True)
        
        # Configuration parameters
        self.default_limit = self.chat_history_config.get('default_limit', 50)
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
        self._session_token_counts = {}  # session_id -> total token count

        # Per-session locks for thread-safe cleanup operations
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # Lock for managing session locks

        self._initialized = False
        
        # Cleanup task handle
        self._cleanup_task = None
        
        # Tokenization configuration
        self.tokenizer_config = self.chat_history_config.get('tokenizer', 'character')
        self._tokenizer = None  # Lazy initialization
        self._tokenization_queue = asyncio.Queue() if self.enabled else None
        self._tokenization_task = None
        
        # Calculate token budget for conversation history
        self.max_token_budget = self._calculate_max_token_budget()

        logger.info(f"Chat History Service initialized with max_token_budget={self.max_token_budget} tokens")
        
    def _get_tokenizer(self):
        """Get or create tokenizer instance (lazy initialization)"""
        if self._tokenizer is None:
            self._tokenizer = get_tokenizer(self.tokenizer_config)
        return self._tokenizer
    
    def _estimate_token_count(self, content: str) -> int:
        """
        Estimate token count for a message (fast, used for immediate storage).
        
        Uses character-based estimation: ~3 characters per token (conservative).
        Actual tokenization happens asynchronously.
        """
        return max(1, len(content) // 3)
    
    def _calculate_max_token_budget(self) -> int:
        """
        Calculate the maximum token budget for conversation history.
        
        Returns:
            Maximum tokens available for conversation history
        """
        try:
            # Get the active inference provider
            inference_provider = self.config.get('general', {}).get('inference_provider', 'ollama')
            inference_config = self.config.get('inference', {}).get(inference_provider, {})
            
            # Extract context window size
            context_window = self._get_context_window_size(inference_provider, inference_config)
            
            # Reserve space for system prompts, current query, and response generation
            # System prompt: ~200 tokens, current query: ~50 tokens, response buffer: ~100 tokens
            reserved_tokens = 350
            
            # Calculate available tokens for conversation history
            available_tokens = max(0, context_window - reserved_tokens)
            
            # Apply safety bounds: minimum 100 tokens, maximum 800,000 tokens (for very large models)
            max_tokens = max(100, min(800000, available_tokens))
            
            logger.debug(
                "Token budget calculation: provider=%s, context_window=%s, "
                "reserved=%s, available=%s, max_budget=%s",
                inference_provider,
                context_window,
                reserved_tokens,
                available_tokens,
                max_tokens,
            )
            
            return max_tokens
            
        except Exception as e:
            logger.warning(f"Error calculating max token budget: {str(e)}. Using fallback value.")
            # Fallback to a reasonable default if calculation fails
            return 4000  # ~40 messages at 100 tokens each
    
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
                logger.debug(
                    "Using configured %s=%s for provider %s",
                    param_name,
                    context_window,
                    provider,
                )
                return context_window
        
        # Second, try alternative parameter names
        alternatives = alternative_params.get(provider, [])
        for alt_param in alternatives:
            if alt_param in provider_config:
                context_window = provider_config[alt_param]
                if isinstance(context_window, int) and context_window > 0:
                    logger.debug(
                        "Using configured %s=%s for provider %s",
                        alt_param,
                        context_window,
                        provider,
                    )
                    return context_window
        
        # Finally, fall back to provider-specific defaults
        default_window = default_context_windows.get(provider, 4096)
        
        logger.debug(
            "No context window configured for %s, using default: %s tokens",
            provider,
            default_window,
        )
            
        return default_window
        
    async def initialize(self) -> None:
        """Initialize the chat history service"""
        if self._initialized:
            return
            
        if not self.enabled:
            logger.info("Chat history service is disabled")
            return
            
        try:
            # Ensure database service is available
            if not self.database_service:
                raise ValueError("Database service is required for chat history")

            # Initialize thread dataset service for proper dataset handling
            if self.thread_dataset_service:
                await self.thread_dataset_service.initialize()

            # Create indexes for efficient querying
            await self._create_indexes()
            
            # Schedule cleanup tasks
            if self.retention_days > 0:
                self._cleanup_task = asyncio.create_task(self._cleanup_old_conversations())
                self._inactive_cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions_periodic())
            
            # Start tokenization background task
            if self._tokenization_queue is not None:
                self._tokenization_task = asyncio.create_task(self._tokenization_worker())
                
            # Start batch backfill task for existing messages without token_count
            if self.enabled:
                asyncio.create_task(self._backfill_token_counts())
                
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
            
            # Create index for token-based queries (for rolling window)
            await self.database_service.create_index(
                self.collection_name,
                [("session_id", 1), ("timestamp", -1), ("token_count", 1)]
            )
            
            logger.debug("Created indexes for chat history collection")
                
        except Exception as e:
            logger.error(f"Error creating indexes: {str(e)}")
            raise
    
    def _generate_message_hash(self, session_id: str, role: str, content: str, timestamp: datetime) -> str:
        """Generate a hash for message deduplication"""
        # Create a unique hash based on session, role, content, and timestamp
        hash_input = f"{session_id}:{role}:{content}:{timestamp.isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    async def _calculate_actual_tokens(self, content: str) -> int:
        """
        Calculate actual token count for a message.
        
        This is the accurate tokenization that happens asynchronously.
        """
        try:
            tokenizer = self._get_tokenizer()
            # Count tokens in content, add overhead for role labels and formatting (~5 tokens)
            token_count = tokenizer.count_tokens(content) + 5
            return max(1, token_count)
        except Exception as e:
            logger.warning(f"Error calculating tokens, using estimate: {str(e)}")
            return self._estimate_token_count(content)
    
    async def _tokenization_worker(self) -> None:
        """
        Background worker that processes tokenization queue.
        
        Calculates actual token counts for messages and updates the database.
        """
        while True:
            try:
                # Get message from queue (with timeout to allow cancellation)
                try:
                    item = await asyncio.wait_for(self._tokenization_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                message_id, content = item
                
                # Calculate actual token count
                actual_token_count = await self._calculate_actual_tokens(content)
                
                # Update message in database
                try:
                    # Get the message to find its session_id for cache update
                    message = await self.database_service.find_one(
                        self.collection_name,
                        {"_id": message_id}
                    )
                    
                    if message:
                        old_token_count = message.get("token_count", 0)
                        session_id = message.get("session_id")
                        
                        # Update token count in database (wrap in $set for MongoDB/SQLite compatibility)
                        await self.database_service.update_one(
                            self.collection_name,
                            {"_id": message_id},
                            {"$set": {"token_count": actual_token_count}}
                        )
                        
                        # Update cache if session_id is available
                        if session_id:
                            # Adjust cache by the difference
                            current_cache = self._session_token_counts.get(session_id, 0)
                            adjustment = actual_token_count - old_token_count
                            self._session_token_counts[session_id] = current_cache + adjustment
                        
                        logger.debug(
                            "Updated token_count for message %s: %s",
                            message_id,
                            actual_token_count,
                        )
                    else:
                        logger.warning(f"Message {message_id} not found for token count update")
                        
                except Exception as e:
                    logger.error(f"Error updating token_count for message {message_id}: {str(e)}")
                
                # Mark task as done
                self._tokenization_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Tokenization worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in tokenization worker: {str(e)}")
                await asyncio.sleep(1)  # Brief pause before retrying
    
    async def _backfill_token_counts(self) -> None:
        """
        Background task to backfill token counts for existing messages.
        
        Processes messages in batches to avoid blocking.
        """
        try:
            # Wait a bit before starting backfill to let service fully initialize
            await asyncio.sleep(5)
            
            logger.debug("Starting token count backfill for existing messages")
            
            batch_size = 100
            processed = 0  # Count of messages actually updated
            offset = 0     # Monotonically increasing offset for pagination
            
            while True:
                # Fetch messages in batches (backend-agnostic approach)
                # We'll filter in Python to avoid backend-specific query syntax
                # Use offset (not processed) to ensure we scan all messages
                messages = await self.database_service.find_many(
                    self.collection_name,
                    {},  # Fetch all messages, filter in Python
                    limit=batch_size,
                    skip=offset
                )
                
                if not messages:
                    # No more messages to process
                    if processed > 0:
                        logger.debug(
                            "Token count backfill complete: processed %s messages",
                            processed,
                        )
                    break
                
                # Process batch - only update messages without token_count
                batch_processed = 0
                for msg in messages:
                    message_id = msg.get("_id")
                    content = msg.get("content", "")
                    token_count = msg.get("token_count")
                    
                    # Skip if token_count already exists and is not None
                    if token_count is not None:
                        continue
                    
                    if message_id and content:
                        # Calculate actual token count
                        actual_token_count = await self._calculate_actual_tokens(content)
                        
                        # Update message (wrap in $set for MongoDB/SQLite compatibility)
                        try:
                            await self.database_service.update_one(
                                self.collection_name,
                                {"_id": message_id},
                                {"$set": {"token_count": actual_token_count}}
                            )
                            processed += 1
                            batch_processed += 1
                        except Exception as e:
                            logger.warning(f"Error updating token_count for message {message_id}: {str(e)}")
                
                # Always advance offset by batch size to scan all messages
                # Don't break early - continue scanning even if current batch had no updates
                offset += batch_size
                
                # Small delay between batches to avoid overwhelming the system
                await asyncio.sleep(0.1)
                
                # Safety check: if we've processed a very large number, log and continue
                if offset > 100000:
                    logger.debug(
                        "Token count backfill: scanned %s messages, updated %s",
                        offset,
                        processed,
                    )
                
        except asyncio.CancelledError:
            logger.info("Token count backfill cancelled")
        except Exception as e:
            logger.error(f"Error in token count backfill: {str(e)}")
    
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
    ) -> Optional[Any]:
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
            Database ID of the inserted message, or None if disabled/failed
        """
        if not self.enabled:
            return None
            
        try:
            # Prepare message document
            timestamp = datetime.now(UTC)
            
            # Estimate token count immediately (fast, non-blocking)
            estimated_token_count = self._estimate_token_count(content)
            
            message_doc = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "token_count": estimated_token_count  # Store estimate immediately
            }
            
            # Add optional fields
            if user_id:
                message_doc["user_id"] = user_id
                
            if api_key:
                message_doc["api_key"] = mask_api_key(api_key, show_last=True, num_chars=6)
                
            if metadata and self.store_metadata:
                message_doc["metadata"] = metadata
            
            # Add deduplication hash
            if idempotency_key:
                message_doc["message_hash"] = idempotency_key
            else:
                message_doc["message_hash"] = self._generate_message_hash(
                    session_id, role, content, timestamp
                )
            
            # Insert into database with duplicate handling
            try:
                message_id = await self.database_service.insert_one(
                    self.collection_name,
                    message_doc
                )
                
                # Update session tracking
                self._active_sessions[session_id] = timestamp

                # Update token count cache (using estimate for now)
                self._session_token_counts[session_id] = \
                    self._session_token_counts.get(session_id, 0) + estimated_token_count
                
                # Enqueue actual tokenization (non-blocking)
                if self._tokenization_queue is not None and message_id:
                    try:
                        self._tokenization_queue.put_nowait((message_id, content))
                    except asyncio.QueueFull:
                        logger.warning(f"Tokenization queue full, skipping token calculation for message {message_id}")
                
                # Add useful progress logging
                current_tokens = self._session_token_counts.get(session_id, 0)
                logger.debug(
                    "Session %s: %s/%s tokens used (%s)",
                    session_id,
                    current_tokens,
                    self.max_token_budget,
                    role,
                )
                
                # Check if we need to clean up inactive sessions
                if len(self._active_sessions) > self.max_tracked_sessions:
                    await self._cleanup_inactive_sessions()
                
                return message_id

            except DatabaseDuplicateKeyError:
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
    ) -> Tuple[Optional[Any], Optional[Any]]:
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
        
        # Trigger cleanup if session exceeds token budget threshold
        await self._cleanup_excess_messages(session_id)

        return user_msg_id, assistant_msg_id

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """
        Get or create a lock for a specific session.

        This ensures thread-safe cleanup operations per session.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Lock for the session
        """
        async with self._locks_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def _cleanup_excess_messages(self, session_id: str) -> int:
        """
        Delete messages that fall outside the rolling window token budget.

        This method is called after adding new messages to keep the session
        within reasonable bounds. Messages are deleted from oldest to newest
        until the session fits within the token budget.

        Thread-safe: Uses per-session locking to prevent concurrent cleanup.

        Args:
            session_id: Session identifier

        Returns:
            Number of messages deleted
        """
        if not self.enabled:
            return 0

        # Quick check before acquiring lock (avoid lock contention for normal case)
        current_tokens = self._session_token_counts.get(session_id, 0)
        cleanup_threshold = int(self.max_token_budget * 1.2)

        if current_tokens <= cleanup_threshold:
            return 0

        # Acquire per-session lock to prevent concurrent cleanup
        session_lock = await self._get_session_lock(session_id)

        # Use try_lock pattern: if another coroutine is already cleaning up, skip
        if session_lock.locked():
            logger.debug(
                "Session %s cleanup already in progress, skipping",
                session_id,
            )
            return 0

        async with session_lock:
            try:
                # Re-check after acquiring lock (another coroutine may have cleaned up)
                current_tokens = self._session_token_counts.get(session_id, 0)

                if current_tokens <= cleanup_threshold:
                    return 0

                logger.debug(
                    "Session %s exceeds cleanup threshold (%s/%s tokens), starting cleanup",
                    session_id,
                    current_tokens,
                    cleanup_threshold,
                )

                # Fetch all messages for session, ordered by timestamp ASC (oldest first)
                all_messages = await self.database_service.find_many(
                    self.collection_name,
                    {"session_id": session_id},
                    sort=[("timestamp", 1)],  # Oldest first
                    limit=10000  # Reasonable upper bound
                )

                if not all_messages:
                    return 0

                # Calculate which messages to keep (from newest, within budget)
                # Work backwards from newest to oldest
                messages_reversed = list(reversed(all_messages))
                accumulated_tokens = 0
                keep_count = 0

                for msg in messages_reversed:
                    token_count = msg.get("token_count")
                    if token_count is None:
                        content = msg.get("content", "")
                        token_count = self._estimate_token_count(content)

                    if accumulated_tokens + token_count > self.max_token_budget:
                        break

                    accumulated_tokens += token_count
                    keep_count += 1

                # Calculate how many to delete (oldest messages)
                delete_count = len(all_messages) - keep_count

                if delete_count <= 0:
                    return 0

                # Get IDs of messages to delete (oldest ones)
                messages_to_delete = all_messages[:delete_count]
                deleted_ids = [msg.get("_id") for msg in messages_to_delete if msg.get("_id")]

                # Calculate tokens being removed for cache update
                tokens_removed = 0
                for msg in messages_to_delete:
                    token_count = msg.get("token_count")
                    if token_count is None:
                        content = msg.get("content", "")
                        token_count = self._estimate_token_count(content)
                    tokens_removed += token_count

                # Delete messages in batches
                actual_deleted = 0
                for msg_id in deleted_ids:
                    try:
                        deleted = await self.database_service.delete_one(
                            self.collection_name,
                            {"_id": msg_id}
                        )
                        if deleted:
                            actual_deleted += 1
                    except Exception as e:
                        logger.warning(f"Error deleting message {msg_id}: {str(e)}")

                # Update cache atomically within the lock
                if actual_deleted > 0:
                    self._session_token_counts[session_id] = max(
                        0,
                        self._session_token_counts.get(session_id, 0) - tokens_removed
                    )

                    logger.debug(
                        "Cleaned up %s old messages from session %s (freed %s tokens, now %s/%s)",
                        actual_deleted,
                        session_id,
                        tokens_removed,
                        self._session_token_counts.get(session_id, 0),
                        self.max_token_budget,
                    )

                return actual_deleted

            except Exception as e:
                logger.error(f"Error cleaning up excess messages for session {session_id}: {str(e)}")
                return 0

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
            logger.debug(
                "Fetching chat history for session %s with limit %s",
                session_id,
                effective_limit,
            )
            
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
            logger.debug(
                "Retrieved %s messages for session %s",
                len(messages),
                session_id,
            )
            
            # Process messages
            processed_messages = []
            for msg in messages:
                message_id = msg.get("_id") or msg.get("id")
                if message_id is not None:
                    try:
                        message_id = str(message_id)
                    except Exception:
                        message_id = str(message_id)

                processed_msg = {
                    "message_id": message_id,
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
            # Get all messages for the user, sorted by timestamp descending
            messages = await self.database_service.find_many(
                self.collection_name,
                {"user_id": user_id},
                sort=[("timestamp", -1)],
                limit=10000  # reasonable limit to prevent memory issues
            )

            # Group messages by session_id in Python
            sessions_dict = {}
            for msg in messages:
                session_id = msg.get("session_id")
                if not session_id:
                    continue

                if session_id not in sessions_dict:
                    sessions_dict[session_id] = {
                        "messages": [],
                        "last_activity": msg.get("timestamp"),
                        "first_activity": msg.get("timestamp"),
                        "last_message": msg.get("content", ""),
                        "last_role": msg.get("role")
                    }

                sessions_dict[session_id]["messages"].append(msg)
                # Update first_activity (since messages are sorted desc, last one we see is oldest)
                sessions_dict[session_id]["first_activity"] = msg.get("timestamp")

            # Convert to list and calculate stats
            sessions_list = []
            for session_id, data in sessions_dict.items():
                session_data = {
                    "session_id": session_id,
                    "last_activity": data["last_activity"],
                    "first_activity": data["first_activity"],
                    "message_count": len(data["messages"]),
                    "duration_seconds": (
                        data["last_activity"] - data["first_activity"]
                    ).total_seconds() if data["last_activity"] and data["first_activity"] else 0
                }

                if include_summary:
                    # Truncate message preview
                    preview = data.get("last_message", "")[:100]
                    if len(data.get("last_message", "")) > 100:
                        preview += "..."
                    session_data["last_message_preview"] = preview
                    session_data["last_message_role"] = data.get("last_role")

                sessions_list.append(session_data)

            # Sort by last_activity descending
            sessions_list.sort(key=lambda x: x["last_activity"], reverse=True)

            # Apply pagination
            paginated_results = sessions_list[offset:offset + limit]

            return paginated_results

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
            # Delete from database
            deleted_count = await self.database_service.delete_many(
                self.collection_name,
                {"session_id": session_id}
            )

            # Delete any associated threads (cascade delete)
            try:
                # First, get all threads for this session to clean up their datasets
                threads = await self.database_service.find_many(
                    "conversation_threads",
                    {"parent_session_id": session_id}
                )

                datasets_deleted = 0
                thread_sessions_deleted = 0
                # Delete thread datasets using ThreadDatasetService (handles Redis/database)
                if threads:
                    for thread in threads:
                        dataset_key = thread.get('dataset_key')
                        if dataset_key:
                            try:
                                if await self.thread_dataset_service.delete_dataset(dataset_key):
                                    datasets_deleted += 1
                            except Exception:
                                pass  # Dataset might not exist or already deleted

                        # Thread replies live under their own session_id, so delete them too
                        thread_session_id = thread.get('thread_session_id')
                        if thread_session_id:
                            try:
                                deleted = await self.database_service.delete_many(
                                    self.collection_name,
                                    {"session_id": thread_session_id}
                                )
                                thread_sessions_deleted += deleted
                            except Exception as thread_session_error:
                                logger.warning(
                                    "Failed to delete thread session %s: %s",
                                    thread_session_id,
                                    thread_session_error
                                )

                # Delete thread records
                threads_deleted = await self.database_service.delete_many(
                    "conversation_threads",
                    {"parent_session_id": session_id}
                )
                if threads_deleted > 0:
                    logger.debug(
                        "Deleted %s associated threads (%s replies, %s datasets) for session %s",
                        threads_deleted,
                        thread_sessions_deleted,
                        datasets_deleted,
                        session_id,
                    )
            except Exception as thread_error:
                logger.warning(f"Error deleting threads for session {session_id}: {str(thread_error)}")

            # Clear from tracking
            self._active_sessions.pop(session_id, None)
            self._session_token_counts.pop(session_id, None)

            logger.debug(
                "Cleared history for session %s: %s messages",
                session_id,
                deleted_count,
            )

            return deleted_count > 0

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
                # Get adapter manager to check live configs (respects hot-reload)
                adapter_manager = None
                if hasattr(self, 'database_service') and hasattr(self.database_service, 'app_state'):
                    adapter_manager = getattr(self.database_service.app_state, 'adapter_manager', None)

                is_valid, adapter_name, _ = await self.api_key_service.validate_api_key(api_key, adapter_manager)
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

            deleted_count = await self.database_service.delete_many(
                self.collection_name,
                {"session_id": session_id}
            )

            # Delete any associated threads (cascade delete)
            threads_deleted = 0
            thread_messages_deleted = 0
            files_deleted = 0
            try:
                # First, get all threads for this session to clean up their datasets
                threads = await self.database_service.find_many(
                    "conversation_threads",
                    {"parent_session_id": session_id}
                )

                # Extract and delete uploaded files from thread datasets BEFORE deleting the datasets
                # This prevents orphaned chunks in vector stores (Qdrant, ChromaDB, etc.)
                if threads:
                    logger.debug(
                        "Extracting file_ids from %s thread(s) for session %s",
                        len(threads),
                        session_id
                    )
                    file_ids_to_delete = set()  # Use set to avoid duplicates

                    for thread in threads:
                        dataset_key = thread.get('dataset_key')
                        if dataset_key:
                            try:
                                # Get dataset to extract file_ids
                                dataset = await self.thread_dataset_service.get_dataset(dataset_key)
                                if dataset:
                                    query_context, raw_results = dataset
                                    logger.debug(
                                        "Processing dataset %s with %s results",
                                        dataset_key,
                                        len(raw_results) if raw_results else 0
                                    )

                                    # Extract file_ids from raw_results metadata
                                    for result in raw_results:
                                        if isinstance(result, dict):
                                            metadata = result.get('metadata', {})
                                            file_id = metadata.get('file_id')
                                            if file_id:
                                                logger.debug("Found file_id in metadata: %s", file_id)
                                                file_ids_to_delete.add(file_id)

                                            # Also check file_metadata (nested structure)
                                            file_metadata = result.get('file_metadata', {})
                                            if file_metadata and isinstance(file_metadata, dict):
                                                file_id = file_metadata.get('file_id')
                                                if file_id:
                                                    logger.debug("Found file_id in file_metadata: %s", file_id)
                                                    file_ids_to_delete.add(file_id)
                                else:
                                    logger.debug("No dataset found for key %s", dataset_key)
                            except Exception as extract_error:
                                logger.warning(
                                    "Failed to extract file_ids from dataset %s: %s",
                                    dataset_key,
                                    extract_error
                                )

                    # Delete files using FileProcessingService (handles vector store cleanup)
                    if file_ids_to_delete:
                        logger.debug(
                            "Found %s unique file(s) to delete for session %s: %s",
                            len(file_ids_to_delete),
                            session_id,
                            list(file_ids_to_delete)
                        )
                        logger.debug("Starting file deletion from vector stores and storage...")

                        # Get file_processing_service from app_state if available
                        file_processing_service = None
                        if hasattr(self, 'database_service') and hasattr(self.database_service, 'app_state'):
                            file_processing_service = getattr(self.database_service.app_state, 'file_processing_service', None)

                        if file_processing_service:
                            for file_id in file_ids_to_delete:
                                try:
                                    # Delete file and its chunks from vector store
                                    deleted = await file_processing_service.delete_file(file_id, api_key)
                                    if deleted:
                                        files_deleted += 1
                                        logger.debug("✓ Deleted file %s and its chunks from vector store", file_id)
                                    else:
                                        logger.warning("✗ Failed to delete file %s (may not exist)", file_id)
                                except Exception as file_delete_error:
                                    logger.warning(
                                        "✗ Error deleting file %s: %s",
                                        file_id,
                                        file_delete_error
                                    )
                            logger.debug("Completed file deletion: %s/%s files successfully deleted", files_deleted, len(file_ids_to_delete))
                        else:
                            logger.warning(
                                "FileProcessingService not available - files will not be deleted. "
                                "This may leave orphaned chunks in vector stores."
                            )
                    else:
                        logger.debug("No uploaded files found for session %s", session_id)

                # Delete thread datasets using ThreadDatasetService (handles Redis/database)
                datasets_deleted = 0
                if threads:
                    for thread in threads:
                        dataset_key = thread.get('dataset_key')
                        if dataset_key:
                            try:
                                result = await self.thread_dataset_service.delete_dataset(dataset_key)
                                if result:
                                    datasets_deleted += 1
                            except Exception:
                                pass  # Dataset might not exist or already deleted

                        # Remove chat history rows that belong to the thread session itself
                        thread_session_id = thread.get('thread_session_id')
                        if thread_session_id:
                            try:
                                deleted = await self.database_service.delete_many(
                                    self.collection_name,
                                    {"session_id": thread_session_id}
                                )
                                thread_messages_deleted += deleted
                            except Exception as thread_session_error:
                                logger.warning(
                                    "Failed to delete thread session history %s: %s",
                                    thread_session_id,
                                    thread_session_error
                                )

                # Delete thread records
                threads_deleted = await self.database_service.delete_many(
                    "conversation_threads",
                    {"parent_session_id": session_id}
                )
                if threads_deleted > 0:
                    logger.debug(
                        "Deleted %s associated threads, %s datasets, %s files, and %s thread messages for session %s",
                        threads_deleted,
                        datasets_deleted,
                        files_deleted,
                        thread_messages_deleted,
                        session_id,
                    )
            except Exception as thread_error:
                logger.warning(f"Error deleting threads for session {session_id}: {str(thread_error)}")

            self._active_sessions.pop(session_id, None)
            self._session_token_counts.pop(session_id, None)

            logger.debug(
                "Cleared conversation history for session %s: %s messages deleted, %s threads deleted, %s files deleted",
                session_id,
                deleted_count,
                threads_deleted,
                files_deleted,
            )

            return {
                "success": True,
                "session_id": session_id,
                "deleted_count": deleted_count,
                "deleted_threads": threads_deleted,
                "deleted_files": files_deleted,
                "deleted_thread_messages": thread_messages_deleted,
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
            # Get all messages for the session
            messages = await self.database_service.find_many(
                self.collection_name,
                {"session_id": session_id},
                sort=[("timestamp", 1)],  # Sort ascending to get first/last easily
                limit=10000  # reasonable limit
            )

            if not messages:
                return {"session_id": session_id, "message_count": 0}

            # Calculate stats in Python
            message_count = len(messages)
            user_messages = sum(1 for msg in messages if msg.get("role") == "user")
            assistant_messages = sum(1 for msg in messages if msg.get("role") == "assistant")
            total_chars = sum(len(msg.get("content", "")) for msg in messages)
            first_message = messages[0].get("timestamp") if messages else None
            last_message = messages[-1].get("timestamp") if messages else None

            return {
                "session_id": session_id,
                "message_count": message_count,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "first_message": first_message,
                "last_message": last_message,
                "duration_seconds": (
                    last_message - first_message
                ).total_seconds() if last_message and first_message else 0,
                "total_characters": total_chars,
                "avg_message_length": total_chars // message_count if message_count > 0 else 0
            }

        except Exception as e:
            logger.error(f"Error getting session stats: {str(e)}")
            return {"session_id": session_id, "error": str(e)}
    
    async def _get_session_token_count(self, session_id: str) -> int:
        """
        Get total token count for a session (backend-agnostic).
        
        Uses cache if available, otherwise queries database.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Total token count for the session
        """
        # Check cache first
        if session_id in self._session_token_counts:
            return self._session_token_counts[session_id]
        
        # Query database for accurate count
        try:
            messages = await self.database_service.find_many(
                self.collection_name,
                {"session_id": session_id},
                limit=10000  # Reasonable upper bound
            )
            
            # Sum token counts (use estimate if token_count is missing)
            total_tokens = 0
            for msg in messages:
                token_count = msg.get("token_count")
                if token_count is None:
                    # Fallback to estimate if token_count not yet calculated
                    content = msg.get("content", "")
                    token_count = self._estimate_token_count(content)
                total_tokens += token_count
            
            # Update cache
            self._session_token_counts[session_id] = total_tokens
            
            return total_tokens
            
        except Exception as e:
            logger.error(f"Error getting session token count: {str(e)}")
            return 0
    
    async def _get_rolling_window_token_count(self, session_id: str) -> int:
        """
        Get token count for messages that would be included in rolling window query.
        
        This calculates the tokens that would actually be included in context,
        not the total tokens in the session. Uses the same logic as get_context_messages.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Token count for messages that fit within token budget
        """
        if not self.enabled:
            return 0
        
        token_budget = self.max_token_budget
        
        try:
            # Calculate intelligent fetch limit based on token budget
            # Assume conservative minimum of 50 tokens per message
            # Add 20% buffer to account for variation in message sizes
            estimated_messages_needed = int((token_budget / 50) * 1.2)
            # Cap at reasonable maximum to prevent excessive memory usage
            fetch_limit = min(max(estimated_messages_needed, 20), 1000)
            
            # Fetch messages for session, ordered by timestamp DESC (newest first)
            all_messages = await self.database_service.find_many(
                self.collection_name,
                {"session_id": session_id},
                sort=[("timestamp", -1)],  # Newest first
                limit=fetch_limit
            )
            
            # Rolling window: accumulate messages from newest to oldest until token budget reached
            accumulated_tokens = 0
            
            for msg in all_messages:
                # Get token count (use actual if available, otherwise estimate)
                token_count = msg.get("token_count")
                if token_count is None:
                    # Fallback to estimate if token_count not yet calculated
                    content = msg.get("content", "")
                    token_count = self._estimate_token_count(content)
                
                # Check if adding this message would exceed budget
                if accumulated_tokens + token_count > token_budget:
                    # Stop here - we've reached the token budget
                    break
                
                accumulated_tokens += token_count
            
            return accumulated_tokens
            
        except Exception as e:
            logger.error(f"Error getting rolling window token count: {str(e)}")
            return 0
    
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
                            self._session_token_counts.pop(session_id, None)

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
        max_messages: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation messages formatted for LLM context using rolling window query.
        
        This method uses a token-based rolling window approach:
        - Fetches messages from newest to oldest
        - Accumulates tokens until budget is reached
        - Returns messages in chronological order (oldest to newest)
        - No archiving needed - query naturally enforces token budget
        
        Args:
            session_id: Session identifier
            max_messages: Maximum number of messages to include (deprecated, use max_tokens)
            max_tokens: Maximum token budget for context (defaults to max_token_budget)
            
        Returns:
            List of messages formatted for LLM context
        """
        if not self.enabled:
            return []
        
        # Determine token budget
        token_budget = max_tokens or self.max_token_budget

        try:
            # Calculate intelligent fetch limit based on token budget
            # Assume conservative minimum of 50 tokens per message
            # Add 20% buffer to account for variation in message sizes
            estimated_messages_needed = int((token_budget / 50) * 1.2)
            # Cap at reasonable maximum to prevent excessive memory usage
            fetch_limit = min(max(estimated_messages_needed, 20), 1000)

            logger.debug(
                "Fetching up to %s messages for token budget %s",
                fetch_limit,
                token_budget,
            )

            # Fetch messages for session, ordered by timestamp DESC (newest first)
            all_messages = await self.database_service.find_many(
                self.collection_name,
                {"session_id": session_id},
                sort=[("timestamp", -1)],  # Newest first
                limit=fetch_limit
            )
            
            # Rolling window: accumulate messages from newest to oldest until token budget reached
            selected_messages = []
            accumulated_tokens = 0
            
            for msg in all_messages:
                # Get token count (use actual if available, otherwise estimate)
                token_count = msg.get("token_count")
                if token_count is None:
                    # Fallback to estimate if token_count not yet calculated
                    content = msg.get("content", "")
                    token_count = self._estimate_token_count(content)
                
                # Check if adding this message would exceed budget
                if accumulated_tokens + token_count > token_budget:
                    # Stop here - we've reached the token budget
                    break
                
                # Add message to selection
                selected_messages.append(msg)
                accumulated_tokens += token_count
            
            # Reverse to get chronological order (oldest to newest)
            selected_messages.reverse()
            
            logger.debug(
                "Session %s: Selected %s messages using %s/%s tokens",
                session_id,
                len(selected_messages),
                accumulated_tokens,
                token_budget,
            )
            
            # Format for LLM context
            context_messages = []
            for msg in selected_messages:
                role = msg.get("role")
                if role in ["user", "assistant", "system"]:
                    context_messages.append({
                        "role": role,
                        "content": msg.get("content", "")
                    })
            
            return context_messages
            
        except Exception as e:
            logger.error(f"Error getting context messages: {str(e)}")
            return []
    
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
                "tracked_sessions": len(self._session_token_counts)
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
            # Get today's message count using database service
            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            today_messages = await self.database_service.find_many(
                self.collection_name,
                {"timestamp": {"$gte": today_start}},
                limit=100000  # Large limit to get count
            )
            today_count = len(today_messages)

            return {
                "active_sessions": len(self._active_sessions),
                "tracked_sessions": len(self._session_token_counts),
                "messages_today": today_count,
                "oldest_tracked_session": min(self._active_sessions.values()).isoformat() if self._active_sessions else None,
                "max_token_budget": self.max_token_budget,
                "max_tracked_sessions": self.max_tracked_sessions,
                "retention_days": self.retention_days
            }
        except Exception as e:
            logger.error(f"Error getting metrics: {str(e)}")
            return {
                "error": str(e),
                "active_sessions": len(self._active_sessions),
                "tracked_sessions": len(self._session_token_counts)
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
                self._session_token_counts.pop(sid, None)
                self._session_locks.pop(sid, None)  # Clean up session locks

            if inactive:
                logger.debug(
                    "Cleaned up %s inactive sessions from memory tracking",
                    len(inactive),
                )
                
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
        
        # Cancel tokenization task
        if self._tokenization_task:
            self._tokenization_task.cancel()
            try:
                await self._tokenization_task
            except asyncio.CancelledError:
                pass
        
        # Clear tracking
        self._active_sessions.clear()
        self._session_token_counts.clear()
        self._session_locks.clear()

        logger.info("Chat history service closed")
