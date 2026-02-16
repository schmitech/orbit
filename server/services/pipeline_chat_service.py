"""
Pipeline-based Chat Service

This module provides a chat service implementation using the pipeline architecture
with clean, direct provider implementations. Delegates to specialized handlers
for better maintainability and single responsibility.
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
from bson import ObjectId

from inference.pipeline_factory import PipelineFactory

from inference.pipeline import ProcessingContext
from .chat_handlers import (
    ConversationHistoryHandler,
    AudioHandler,
    RequestContextBuilder,
    StreamingHandler,
    StreamingState,
    ResponseProcessor
)

# Configure logging
logger = logging.getLogger(__name__)


class PipelineChatService:
    """
    Pipeline-based chat service for processing chat messages.

    This service uses the pipeline architecture with clean
    provider implementations and delegates to specialized handlers
    for conversation history, audio generation, and streaming.
    """

    def __init__(self, config: Dict[str, Any], logger_service,
                 chat_history_service=None, moderator_service=None,
                 retriever=None, reranker_service=None, prompt_service=None, clock_service=None,
                 redis_service=None, adapter_manager=None, audit_service=None,
                 database_service=None, thread_dataset_service=None):
        """
        Initialize the pipeline chat service.

        Args:
            config: Application configuration
            logger_service: Logger service
            chat_history_service: Optional chat history service
            moderator_service: Optional moderator service
            retriever: Optional retriever service
            reranker_service: Optional reranker service
            prompt_service: Optional prompt service
            clock_service: Optional clock service
            redis_service: Optional Redis service for session persistence
            adapter_manager: Optional shared adapter manager (uses app.state.adapter_manager).
            audit_service: Optional audit service for audit trail storage.
                           If provided, config changes during reload will be reflected.
                           If not provided, creates a local instance (backward compatibility).
            database_service: Optional database service (SQLite/MongoDB) for thread operations.
            thread_dataset_service: Optional thread dataset service for conversation threading.
        """
        self.config = config

        # Store services for direct access
        self.logger_service = logger_service
        self.chat_history_service = chat_history_service
        self.moderator_service = moderator_service
        self.clock_service = clock_service
        self.redis_service = redis_service
        self.audit_service = audit_service

        # Create pipeline factory
        self.pipeline_factory = PipelineFactory(config)

        # Use provided adapter manager or create a local one (backward compatibility)
        if adapter_manager is not None:
            # Use the shared adapter manager - config changes during reload will be reflected
            # For FaultTolerantAdapterManager, use base_adapter_manager for handlers
            if hasattr(adapter_manager, 'base_adapter_manager'):
                adapter_manager = adapter_manager.base_adapter_manager
            logger.debug("Using shared adapter manager for pipeline chat service")
        else:
            # Create local adapter manager (backward compatibility, but won't reflect reloads)
            from services.dynamic_adapter_manager import DynamicAdapterManager
            adapter_manager = DynamicAdapterManager(config)
            logger.debug("Created local adapter manager for pipeline chat service")

        # Create pipeline with services
        self.pipeline = self.pipeline_factory.create_pipeline_with_services(
            retriever=retriever,
            reranker_service=reranker_service,
            prompt_service=prompt_service,
            moderator_service=moderator_service,
            chat_history_service=chat_history_service,
            logger_service=logger_service,
            adapter_manager=adapter_manager,
            clock_service=self.clock_service,
            redis_service=self.redis_service,
            database_service=database_service,
            thread_dataset_service=thread_dataset_service
        )

        # Initialize handlers with shared adapter_manager
        self._init_handlers(adapter_manager)

        # Store pipeline reference for async initialization
        self._pipeline_initialized = False

        logger.debug("Pipeline-based chat service initialized with clean providers")

    def _init_handlers(self, adapter_manager) -> None:
        """
        Initialize all specialized handlers.

        Args:
            adapter_manager: The adapter manager instance
        """
        # Conversation history handler
        self.conversation_handler = ConversationHistoryHandler(
            config=self.config,
            chat_history_service=self.chat_history_service,
            adapter_manager=adapter_manager
        )

        # Audio handler
        self.audio_handler = AudioHandler(
            config=self.config,
            adapter_manager=adapter_manager
        )

        # Request context builder
        self.context_builder = RequestContextBuilder(
            config=self.config,
            adapter_manager=adapter_manager
        )

        # Streaming handler (depends on audio handler)
        self.streaming_handler = StreamingHandler(
            config=self.config,
            audio_handler=self.audio_handler
        )

        # Response processor (depends on conversation handler)
        self.response_processor = ResponseProcessor(
            config=self.config,
            conversation_handler=self.conversation_handler,
            logger_service=self.logger_service,
            audit_service=self.audit_service
        )

    async def initialize(self):
        """Initialize the pipeline provider."""
        if not self._pipeline_initialized:
            await self.pipeline_factory.initialize_provider(self.pipeline.container)
            self._pipeline_initialized = True
            logger.info("Pipeline provider initialized")

    async def process_chat(self, message: str, client_ip: str, adapter_name: str,
                          system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                          session_id: Optional[str] = None, user_id: Optional[str] = None,
                          file_ids: Optional[List[str]] = None,
                          thread_id: Optional[str] = None,
                          audio_input: Optional[str] = None,
                          audio_format: Optional[str] = None,
                          language: Optional[str] = None,
                          return_audio: Optional[bool] = None,
                          tts_voice: Optional[str] = None,
                          source_language: Optional[str] = None,
                          target_language: Optional[str] = None) -> Dict[str, Any]:
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
            file_ids: Optional list of file IDs for file context
            audio_input: Optional base64 encoded audio input
            audio_format: Optional audio format
            language: Optional language code
            return_audio: Whether to return audio response
            tts_voice: Optional TTS voice
            source_language: Optional source language for translation
            target_language: Optional target language for translation

        Returns:
            Dictionary containing response and metadata
        """
        try:
            # Ensure pipeline is initialized
            await self.initialize()

            # Log request details
            await self.response_processor.log_request_details(
                message, client_ip, adapter_name,
                str(system_prompt_id) if system_prompt_id else None,
                api_key, session_id, user_id
            )

            # Get conversation context
            context_messages = await self.conversation_handler.get_context(session_id, adapter_name)

            # Build processing context
            context = self.context_builder.build_context(
                message=message,
                adapter_name=adapter_name,
                context_messages=context_messages,
                system_prompt_id=system_prompt_id,
                user_id=user_id,
                session_id=session_id,
                api_key=api_key,
                file_ids=file_ids,
                thread_id=thread_id,
                audio_input=audio_input,
                audio_format=audio_format,
                language=language,
                return_audio=return_audio,
                tts_voice=tts_voice,
                source_language=source_language,
                target_language=target_language
            )

            # Process through pipeline
            result = await self.pipeline.process(context)

            # Handle errors
            if result.has_error():
                error_msg = result.error or "Pipeline processing failed"
                logger.error(f"Pipeline error: {error_msg}")
                return {"error": error_msg}

            # Determine backend for logging
            backend = (
                result.inference_provider
                or self.config.get('general', {}).get('inference_provider', 'unknown')
            )

            # Process response (formatting, warnings, storage, logging)
            processed_response, assistant_message_id = await self.response_processor.process_response(
                response=result.response,
                message=message,
                client_ip=client_ip,
                adapter_name=adapter_name,
                session_id=session_id,
                user_id=user_id,
                api_key=api_key,
                backend=backend,
                processing_time=result.processing_time,
                retrieved_docs=result.retrieved_docs
            )

            # Generate audio if requested
            audio_data = None
            audio_format_str = None
            if return_audio and result.response:
                try:
                    result_audio = await self.audio_handler.generate_audio(
                        text=result.response,
                        adapter_name=adapter_name,
                        tts_voice=tts_voice,
                        language=language
                    )
                    # Properly handle None or tuple return
                    if result_audio is not None:
                        audio_data, audio_format_str = result_audio
                except Exception as e:
                    logger.warning(f"Failed to generate audio: {str(e)}")

            # Build and return result
            return self.response_processor.build_result(
                response=processed_response,
                sources=result.sources,
                metadata=result.metadata,
                processing_time=result.processing_time,
                audio_data=audio_data,
                audio_format=audio_format_str,
                assistant_message_id=assistant_message_id,
                session_id=session_id,
                adapter_name=adapter_name
            )

        except Exception as e:
            logger.error(f"Error processing chat with pipeline: {str(e)}")
            return {"error": str(e)}

    async def process_chat_stream(self, message: str, client_ip: str, adapter_name: str,
                                 system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                                 session_id: Optional[str] = None, user_id: Optional[str] = None,
                                 file_ids: Optional[List[str]] = None,
                                 thread_id: Optional[str] = None,
                                 audio_input: Optional[str] = None,
                                 audio_format: Optional[str] = None,
                                 language: Optional[str] = None,
                                 return_audio: Optional[bool] = None,
                                 tts_voice: Optional[str] = None,
                                 source_language: Optional[str] = None,
                                 target_language: Optional[str] = None,
                                 cancel_event: Optional[asyncio.Event] = None):
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
            file_ids: Optional list of file IDs for file context
            audio_input: Optional base64 encoded audio input
            audio_format: Optional audio format
            language: Optional language code
            return_audio: Whether to return audio response
            tts_voice: Optional TTS voice
            source_language: Optional source language for translation
            target_language: Optional target language for translation
            cancel_event: Optional asyncio.Event for stream cancellation

        Yields:
            Streaming response chunks
        """
        try:
            logger.debug(f"[PIPELINE_CHAT_SERVICE] Starting stream processing: adapter={adapter_name}, session={session_id}, has_cancel_event={cancel_event is not None}")
            # Ensure pipeline is initialized
            await self.initialize()

            # Log request details
            await self.response_processor.log_request_details(
                message, client_ip, adapter_name,
                str(system_prompt_id) if system_prompt_id else None,
                api_key, session_id, user_id
            )

            # Get conversation context
            context_messages = await self.conversation_handler.get_context(session_id, adapter_name)

            # Build processing context
            context = self.context_builder.build_context(
                message=message,
                adapter_name=adapter_name,
                context_messages=context_messages,
                system_prompt_id=system_prompt_id,
                user_id=user_id,
                session_id=session_id,
                api_key=api_key,
                file_ids=file_ids,
                thread_id=thread_id,
                audio_input=audio_input,
                audio_format=audio_format,
                language=language,
                return_audio=return_audio,
                tts_voice=tts_voice,
                source_language=source_language,
                target_language=target_language,
                cancel_event=cancel_event
            )

            # Track state for post-processing
            final_state = None

            try:
                # Get pipeline stream
                pipeline_stream = self.pipeline.process_stream(context)
                
                # Validate pipeline stream is not None
                if pipeline_stream is None:
                    logger.error("pipeline.process_stream returned None")
                    error_chunk = json.dumps({
                        "error": "Pipeline stream is not available",
                        "done": True
                    })
                    yield f"data: {error_chunk}\n\n"
                    return
                
                # Process stream through handler
                # Wrap in try-except to catch unpacking errors
                try:
                    async for item in self.streaming_handler.process_stream(
                        pipeline_stream=pipeline_stream,
                        adapter_name=adapter_name,
                        tts_voice=tts_voice,
                        language=language,
                        return_audio=return_audio or False
                    ):
                        # Check for cancellation before processing each item
                        if cancel_event and cancel_event.is_set():
                            logger.debug(f"[PIPELINE_CHAT_SERVICE] >>> CANCELLATION DETECTED <<< adapter={adapter_name}")
                            break

                        # Validate that item is a tuple before unpacking
                        if item is None:
                            logger.error("streaming_handler.process_stream yielded None instead of tuple")
                            continue
                        if not isinstance(item, tuple) or len(item) != 2:
                            logger.error(f"streaming_handler.process_stream yielded invalid item: {type(item)}, value: {item}")
                            continue

                        chunk, state = item
                        yield chunk
                        # No sleep needed - async generator already yields control
                        final_state = state
                except TypeError as te:
                    if "cannot unpack" in str(te) or "non-iterable" in str(te):
                        logger.error(f"Unpacking error in stream processing: {str(te)}", exc_info=True)
                        error_chunk = json.dumps({
                            "error": f"Stream processing error: {str(te)}",
                            "done": True
                        })
                        yield f"data: {error_chunk}\n\n"
                        return
                    raise

                # Post-stream processing
                if final_state and final_state.accumulated_text and final_state.stream_completed:
                    async for chunk in self._process_post_stream(
                        final_state=final_state,
                        context=context,
                        message=message,
                        client_ip=client_ip,
                        adapter_name=adapter_name,
                        session_id=session_id,
                        user_id=user_id,
                        api_key=api_key,
                        return_audio=return_audio,
                        tts_voice=tts_voice,
                        language=language
                    ):
                        yield chunk

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

    async def _process_post_stream(
        self,
        final_state: StreamingState,
        context: ProcessingContext,
        message: str,
        client_ip: str,
        adapter_name: str,
        session_id: Optional[str],
        user_id: Optional[str],
        api_key: Optional[str],
        return_audio: Optional[bool],
        tts_voice: Optional[str],
        language: Optional[str]
    ):
        """
        Handle post-stream processing including response finalization,
        warnings, and audio generation.

        Args:
            final_state: The final streaming state
            context: Processing context
            message: Original user message
            client_ip: Client IP address
            adapter_name: Adapter name
            session_id: Session identifier
            user_id: User identifier
            api_key: API key
            return_audio: Whether to return audio
            tts_voice: TTS voice
            language: Language code

        Yields:
            Post-processing chunks
        """
        # Process response (formatting, warnings, storage, logging)
        backend = (
            context.inference_provider
            or self.config.get('general', {}).get('inference_provider', 'unknown')
        )

        final_response, assistant_message_id = await self.response_processor.process_response(
            response=final_state.accumulated_text,
            message=message,
            client_ip=client_ip,
            adapter_name=adapter_name,
            session_id=session_id,
            user_id=user_id,
            api_key=api_key,
            backend=backend,
            processing_time=context.processing_time,
            retrieved_docs=context.retrieved_docs
        )

        # Check if warning was added and send as additional chunk
        warning = await self.conversation_handler.check_limit_warning(session_id, adapter_name)
        if warning:
            warning_chunk = json.dumps({
                "response": f"\n\n---\n{warning}",
                "done": False
            })
            yield f"data: {warning_chunk}\n\n"

        # Generate remaining audio if streaming audio was used
        # Note: Remaining audio may have already been generated early during streaming
        # Check if there's actually remaining text that needs audio
        if return_audio and final_state.sentence_detector and final_state.audio_chunks_sent > 0:
            # Only generate if there's actually remaining text (early generation may have already handled it)
            remaining_text = final_state.sentence_detector.get_remaining_text()
            if remaining_text and remaining_text.strip():
                remaining_audio_chunk = await self.streaming_handler.generate_remaining_audio(
                    state=final_state,
                    adapter_name=adapter_name,
                    tts_voice=tts_voice,
                    language=language
                )
                if remaining_audio_chunk:
                    yield remaining_audio_chunk

        # Generate full audio if no streaming audio was sent
        audio_data = None
        audio_format_str = None
        if return_audio and final_response:
            if not (final_state.sentence_detector and final_state.audio_chunks_sent > 0):
                try:
                    logger.debug(f"Calling audio_handler.generate_audio for adapter: {adapter_name}, voice: {tts_voice}")
                    result = await self.audio_handler.generate_audio(
                        text=final_response,
                        adapter_name=adapter_name,
                        tts_voice=tts_voice,
                        language=language
                    )
                    # Properly handle None or tuple return
                    if result is not None:
                        audio_data, audio_format_str = result
                    logger.debug(f"Audio generation result: audio_data={audio_data is not None}, format={audio_format_str}")
                except Exception as e:
                    logger.warning(f"Failed to generate audio: {str(e)}", exc_info=True)

        # Check if adapter supports threading and add metadata
        # Only enable threading if there are actual retrieved results to thread on
        # Uses centralized _has_meaningful_results which checks:
        # 1. LLM response text (PRIMARY - if LLM says "no results", trust it)
        # 2. Document confidence scores
        # 3. Source content for actual data
        threading_metadata = None
        if assistant_message_id and session_id and adapter_name:
            supports_threading = self.response_processor._adapter_supports_threading(adapter_name)

            # Use centralized meaningful results check (includes LLM response analysis)
            accumulated_response = final_state.accumulated_text if final_state else ""
            has_results = self.response_processor._has_meaningful_results(
                sources=context.retrieved_docs or [],
                response=accumulated_response
            )

            # For debug logging, also compute meaningful_docs count
            meaningful_docs = []
            if context.retrieved_docs:
                meaningful_docs = [
                    doc for doc in context.retrieved_docs
                    if (doc.get('confidence', 0) > 0.01 or
                        doc.get('metadata', {}).get('similarity', 0) > 0.01)
                ]

            if supports_threading and has_results:
                threading_metadata = {
                    "supports_threading": True,
                    "message_id": assistant_message_id,
                    "session_id": session_id,
                }
                logger.debug(
                    f"Adding threading metadata to done chunk: adapter={adapter_name}, message_id={assistant_message_id}, session_id={session_id}, meaningful_results={len(meaningful_docs)}"
                )
            elif supports_threading and not has_results:
                total_docs = len(context.retrieved_docs) if context.retrieved_docs else 0
                logger.debug(
                    f"Adapter {adapter_name} supports threading but no meaningful results found (total_docs={total_docs}, all low-confidence placeholders) - threading disabled"
                )
            else:
                logger.debug(
                    f"Adapter {adapter_name} does not support threading"
                )
        
        # Send final done chunk
        done_chunk = self.streaming_handler.build_done_chunk(
            state=final_state,
            audio_data=audio_data,
            audio_format_str=audio_format_str,
            threading_metadata=threading_metadata
        )
        yield done_chunk
