"""
Response Processor

Handles post-processing of chat responses including text formatting,
warning injection, conversation storage, and logging.
"""

import logging
from typing import Dict, Any, Optional

from utils.text_utils import fix_text_formatting, mask_api_key
from .conversation_history_handler import ConversationHistoryHandler

logger = logging.getLogger(__name__)


class ResponseProcessor:
    """Handles post-processing of chat responses."""

    def __init__(
        self,
        config: Dict[str, Any],
        conversation_handler: ConversationHistoryHandler,
        logger_service,
        verbose: bool = False
    ):
        """
        Initialize the response processor.

        Args:
            config: Application configuration
            conversation_handler: Conversation history handler
            logger_service: Logger service for conversation logging
            verbose: Enable verbose logging
        """
        self.config = config
        self.conversation_handler = conversation_handler
        self.logger_service = logger_service
        self.verbose = verbose

    def format_response(self, text: str) -> str:
        """
        Apply text formatting to clean up response.

        Args:
            text: Raw response text

        Returns:
            Formatted text
        """
        return fix_text_formatting(text)

    def inject_warning(self, response: str, warning: Optional[str]) -> str:
        """
        Inject warning message into response if provided.

        Args:
            response: Original response text
            warning: Optional warning message

        Returns:
            Response with warning appended if provided
        """
        if warning:
            return f"{response}\n\n---\n{warning}"
        return response

    async def log_request_details(
        self,
        message: str,
        client_ip: str,
        adapter_name: str,
        system_prompt_id: Optional[str],
        api_key: Optional[str],
        session_id: Optional[str],
        user_id: Optional[str]
    ) -> None:
        """
        Log detailed request information for debugging.

        Args:
            message: The chat message
            client_ip: Client IP address
            adapter_name: Adapter name being used
            system_prompt_id: System prompt ID
            api_key: API key (will be masked)
            session_id: Session identifier
            user_id: User identifier
        """
        if self.verbose:
            logger.info(f"Processing chat message from {client_ip}, adapter: {adapter_name}")
            logger.info(f"Message: {message}")

            # Mask API key for logging
            masked_api_key = "None"
            if api_key:
                masked_api_key = mask_api_key(api_key, show_last=True)

            logger.info(f"System prompt ID: {system_prompt_id}")
            logger.info(f"API key: {masked_api_key}")
            logger.info(f"Session ID: {session_id}")
            logger.info(f"User ID: {user_id}")

    async def log_conversation(
        self,
        query: str,
        response: str,
        client_ip: str,
        backend: str,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Log conversation asynchronously.

        Args:
            query: User query
            response: Assistant response
            client_ip: Client IP address
            backend: Backend/provider used
            api_key: Optional API key
            session_id: Optional session ID
            user_id: Optional user ID
        """
        try:
            await self.logger_service.log_conversation(
                query=query,
                response=response,
                ip=client_ip,
                backend=backend,
                blocked=False,
                api_key=api_key,
                session_id=session_id,
                user_id=user_id
            )
        except Exception as e:
            logger.error(f"Error logging conversation: {str(e)}", exc_info=True)

    async def process_response(
        self,
        response: str,
        message: str,
        client_ip: str,
        adapter_name: str,
        session_id: Optional[str],
        user_id: Optional[str],
        api_key: Optional[str],
        backend: str,
        processing_time: float,
        retrieved_docs: Optional[list] = None
    ) -> tuple[str, Optional[str]]:
        """
        Complete post-processing of a chat response.

        This includes:
        - Text formatting
        - Warning injection (if approaching conversation limit)
        - Conversation storage
        - Logging

        Args:
            response: Raw response text
            message: Original user message
            client_ip: Client IP address
            adapter_name: Adapter being used
            session_id: Session identifier
            user_id: User identifier
            api_key: API key
            backend: Backend/provider used
            processing_time: Pipeline processing time

        Returns:
            Tuple of (processed_response_text, assistant_message_id)
        """
        # Clean response text
        processed_response = self.format_response(response)

        # Check for conversation limit warning
        warning = await self.conversation_handler.check_limit_warning(session_id, adapter_name)
        processed_response = self.inject_warning(processed_response, warning)

        # Store conversation turn with retrieved_docs in metadata
        # Always store for threading support, even if chat history is disabled for context retrieval
        assistant_message_id = None
        if session_id:
            # Build metadata with retrieved_docs for thread creation
            metadata = {
                "adapter_name": adapter_name,
                "client_ip": client_ip,
                "pipeline_processing_time": processing_time,
                "original_query": message
            }
            
            # Include retrieved_docs if available (for thread creation)
            if retrieved_docs:
                metadata["retrieved_docs"] = retrieved_docs
                # Extract template_id and parameters from first doc if available
                if retrieved_docs and len(retrieved_docs) > 0:
                    first_doc_meta = retrieved_docs[0].get('metadata', {})
                    if first_doc_meta:
                        metadata["template_id"] = first_doc_meta.get('template_id')
                        metadata["parameters_used"] = first_doc_meta.get('parameters_used', {})
            
            # Store turn - this will store metadata even if chat history context is disabled
            # The store_turn method checks should_enable for context retrieval, but we need metadata for threading
            _, assistant_message_id = await self.conversation_handler.store_turn(
                session_id=session_id,
                user_message=message,
                assistant_response=processed_response,
                adapter_name=adapter_name,
                user_id=user_id,
                api_key=api_key,
                metadata=metadata
            )

        # Log conversation
        await self.log_conversation(
            query=message,
            response=processed_response,
            client_ip=client_ip,
            backend=backend,
            api_key=api_key,
            session_id=session_id,
            user_id=user_id
        )

        return processed_response, assistant_message_id

    def build_result(
        self,
        response: str,
        sources: list,
        metadata: Dict[str, Any],
        processing_time: float,
        audio_data: Optional[bytes] = None,
        audio_format: Optional[str] = None,
        assistant_message_id: Optional[str] = None,
        session_id: Optional[str] = None,
        adapter_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build the final result dictionary.

        Args:
            response: Processed response text
            sources: Source documents
            metadata: Additional metadata
            processing_time: Pipeline processing time
            audio_data: Optional audio data
            audio_format: Optional audio format
            assistant_message_id: Optional assistant message ID for threading
            session_id: Optional session ID for threading
            adapter_name: Optional adapter name for threading support detection

        Returns:
            Complete result dictionary
        """
        import base64

        result = {
            "response": response,
            "sources": sources,
            "metadata": {
                **metadata,
                "processing_time": processing_time,
                "pipeline_used": True
            }
        }

        # Add threading metadata if adapter supports it
        if assistant_message_id and session_id and adapter_name:
            # Check if adapter supports threading (intent or QA adapters)
            supports_threading = self._adapter_supports_threading(adapter_name)
            if supports_threading:
                result["threading"] = {
                    "supports_threading": True,
                    "message_id": assistant_message_id,
                    "session_id": session_id
                }

        # Add audio if generated
        if audio_data:
            result["audio"] = base64.b64encode(audio_data).decode('utf-8')
            result["audio_format"] = audio_format or "mp3"

        return result
    
    def _adapter_supports_threading(self, adapter_name: str) -> bool:
        """
        Check if an adapter supports threading.
        
        Args:
            adapter_name: Name of the adapter
            
        Returns:
            True if adapter supports threading (intent or QA adapters)
        """
        if not adapter_name:
            return False
        
        # Intent adapters support threading
        if adapter_name.startswith('intent-'):
            return True
        
        # QA adapters support threading
        if adapter_name.startswith('qa-') or 'qa' in adapter_name.lower():
            return True
        
        # Conversational and multimodal adapters do not support threading
        if 'conversational' in adapter_name.lower() or 'multimodal' in adapter_name.lower():
            return False
        
        return False
