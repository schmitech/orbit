"""
Pipeline-based Chat Service

This module provides a chat service implementation using the pipeline architecture
with clean, direct provider implementations. Delegates to specialized handlers
for better maintainability and single responsibility.
"""

import json
import asyncio
import hashlib
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
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
                 database_service=None, thread_dataset_service=None,
                 file_processing_service=None):
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

        self.logger_service = logger_service
        self.chat_history_service = chat_history_service
        self.moderator_service = moderator_service
        self.clock_service = clock_service
        self.redis_service = redis_service
        self.audit_service = audit_service
        self.file_processing_service = file_processing_service

        self.pipeline_factory = PipelineFactory(config)

        if adapter_manager is not None:
            # For FaultTolerantAdapterManager, use base_adapter_manager for handlers
            if hasattr(adapter_manager, 'base_adapter_manager'):
                adapter_manager = adapter_manager.base_adapter_manager
            logger.debug("Using shared adapter manager for pipeline chat service")
        else:
            from services.dynamic_adapter_manager import DynamicAdapterManager
            adapter_manager = DynamicAdapterManager(config)
            logger.debug("Created local adapter manager for pipeline chat service")

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

        self._init_handlers(adapter_manager)
        self._pipeline_initialized = False

        query_cache_config = config.get('internal_services', {}).get('redis', {}).get('query_cache', {})
        self._query_cache_enabled = query_cache_config.get('enabled', True)
        self._query_cache_ttl = int(query_cache_config.get('ttl', 30))
        self._query_cache_max_memory = int(query_cache_config.get('max_memory_entries', 100))
        self._memory_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

        logger.debug("Pipeline-based chat service initialized with clean providers")

    def _init_handlers(self, adapter_manager) -> None:
        """Initialize all specialized handlers."""
        self.conversation_handler = ConversationHistoryHandler(
            config=self.config,
            chat_history_service=self.chat_history_service,
            adapter_manager=adapter_manager
        )
        self.audio_handler = AudioHandler(
            config=self.config,
            adapter_manager=adapter_manager
        )
        self.context_builder = RequestContextBuilder(
            config=self.config,
            adapter_manager=adapter_manager
        )
        self.streaming_handler = StreamingHandler(
            config=self.config,
            audio_handler=self.audio_handler
        )
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

    # -------------------------------------------------------------------------
    # Image persistence
    # -------------------------------------------------------------------------

    async def _persist_generated_image(self, context: ProcessingContext) -> None:
        """Save generated image bytes to filesystem and set context.image_url."""
        if not context.image or not self.file_processing_service:
            return
        import uuid
        import base64 as _base64
        try:
            file_id = str(uuid.uuid4())
            fmt = context.image_format or "png"
            filename = f"generated_{file_id}.{fmt}"
            mime_type = f"image/{fmt}"
            image_bytes = _base64.b64decode(context.image)
            api_key = context.api_key or "_generated"
            storage_key = f"{api_key}/{file_id}/{filename}"

            await self.file_processing_service.storage.put_file(
                file_data=image_bytes,
                key=storage_key,
                metadata={"filename": filename, "mime_type": mime_type,
                          "file_size": len(image_bytes), "generated": True}
            )
            await self.file_processing_service.metadata_store.record_file_upload(
                file_id=file_id, api_key=api_key, filename=filename,
                mime_type=mime_type, file_size=len(image_bytes),
                storage_key=storage_key, storage_type="raw",
                metadata={"generated": True, "format": fmt, "session_id": context.session_id or ""}
            )
            await self.file_processing_service.metadata_store.update_processing_status(
                file_id=file_id, status="completed"
            )
            context.image_url = f"/api/files/{file_id}/content"
        except Exception as e:
            logger.warning(f"Failed to persist generated image: {e}")

    # -------------------------------------------------------------------------
    # Query burst cache helpers
    # -------------------------------------------------------------------------

    def _build_query_cache_key(
        self,
        message: str,
        adapter_name: str,
        thread_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        system_prompt_id: Optional[ObjectId] = None,
    ) -> str:
        """Build a deterministic cache key for query burst deduplication."""
        key_data = json.dumps({
            'msg': message.strip().lower(),
            'adapter': adapter_name,
            'tid': thread_id or '',
            'fids': sorted(file_ids) if file_ids else [],
            'pid': str(system_prompt_id) if system_prompt_id else '',
        }, sort_keys=True)
        return f"qcache:{hashlib.sha256(key_data.encode()).hexdigest()[:32]}"

    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Return cached query result from Redis or in-memory fallback."""
        if not self._query_cache_enabled:
            return None

        if self.redis_service:
            try:
                cached = await self.redis_service.get_json(cache_key)
                if cached:
                    logger.debug(f"Query cache HIT (Redis): {cache_key[:20]}")
                    return cached
            except Exception:
                logger.debug("Failed to read query cache from Redis", exc_info=True)

        entry = self._memory_cache.get(cache_key)
        if entry:
            result, expire_at = entry
            if time.monotonic() < expire_at:
                logger.debug(f"Query cache HIT (memory): {cache_key[:20]}")
                return result
            del self._memory_cache[cache_key]

        return None

    async def _store_cached_response(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Store query result in Redis and in-memory cache."""
        if not self._query_cache_enabled or 'error' in result:
            return

        if self.redis_service:
            try:
                await self.redis_service.store_json(cache_key, result, ttl=self._query_cache_ttl)
            except Exception:
                logger.debug("Failed to store query cache in Redis", exc_info=True)

        now = time.monotonic()
        if len(self._memory_cache) >= self._query_cache_max_memory:
            expired = [k for k, (_, exp) in self._memory_cache.items() if now >= exp]
            for k in expired:
                del self._memory_cache[k]
            if len(self._memory_cache) >= self._query_cache_max_memory:
                del self._memory_cache[next(iter(self._memory_cache))]

        self._memory_cache[cache_key] = (result, now + self._query_cache_ttl)

    async def clear_prompt_cache(self, prompt_id: Optional[str] = None) -> Dict[str, int]:
        """Clear prompt-dependent runtime caches after persona mutations."""
        prompt_entries = 0
        if hasattr(self.pipeline, "clear_prompt_cache"):
            prompt_entries = self.pipeline.clear_prompt_cache(str(prompt_id) if prompt_id else None)

        memory_query_entries = len(self._memory_cache)
        self._memory_cache.clear()

        redis_query_entries = 0
        if self.redis_service and hasattr(self.redis_service, "_clear_keys_by_pattern"):
            try:
                redis_query_entries = await self.redis_service._clear_keys_by_pattern(
                    "qcache:*",
                    "query burst cache",
                )
            except Exception:
                logger.debug("Failed to clear Redis query cache after prompt cache invalidation", exc_info=True)

        return {
            "prompt_entries": prompt_entries,
            "memory_query_entries": memory_query_entries,
            "redis_query_entries": redis_query_entries,
        }

    # -------------------------------------------------------------------------
    # Thread context resolution
    # -------------------------------------------------------------------------

    async def _resolve_context_for_thread(
        self,
        thread_id: str,
        session_id: Optional[str],
        adapter_name: str,
    ) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """
        Return (context_messages, effective_session_id) for a thread request.

        Turn 1 (thread session empty): seeds from the parent session so the LLM
        sees the exchange that spawned this thread.
        Turn 2+: uses the thread session's own accumulated history.
        """
        assert thread_id, "thread_id must not be empty"

        container = self.pipeline.container
        if not container.has('thread_service'):
            return await self.conversation_handler.get_context(session_id, adapter_name), session_id

        thread_service = container.get('thread_service')
        thread_info = await thread_service.get_thread(thread_id)
        if not thread_info:
            logger.warning(f"Thread {thread_id} not found; falling back to session context")
            return await self.conversation_handler.get_context(session_id, adapter_name), session_id

        thread_session_id = thread_info.get('thread_session_id', session_id)

        thread_messages = await self.conversation_handler.get_context(thread_session_id, adapter_name)
        if thread_messages:
            return thread_messages, thread_session_id

        # First turn: thread session is empty — seed with parent context so the LLM
        # retains the conversation that led to this thread being created.
        parent_session_id = thread_info.get('parent_session_id', session_id)
        parent_messages = await self.conversation_handler.get_context(parent_session_id, adapter_name)
        return parent_messages, thread_session_id

    # -------------------------------------------------------------------------
    # Pure computation helpers (no I/O, no side effects)
    # -------------------------------------------------------------------------

    def _determine_inference_backend(self, context: ProcessingContext) -> str:
        """Return the inference provider name for logging."""
        return (
            context.inference_provider
            or self.config.get('general', {}).get('inference_provider', 'unknown')
        )

    def _build_threading_metadata(
        self,
        context: ProcessingContext,
        adapter_name: str,
        assistant_message_id: Optional[str],
        session_id: Optional[str],
        accumulated_text: str,
    ) -> Optional[Dict[str, Any]]:
        """Return threading metadata for the done chunk, or None if threading is not applicable."""
        if not (assistant_message_id and session_id and adapter_name):
            return None
        if not self.response_processor._adapter_supports_threading(adapter_name):
            logger.debug(f"Adapter {adapter_name} does not support threading")
            return None
        has_results = self.response_processor._has_meaningful_results(
            sources=context.retrieved_docs or [],
            response=accumulated_text,
        )
        if not has_results:
            total_docs = len(context.retrieved_docs) if context.retrieved_docs else 0
            logger.debug(
                f"Adapter {adapter_name} supports threading but no meaningful results "
                f"(total_docs={total_docs}) - threading disabled"
            )
            return None
        logger.debug(
            f"Adding threading metadata: adapter={adapter_name}, "
            f"message_id={assistant_message_id}, session_id={session_id}"
        )
        return {
            "supports_threading": True,
            "message_id": assistant_message_id,
            "session_id": session_id,
        }

    # -------------------------------------------------------------------------
    # Audio helpers
    # -------------------------------------------------------------------------

    async def _maybe_generate_full_audio(
        self,
        response_text: str,
        final_state: Optional[StreamingState],
        adapter_name: str,
        tts_voice: Optional[str],
        language: Optional[str],
        return_audio: Optional[bool],
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate a full audio blob when not using incremental sentence streaming.
        Returns (audio_data, audio_format) or (None, None) if audio is unavailable.
        """
        if not return_audio or not response_text:
            return None, None
        if final_state and final_state.sentence_detector and final_state.audio_chunks_sent > 0:
            return None, None  # already delivered incrementally during streaming
        try:
            result = await self.audio_handler.generate_audio(
                text=response_text,
                adapter_name=adapter_name,
                tts_voice=tts_voice,
                language=language,
            )
            if result is not None:
                return result
        except Exception as e:
            logger.warning(f"Failed to generate audio: {e}", exc_info=True)
        return None, None

    async def _maybe_yield_remaining_audio_chunk(
        self,
        final_state: StreamingState,
        adapter_name: str,
        tts_voice: Optional[str],
        language: Optional[str],
    ) -> Optional[str]:
        """
        Return a streaming chunk for any sentence-streaming audio remainder, or None.
        Only applies when audio was already sent incrementally during streaming.
        """
        if not (final_state.sentence_detector and final_state.audio_chunks_sent > 0):
            return None
        remaining_text = final_state.sentence_detector.get_remaining_text()
        if not remaining_text or not remaining_text.strip():
            return None
        return await self.streaming_handler.generate_remaining_audio(
            state=final_state,
            adapter_name=adapter_name,
            tts_voice=tts_voice,
            language=language,
        )

    # -------------------------------------------------------------------------
    # Pipeline stream consumer
    # -------------------------------------------------------------------------

    async def _consume_pipeline_stream(
        self,
        context: ProcessingContext,
        adapter_name: str,
        tts_voice: Optional[str],
        language: Optional[str],
        return_audio: bool,
        cancel_event: Optional[asyncio.Event],
    ):
        """
        Yield (chunk, StreamingState) pairs from the pipeline stream.
        Raises RuntimeError if the pipeline returns no stream.
        """
        pipeline_stream = self.pipeline.process_stream(context)
        if pipeline_stream is None:
            raise RuntimeError("pipeline.process_stream returned None")

        async for item in self.streaming_handler.process_stream(
            pipeline_stream=pipeline_stream,
            adapter_name=adapter_name,
            tts_voice=tts_voice,
            language=language,
            return_audio=return_audio,
        ):
            if cancel_event and cancel_event.is_set():
                logger.debug(f"Stream cancelled for adapter={adapter_name}")
                return
            if not isinstance(item, tuple) or len(item) != 2:
                logger.error(f"Invalid stream item from streaming_handler: type={type(item)}")
                continue
            yield item

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    async def process_chat(
        self,
        message: str,
        client_ip: str,
        adapter_name: str,
        system_prompt_id: Optional[ObjectId] = None,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        audio_input: Optional[str] = None,
        audio_format: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: Optional[bool] = None,
        tts_voice: Optional[str] = None,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        requested_model: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a chat message using the pipeline architecture.

        Returns a dictionary containing response and metadata, or {"error": ...}
        on failure.
        """
        if not message or not message.strip():
            return {"error": "message must not be empty"}
        if not adapter_name:
            return {"error": "adapter_name must not be empty"}

        try:
            await self.initialize()

            cache_key = None
            if self._query_cache_enabled and not audio_input:
                cache_key = self._build_query_cache_key(
                    message, adapter_name, thread_id, file_ids, system_prompt_id
                )
                cached = await self._get_cached_response(cache_key)
                if cached:
                    return cached

            await self.response_processor.log_request_details(
                message, client_ip, adapter_name,
                str(system_prompt_id) if system_prompt_id else None,
                api_key, session_id, user_id,
            )

            if thread_id:
                context_messages, effective_session_id = await self._resolve_context_for_thread(
                    thread_id, session_id, adapter_name
                )
            else:
                context_messages = await self.conversation_handler.get_context(session_id, adapter_name)
                effective_session_id = session_id

            context = self.context_builder.build_context(
                message=message,
                adapter_name=adapter_name,
                context_messages=context_messages,
                system_prompt_id=system_prompt_id,
                user_id=user_id,
                session_id=effective_session_id,
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
                requested_model=requested_model,
                skill=skill,
            )

            result = await self.pipeline.process(context)

            if result.has_error():
                error_msg = result.error or "Pipeline processing failed"
                logger.error(f"Pipeline error: {error_msg}")
                return {"error": error_msg}

            backend = self._determine_inference_backend(context)

            processed_response, assistant_message_id = await self.response_processor.process_response(
                response=result.response,
                message=message,
                client_ip=client_ip,
                adapter_name=adapter_name,
                session_id=context.session_id,
                user_id=user_id,
                api_key=api_key,
                backend=backend,
                processing_time=result.processing_time,
                retrieved_docs=result.retrieved_docs,
            )

            audio_data, audio_format_str = await self._maybe_generate_full_audio(
                result.response or "", None, adapter_name, tts_voice, language, return_audio
            )

            await self._persist_generated_image(context)

            final_result = self.response_processor.build_result(
                response=processed_response,
                sources=result.sources,
                metadata=result.metadata,
                processing_time=result.processing_time,
                audio_data=audio_data,
                audio_format=audio_format_str,
                assistant_message_id=assistant_message_id,
                session_id=context.session_id,
                adapter_name=adapter_name,
                image=result.image,
                image_format=result.image_format,
                image_revised_prompt=result.image_revised_prompt,
                image_url=context.image_url,
            )

            if cache_key and not audio_data:
                await self._store_cached_response(cache_key, final_result)

            return final_result

        except Exception as e:
            logger.error(f"Error processing chat with pipeline: {e}", exc_info=True)
            return {"error": str(e)}

    async def process_chat_stream(
        self,
        message: str,
        client_ip: str,
        adapter_name: str,
        system_prompt_id: Optional[ObjectId] = None,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        audio_input: Optional[str] = None,
        audio_format: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: Optional[bool] = None,
        tts_voice: Optional[str] = None,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
        requested_model: Optional[str] = None,
        skill: Optional[str] = None,
    ):
        """
        Process a chat message with streaming response using the pipeline architecture.

        Yields SSE-formatted data chunks, ending with a done chunk.
        """
        if not message or not message.strip():
            yield f"data: {json.dumps({'error': 'message must not be empty', 'done': True})}\n\n"
            return
        if not adapter_name:
            yield f"data: {json.dumps({'error': 'adapter_name must not be empty', 'done': True})}\n\n"
            return

        try:
            logger.debug(
                f"[PIPELINE_CHAT_SERVICE] Starting stream: adapter={adapter_name}, "
                f"session={session_id}, has_cancel_event={cancel_event is not None}"
            )
            await self.initialize()

            if self._query_cache_enabled and not audio_input:
                stream_cache_key = self._build_query_cache_key(
                    message, adapter_name, thread_id, file_ids, system_prompt_id
                )
                cached = await self._get_cached_response(stream_cache_key)
                if cached:
                    yield f"data: {json.dumps({'response': cached.get('response', ''), 'done': False})}\n\n"
                    done_data: Dict[str, Any] = {"done": True}
                    if cached.get("sources"):
                        done_data["sources"] = cached["sources"]
                    if cached.get("metadata"):
                        done_data["metadata"] = cached["metadata"]
                    yield f"data: {json.dumps(done_data)}\n\n"
                    return

            await self.response_processor.log_request_details(
                message, client_ip, adapter_name,
                str(system_prompt_id) if system_prompt_id else None,
                api_key, session_id, user_id,
            )

            if thread_id:
                context_messages, effective_session_id = await self._resolve_context_for_thread(
                    thread_id, session_id, adapter_name
                )
            else:
                context_messages = await self.conversation_handler.get_context(session_id, adapter_name)
                effective_session_id = session_id

            context = self.context_builder.build_context(
                message=message,
                adapter_name=adapter_name,
                context_messages=context_messages,
                system_prompt_id=system_prompt_id,
                user_id=user_id,
                session_id=effective_session_id,
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
                cancel_event=cancel_event,
                requested_model=requested_model,
                skill=skill,
            )

            final_state = None

            try:
                async for chunk, state in self._consume_pipeline_stream(
                    context, adapter_name, tts_voice, language,
                    return_audio or False, cancel_event,
                ):
                    yield chunk
                    final_state = state
            except Exception as stream_error:
                logger.error(f"Error in pipeline streaming: {stream_error}", exc_info=True)
                yield f"data: {json.dumps({'error': str(stream_error), 'done': True})}\n\n"
                return

            # Image generation: the pipeline emits a single {"done":true,"image":...} chunk.
            # streaming_handler consumes it internally (accumulates text, sets stream_completed)
            # but yields zero items, so final_state is never assigned above.
            # Synthesise a minimal state so _process_post_stream runs and sends the done chunk.
            if final_state is None and context.image:
                final_state = StreamingState()
                final_state.accumulated_text = context.response or ""
                final_state.stream_completed = True

            if not (final_state and final_state.stream_completed
                    and (final_state.accumulated_text or context.image)):
                return

            async for chunk in self._process_post_stream(
                final_state=final_state,
                context=context,
                message=message,
                client_ip=client_ip,
                adapter_name=adapter_name,
                session_id=context.session_id,
                user_id=user_id,
                api_key=api_key,
                return_audio=return_audio,
                tts_voice=tts_voice,
                language=language,
            ):
                yield chunk

            if self._query_cache_enabled and not audio_input and not return_audio:
                if final_state.accumulated_text:
                    try:
                        cache_result = {
                            "response": final_state.accumulated_text,
                            "sources": context.sources if context.sources else [],
                        }
                        await self._store_cached_response(stream_cache_key, cache_result)
                    except Exception:
                        logger.debug("Failed to cache streamed response", exc_info=True)

        except Exception as e:
            logger.error(f"Error processing chat stream with pipeline: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    # -------------------------------------------------------------------------
    # Post-stream finalization
    # -------------------------------------------------------------------------

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
        language: Optional[str],
    ):
        """
        Finalize a completed stream: store the response, emit optional warning and
        audio chunks, then yield the done chunk with threading metadata.
        """
        backend = self._determine_inference_backend(context)

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
            retrieved_docs=context.retrieved_docs,
        )

        warning = await self.conversation_handler.check_limit_warning(session_id, adapter_name)
        if warning:
            yield f"data: {json.dumps({'response': f'{chr(10)}{chr(10)}---{chr(10)}{warning}', 'done': False})}\n\n"

        remaining_chunk = await self._maybe_yield_remaining_audio_chunk(
            final_state, adapter_name, tts_voice, language
        )
        if remaining_chunk:
            yield remaining_chunk

        audio_data, audio_format_str = await self._maybe_generate_full_audio(
            final_response, final_state, adapter_name, tts_voice, language, return_audio
        )

        threading_metadata = self._build_threading_metadata(
            context=context,
            adapter_name=adapter_name,
            assistant_message_id=assistant_message_id,
            session_id=session_id,
            accumulated_text=final_state.accumulated_text if final_state else "",
        )

        await self._persist_generated_image(context)

        yield self.streaming_handler.build_done_chunk(
            state=final_state,
            audio_data=audio_data,
            audio_format_str=audio_format_str,
            threading_metadata=threading_metadata,
            assistant_message_id=assistant_message_id,
            image=context.image,
            image_format=context.image_format,
            image_revised_prompt=context.image_revised_prompt,
            image_url=context.image_url,
        )
