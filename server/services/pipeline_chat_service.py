"""
Pipeline-based Chat Service

This module provides a new chat service implementation using the pipeline architecture
with clean, direct provider implementations.
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
from bson import ObjectId
import threading
from queue import Queue

from utils.text_utils import fix_text_formatting, mask_api_key
from utils import is_true_value
from inference.pipeline import ProcessingContext
from inference.pipeline_factory import PipelineFactory

# Configure logging
logger = logging.getLogger(__name__)

class PipelineChatService:
    """
    Pipeline-based chat service for processing chat messages.
    
    This service uses the new pipeline architecture with clean
    provider implementations, avoiding legacy compatibility layers.
    """
    
    def __init__(self, config: Dict[str, Any], logger_service, 
                 chat_history_service=None, llm_guard_service=None, moderator_service=None,
                 retriever=None, reranker_service=None, prompt_service=None):
        """
        Initialize the pipeline chat service.
        
        Args:
            config: Application configuration
            logger_service: Logger service
            chat_history_service: Optional chat history service
            llm_guard_service: Optional LLM Guard service
            moderator_service: Optional moderator service
            retriever: Optional retriever service
            reranker_service: Optional reranker service
            prompt_service: Optional prompt service
        """
        self.config = config
        self.verbose = is_true_value(config.get('general', {}).get('verbose', False))
        
        # Chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self.chat_history_enabled = is_true_value(self.chat_history_config.get('enabled', True))
        
        # Messages configuration
        self.messages_config = config.get('messages', {})
        
        # Create pipeline factory and pipeline
        self.pipeline_factory = PipelineFactory(config)
        
        # Create adapter manager for dynamic retrieval
        from services.dynamic_adapter_manager import DynamicAdapterManager
        adapter_manager = DynamicAdapterManager(config)
        
        self.pipeline = self.pipeline_factory.create_pipeline_with_services(
            retriever=retriever,
            reranker_service=reranker_service,
            prompt_service=prompt_service,
            llm_guard_service=llm_guard_service,
            moderator_service=moderator_service,
            chat_history_service=chat_history_service,
            logger_service=logger_service,
            adapter_manager=adapter_manager
        )
        
        # Store pipeline reference for async initialization
        self._pipeline_initialized = False
        
        # Store services for direct access
        self.logger_service = logger_service
        self.chat_history_service = chat_history_service
        self.llm_guard_service = llm_guard_service
        self.moderator_service = moderator_service
        
        # Thread-safe queue for streaming responses
        self._stream_queues = {}
        self._stream_locks = {}
        
        if self.verbose:
            logger.info("Pipeline-based chat service initialized with clean providers")
    
    async def initialize(self):
        """Initialize the pipeline provider."""
        if not self._pipeline_initialized:
            await self.pipeline_factory.initialize_provider(self.pipeline.container)
            self._pipeline_initialized = True
            logger.info("Pipeline provider initialized")
    
    async def _get_conversation_context(self, session_id: Optional[str]) -> List[Dict[str, str]]:
        """
        Get conversation context from history for the current session.
        
        Args:
            session_id: The session identifier
            
        Returns:
            List of previous messages formatted for LLM context
        """
        if not self.chat_history_enabled or not self.chat_history_service or not session_id:
            return []
            
        try:
            # Check conversation limits BEFORE retrieving context
            await self.chat_history_service._check_conversation_limits(session_id)
            
            # Get context messages from chat history
            context_messages = await self.chat_history_service.get_context_messages(session_id)
            
            if self.verbose and context_messages:
                logger.info(f"Retrieved {len(context_messages)} context messages for session {session_id}")
                
            return context_messages
            
        except Exception as e:
            logger.error(f"Error retrieving conversation context: {str(e)}")
            return []
    
    async def _store_conversation_turn(
        self,
        session_id: Optional[str],
        user_message: str,
        assistant_response: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store a conversation turn in chat history.
        
        Args:
            session_id: Session identifier
            user_message: The user's message
            assistant_response: The assistant's response
            user_id: Optional user identifier
            api_key: Optional API key
            metadata: Optional metadata to store
        """
        if not self.chat_history_enabled or not self.chat_history_service or not session_id:
            return
            
        try:
            await self.chat_history_service.add_conversation_turn(
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_response,
                user_id=user_id,
                api_key=api_key,
                metadata=metadata
            )
            
            if self.verbose:
                logger.info(f"Stored conversation turn for session {session_id}")
                
        except Exception as e:
            logger.error(f"Error storing conversation turn: {str(e)}")
    
    async def _log_conversation(self, query: str, response: str, client_ip: str, 
                              api_key: Optional[str] = None, session_id: Optional[str] = None, 
                              user_id: Optional[str] = None):
        """Log conversation asynchronously."""
        try:
            await self.logger_service.log_conversation(
                query=query,
                response=response,
                ip=client_ip,
                backend=None,
                blocked=False,
                api_key=api_key,
                session_id=session_id,
                user_id=user_id
            )
        except Exception as e:
            logger.error(f"Error logging conversation: {str(e)}", exc_info=True)
    
    async def _log_request_details(self, message: str, client_ip: str, adapter_name: str, 
                                  system_prompt_id: Optional[ObjectId], api_key: Optional[str],
                                  session_id: Optional[str], user_id: Optional[str]):
        """Log detailed request information for debugging."""
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
    
    async def _check_conversation_limit_warning(self, session_id: Optional[str]) -> Optional[str]:
        """
        Check if the conversation is approaching the limit and return a warning if needed.
        
        Args:
            session_id: The session identifier
            
        Returns:
            Warning message if approaching limit, None otherwise
        """
        if not self.chat_history_enabled or not self.chat_history_service or not session_id:
            return None
            
        try:
            current_count = self.chat_history_service._session_message_counts.get(session_id, 0)
            max_messages = self.chat_history_service.max_conversation_messages
            
            if current_count + 2 == max_messages:
                warning_template = self.messages_config.get(
                    'conversation_limit_warning',
                    "⚠️ **WARNING**: This conversation will reach {max_messages} messages after this response. "
                    "The next exchange will automatically archive older messages. "
                    "Consider starting a new conversation if you want to preserve the full context."
                )
                return warning_template.format(max_messages=max_messages)
                
            return None
            
        except Exception as e:
            logger.error(f"Error checking conversation limit: {str(e)}")
            return None
    
    async def process_chat(self, message: str, client_ip: str, adapter_name: str, 
                          system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                          session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a chat message using the pipeline architecture.
        
        Args:
            message: The chat message
            client_ip: Client IP address
            adapter_name: Adapter name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
            api_key: Optional API key for authentication
            session_id: Optional session identifier for chat history
            user_id: Optional user identifier
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            # Ensure pipeline is initialized
            await self.initialize()
            
            # Log request details
            await self._log_request_details(message, client_ip, adapter_name, system_prompt_id, 
                                           api_key, session_id, user_id)
            
            # Get conversation context
            context_messages = await self._get_conversation_context(session_id)
            
            # Create processing context
            context = ProcessingContext(
                message=message,
                adapter_name=adapter_name,
                system_prompt_id=str(system_prompt_id) if system_prompt_id else None,
                context_messages=context_messages,
                user_id=user_id,
                session_id=session_id,
                api_key=api_key
            )
            
            # Process through pipeline
            result = await self.pipeline.process(context)
            
            # Handle errors
            if result.has_error():
                error_msg = result.error or "Pipeline processing failed"
                logger.error(f"Pipeline error: {error_msg}")
                return {"error": error_msg}
            
            # Get response and clean it
            response = fix_text_formatting(result.response)
            
            # Check for conversation limit warning
            warning = await self._check_conversation_limit_warning(session_id)
            if warning:
                response = f"{response}\n\n---\n{warning}"
            
            # Store conversation turn
            if session_id:
                await self._store_conversation_turn(
                    session_id=session_id,
                    user_message=message,
                    assistant_response=response,
                    user_id=user_id,
                    api_key=api_key,
                    metadata={
                        "adapter_name": adapter_name,
                        "client_ip": client_ip,
                        "pipeline_processing_time": result.processing_time
                    }
                )
            
            # Log conversation (always log, not just when API key is present)
            await self._log_conversation(message, response, client_ip, api_key, session_id, user_id)
            
            # Return response in expected format
            return {
                "response": response,
                "sources": result.sources,
                "metadata": {
                    **result.metadata,
                    "processing_time": result.processing_time,
                    "pipeline_used": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing chat with pipeline: {str(e)}")
            return {"error": str(e)}
    
    async def process_chat_stream(self, message: str, client_ip: str, adapter_name: str, 
                                 system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                                 session_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Process a chat message with streaming response using the pipeline architecture.
        
        Args:
            message: The chat message
            client_ip: Client IP address
            adapter_name: Adapter name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
            api_key: Optional API key for authentication
            session_id: Optional session identifier for chat history
            user_id: Optional user identifier
            
        Yields:
            Streaming response chunks
        """
        try:
            # Ensure pipeline is initialized
            await self.initialize()
            
            # Log request details
            await self._log_request_details(message, client_ip, adapter_name, system_prompt_id, 
                                           api_key, session_id, user_id)
            
            # Get conversation context
            context_messages = await self._get_conversation_context(session_id)
            
            # Create processing context
            context = ProcessingContext(
                message=message,
                adapter_name=adapter_name,
                system_prompt_id=str(system_prompt_id) if system_prompt_id else None,
                context_messages=context_messages,
                user_id=user_id,
                session_id=session_id,
                api_key=api_key
            )
            
            # Buffer to accumulate the complete response
            accumulated_text = ""
            sources = []
            stream_completed_successfully = False
            
            try:
                # Process through pipeline with streaming
                async for chunk in self.pipeline.process_stream(context):
                    try:
                        chunk_data = json.loads(chunk)
                        
                        # Handle errors
                        if "error" in chunk_data:
                            yield f"data: {chunk}\n\n"
                            return
                        
                        # Stream immediately
                        yield f"data: {chunk}\n\n"
                        
                        # Accumulate content
                        if "response" in chunk_data:
                            accumulated_text += chunk_data["response"]
                        
                        # Handle sources
                        if "sources" in chunk_data:
                            sources = chunk_data["sources"]
                        
                        # Handle done marker
                        if chunk_data.get("done", False):
                            stream_completed_successfully = True
                            break
                            
                    except json.JSONDecodeError:
                        # Still yield the chunk even if we can't parse it
                        yield f"data: {chunk}\n\n"
                        continue
                
                # Post-stream processing
                if accumulated_text and stream_completed_successfully:
                    # Clean response
                    final_response = fix_text_formatting(accumulated_text)
                    
                    # Check for conversation limit warning
                    warning = await self._check_conversation_limit_warning(session_id)
                    if warning:
                        final_response = f"{final_response}\n\n---\n{warning}"
                        
                        # Send warning as additional chunk
                        warning_chunk = json.dumps({
                            "response": f"\n\n---\n{warning}",
                            "done": False
                        })
                        yield f"data: {warning_chunk}\n\n"
                    
                    # Store conversation turn
                    if session_id:
                        await self._store_conversation_turn(
                            session_id=session_id,
                            user_message=message,
                            assistant_response=final_response,
                            user_id=user_id,
                            api_key=api_key,
                            metadata={
                                "adapter_name": adapter_name,
                                "client_ip": client_ip,
                                "pipeline_processing_time": context.processing_time
                            }
                        )
                    
                    # Log conversation (always log, not just when API key is present)
                    await self._log_conversation(message, final_response, client_ip, api_key, session_id, user_id)
                    
                    # Send final done marker
                    done_chunk = {"done": True}
                    if sources:
                        done_chunk["sources"] = sources
                    yield f"data: {json.dumps(done_chunk)}\n\n"
                
            except Exception as stream_error:
                logger.error(f"Error in pipeline streaming: {str(stream_error)}")
                error_chunk = json.dumps({
                    "error": f"Stream generation failed: {str(stream_error)}",
                    "done": True
                })
                yield f"data: {error_chunk}\n\n"
                
        except Exception as e:
            logger.error(f"Error processing chat stream with pipeline: {str(e)}")
            error_json = json.dumps({"error": str(e), "done": True})
            yield f"data: {error_json}\n\n" 