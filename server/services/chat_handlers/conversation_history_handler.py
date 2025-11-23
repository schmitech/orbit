"""
Conversation History Handler

Manages conversation history operations including context retrieval,
storage, and limit checking.
"""

import logging
from typing import Dict, Any, Optional, List

from utils import is_true_value

logger = logging.getLogger(__name__)


class ConversationHistoryHandler:
    """Handles all conversation history related operations."""

    def __init__(
        self,
        config: Dict[str, Any],
        chat_history_service=None,
        adapter_manager=None
    ):
        """
        Initialize the conversation history handler.

        Args:
            config: Application configuration
            chat_history_service: Optional chat history service instance
            adapter_manager: Optional adapter manager for checking adapter types
        """
        self.config = config
        self.chat_history_service = chat_history_service
        self.adapter_manager = adapter_manager

        # Chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self._base_enabled = is_true_value(
            self.chat_history_config.get('enabled', True)
        )

        # Messages configuration for warnings
        self.messages_config = config.get('messages', {})

    def should_enable(self, adapter_name: str) -> bool:
        """
        Determine if chat history should be enabled based on adapter type.

        Args:
            adapter_name: The name of the adapter being used

        Returns:
            True if chat history should be enabled, False otherwise
        """
        # If base chat history is disabled in config, always return False
        if not self._base_enabled:
            return False

        # Check adapter type - enable for passthrough adapters and retriever adapters (for threading support)
        if adapter_name and self.adapter_manager:
            adapter_config = self.adapter_manager.get_adapter_config(adapter_name)
            if adapter_config:
                adapter_type = adapter_config.get('type')
                # Enable for passthrough adapters (conversational)
                if adapter_type == 'passthrough':
                    return True
                # Enable for retriever adapters (intent/QA) to support threading
                if adapter_type == 'retriever':
                    return True

        # Disable for all other adapters
        return False

    async def get_context(
        self,
        session_id: Optional[str],
        adapter_name: str
    ) -> List[Dict[str, str]]:
        """
        Get conversation context from history for the current session.

        Args:
            session_id: The session identifier
            adapter_name: The adapter being used

        Returns:
            List of previous messages formatted for LLM context
        """
        if not self.should_enable(adapter_name) or not self.chat_history_service or not session_id:
            return []

        try:
            # Get context messages from chat history using rolling window query
            # No need to check limits - rolling window query naturally enforces token budget
            context_messages = await self.chat_history_service.get_context_messages(session_id)

            if context_messages:
                logger.debug(f"Retrieved {len(context_messages)} context messages for session {session_id}")

            return context_messages

        except Exception as e:
            logger.error(f"Error retrieving conversation context: {str(e)}")
            return []

    async def store_turn(
        self,
        session_id: Optional[str],
        user_message: str,
        assistant_response: str,
        adapter_name: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> tuple[Optional[Any], Optional[Any]]:
        """
        Store a conversation turn in chat history.

        Args:
            session_id: Session identifier
            user_message: The user's message
            assistant_response: The assistant's response
            adapter_name: The adapter being used
            user_id: Optional user identifier
            api_key: Optional API key
            metadata: Optional metadata to store

        Returns:
            Tuple of (user_message_id, assistant_message_id)
        """
        # Always store if chat history service is available and session_id is provided
        # This is needed for threading support even if chat history context is disabled
        # Check if we should enable context retrieval (for get_context), but always store for threading
        if not self.chat_history_service or not session_id:
            return None, None

        # Check if metadata contains retrieved_docs (for threading support)
        # If so, always store even if chat history context is disabled
        has_retrieved_docs = metadata and metadata.get('retrieved_docs')
        should_store = self.should_enable(adapter_name) or has_retrieved_docs

        if not should_store:
            return None, None

        try:
            result = await self.chat_history_service.add_conversation_turn(
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_response,
                user_id=user_id,
                api_key=api_key,
                metadata=metadata
            )

            logger.debug(f"Stored conversation turn for session {session_id} (threading={has_retrieved_docs})")

            return result

        except Exception as e:
            logger.error(f"Error storing conversation turn: {str(e)}")
            return None, None

    async def check_limit_warning(
        self,
        session_id: Optional[str],
        adapter_name: str
    ) -> Optional[str]:
        """
        Check if the conversation is approaching the limit and return a warning if needed.

        Args:
            session_id: The session identifier
            adapter_name: The adapter being used

        Returns:
            Warning message if approaching limit, None otherwise
        """
        if not self.should_enable(adapter_name) or not self.chat_history_service or not session_id:
            return None

        try:
            # Use token-based limits - calculate tokens that would actually be included
            # in the rolling window query, not total session tokens
            current_tokens = await self.chat_history_service._get_rolling_window_token_count(session_id)
            
            max_tokens = getattr(self.chat_history_service, "max_token_budget", 0) or 0
            if max_tokens <= 0:
                return None
            
            threshold = int(max_tokens * 0.9)  # Warn at 90% of token budget

            if current_tokens >= threshold:
                warning_template = self.messages_config.get(
                    'conversation_limit_warning',
                    "⚠️ **WARNING**: This conversation is using {current_tokens}/{max_tokens} tokens. "
                    "Older messages will be automatically excluded from context to stay within limits. "
                    "Consider starting a new conversation if you want to preserve the full context."
                )

                # Format warning with token-based placeholders
                try:
                    return warning_template.format(
                        current_tokens=current_tokens,
                        max_tokens=max_tokens
                    )
                except KeyError as e:
                    # If template uses unexpected placeholders, fall back to default
                    logger.warning(f"Invalid placeholder in conversation_limit_warning template: {e}")
                    return (
                        f"⚠️ **WARNING**: This conversation is using "
                        f"{current_tokens}/{max_tokens} tokens. Older messages will be dropped soon."
                    )

            return None

        except Exception as e:
            logger.error(f"Error checking conversation limit: {str(e)}")
            return None
