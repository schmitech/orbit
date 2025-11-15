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
from utils.sentence_detector import SentenceDetector
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
                 retriever=None, reranker_service=None, prompt_service=None, clock_service=None):
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
            clock_service: Optional clock service
        """
        self.config = config
        self.verbose = is_true_value(config.get('general', {}).get('verbose', False))

        # Chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        # Base chat history enabled setting from config
        self._base_chat_history_enabled = is_true_value(self.chat_history_config.get('enabled', True))
        # Will be determined per request based on adapter type
        self.chat_history_enabled = self._base_chat_history_enabled
        
        # Messages configuration
        self.messages_config = config.get('messages', {})
        
        # Create pipeline factory
        self.pipeline_factory = PipelineFactory(config)
        
        # Create adapter manager for dynamic retrieval
        from services.dynamic_adapter_manager import DynamicAdapterManager
        adapter_manager = DynamicAdapterManager(config)
        
        # Store services for direct access
        self.logger_service = logger_service
        self.chat_history_service = chat_history_service
        self.llm_guard_service = llm_guard_service
        self.moderator_service = moderator_service
        self.clock_service = clock_service

        self.pipeline = self.pipeline_factory.create_pipeline_with_services(
            retriever=retriever,
            reranker_service=reranker_service,
            prompt_service=prompt_service,
            llm_guard_service=llm_guard_service,
            moderator_service=moderator_service,
            chat_history_service=chat_history_service,
            logger_service=logger_service,
            adapter_manager=adapter_manager,
            clock_service=self.clock_service
        )
        
        # Store pipeline reference for async initialization
        self._pipeline_initialized = False
        self._default_provider_available = True  # Assume available unless initialization fails

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
    
    def _should_enable_chat_history(self, adapter_name: str) -> bool:
        """
        Determine if chat history should be enabled based on adapter type and inference mode.

        Args:
            adapter_name: The name of the adapter being used

        Returns:
            True if chat history should be enabled, False otherwise
        """
        # If base chat history is disabled in config, always return False
        if not self._base_chat_history_enabled:
            return False

        # Check adapter type - enable only for passthrough adapters
        if adapter_name and hasattr(self, 'pipeline') and self.pipeline.container.has('adapter_manager'):
            adapter_manager = self.pipeline.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(adapter_name)
            if adapter_config and adapter_config.get('type') == 'passthrough':
                return True

        # Disable for all other adapters
        return False

    async def _get_conversation_context(self, session_id: Optional[str], adapter_name: str) -> List[Dict[str, str]]:
        """
        Get conversation context from history for the current session.

        Args:
            session_id: The session identifier
            adapter_name: The adapter being used

        Returns:
            List of previous messages formatted for LLM context
        """
        if not self._should_enable_chat_history(adapter_name) or not self.chat_history_service or not session_id:
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
        adapter_name: str,
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
            adapter_name: The adapter being used
            user_id: Optional user identifier
            api_key: Optional API key
            metadata: Optional metadata to store
        """
        if not self._should_enable_chat_history(adapter_name) or not self.chat_history_service or not session_id:
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
                              user_id: Optional[str] = None, backend: Optional[str] = None):
        """Log conversation asynchronously."""
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
    
    async def _check_conversation_limit_warning(self, session_id: Optional[str], adapter_name: str) -> Optional[str]:
        """
        Check if the conversation is approaching the limit and return a warning if needed.

        Args:
            session_id: The session identifier
            adapter_name: The adapter being used

        Returns:
            Warning message if approaching limit, None otherwise
        """
        if not self._should_enable_chat_history(adapter_name) or not self.chat_history_service or not session_id:
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
                          session_id: Optional[str] = None, user_id: Optional[str] = None,
                          file_ids: Optional[List[str]] = None,
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
            context_messages = await self._get_conversation_context(session_id, adapter_name)
            
            # Check for adapter-specific inference provider override
            inference_provider_override = None
            timezone = None
            if adapter_name and hasattr(self, 'pipeline') and self.pipeline.container.has('adapter_manager'):
                adapter_manager = self.pipeline.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if adapter_config:
                    inference_provider_override = adapter_config.get('inference_provider')
                    adapter_custom_config = adapter_config.get('config') or {}
                    timezone = adapter_custom_config.get('timezone')
                    if inference_provider_override and self.verbose:
                        logger.info(f"Using adapter-specific inference provider: {inference_provider_override} for adapter: {adapter_name}")
            
            # Create processing context
            context = ProcessingContext(
                message=message,
                adapter_name=adapter_name,
                system_prompt_id=str(system_prompt_id) if system_prompt_id else None,
                inference_provider=inference_provider_override,
                context_messages=context_messages,
                user_id=user_id,
                session_id=session_id,
                api_key=api_key,
                timezone=timezone,
                file_ids=file_ids or [],
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
            
            # Get response and clean it
            response = fix_text_formatting(result.response)
            
            # Check for conversation limit warning
            warning = await self._check_conversation_limit_warning(session_id, adapter_name)
            if warning:
                response = f"{response}\n\n---\n{warning}"
            
            # Store conversation turn
            if session_id:
                await self._store_conversation_turn(
                    session_id=session_id,
                    user_message=message,
                    assistant_response=response,
                    adapter_name=adapter_name,
                    user_id=user_id,
                    api_key=api_key,
                    metadata={
                        "adapter_name": adapter_name,
                        "client_ip": client_ip,
                        "pipeline_processing_time": result.processing_time
                    }
                )
            
            # Log conversation (always log, not just when API key is present)
            # Use the inference provider from the pipeline result context, fallback to global config
            backend = result.inference_provider or self.config.get('general', {}).get('inference_provider', 'unknown')
            await self._log_conversation(message, response, client_ip, api_key, session_id, user_id, backend)
            
            # Generate audio if requested
            audio_data = None
            audio_format_str = None
            if return_audio and result.response:
                try:
                    audio_data, audio_format_str = await self._generate_audio(
                        text=result.response,
                        adapter_name=adapter_name,
                        tts_voice=tts_voice,
                        language=language
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate audio: {str(e)}")
            
            # Return response in expected format
            result_dict = {
                "response": response,
                "sources": result.sources,
                "metadata": {
                    **result.metadata,
                    "processing_time": result.processing_time,
                    "pipeline_used": True
                }
            }
            
            # Add audio if generated
            if audio_data:
                import base64
                result_dict["audio"] = base64.b64encode(audio_data).decode('utf-8')
                result_dict["audio_format"] = audio_format_str or "mp3"
            
            return result_dict
            
        except Exception as e:
            logger.error(f"Error processing chat with pipeline: {str(e)}")
            return {"error": str(e)}
    
    async def process_chat_stream(self, message: str, client_ip: str, adapter_name: str, 
                                 system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                                 session_id: Optional[str] = None, user_id: Optional[str] = None,
                                 file_ids: Optional[List[str]] = None,
                                 audio_input: Optional[str] = None,
                                 audio_format: Optional[str] = None,
                                 language: Optional[str] = None,
                                 return_audio: Optional[bool] = None,
                                 tts_voice: Optional[str] = None,
                                 source_language: Optional[str] = None,
                                 target_language: Optional[str] = None):
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
            context_messages = await self._get_conversation_context(session_id, adapter_name)
            
            # Check for adapter-specific inference provider override
            inference_provider_override = None
            timezone = None
            if adapter_name and hasattr(self, 'pipeline') and self.pipeline.container.has('adapter_manager'):
                adapter_manager = self.pipeline.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if adapter_config:
                    inference_provider_override = adapter_config.get('inference_provider')
                    adapter_custom_config = adapter_config.get('config') or {}
                    timezone = adapter_custom_config.get('timezone')
                    if inference_provider_override and self.verbose:
                        logger.info(f"Using adapter-specific inference provider: {inference_provider_override} for adapter: {adapter_name}")
            
            # Create processing context
            context = ProcessingContext(
                message=message,
                adapter_name=adapter_name,
                system_prompt_id=str(system_prompt_id) if system_prompt_id else None,
                inference_provider=inference_provider_override,
                context_messages=context_messages,
                user_id=user_id,
                session_id=session_id,
                api_key=api_key,
                timezone=timezone,
                file_ids=file_ids or [],
                audio_input=audio_input,
                audio_format=audio_format,
                language=language,
                return_audio=return_audio,
                tts_voice=tts_voice,
                source_language=source_language,
                target_language=target_language
            )
            
            # Buffer to accumulate the complete response
            accumulated_text = ""
            sources = []
            stream_completed_successfully = False
            
            first_chunk_yielded = False
            chunk_count = 0
            
            # Initialize sentence detector for streaming TTS
            sentence_detector = SentenceDetector() if return_audio else None
            audio_chunks_sent = 0
            
            try:
                # Process through pipeline with streaming
                async for chunk in self.pipeline.process_stream(context):
                    try:
                        chunk_data = json.loads(chunk)

                        # Handle errors
                        if "error" in chunk_data:
                            yield f"data: {chunk}\n\n"
                            return

                        # Debug: Log first chunk timing
                        if not first_chunk_yielded and "response" in chunk_data and chunk_data["response"]:
                            first_chunk_yielded = True
                            if self.verbose:
                                logger.info(f"🚀 Yielding first chunk to client: {repr(chunk_data['response'][:50])}")

                        # Handle done marker - DON'T yield it yet, we'll add audio first
                        if chunk_data.get("done", False):
                            # Accumulate any remaining content before breaking
                            if "response" in chunk_data:
                                accumulated_text += chunk_data["response"]
                            if "sources" in chunk_data:
                                sources = chunk_data["sources"]
                            stream_completed_successfully = True
                            break  # Exit loop, we'll send done chunk with audio later

                        # Stream immediately - yield to event loop to prevent buffering
                        yield f"data: {chunk}\n\n"
                        await asyncio.sleep(0)  # Force immediate flush to client

                        chunk_count += 1

                        # Accumulate content
                        if "response" in chunk_data:
                            new_text = chunk_data["response"]
                            accumulated_text += new_text
                            
                            # If streaming audio is enabled, detect sentences and generate TTS
                            # Note: TTS generation happens synchronously but should be fast enough
                            # If it blocks, consider disabling streaming audio for very long responses
                            if return_audio and sentence_detector and new_text:
                                completed_sentences = sentence_detector.add_text(new_text)
                                
                                # Generate TTS for each completed sentence
                                # Use try-except to ensure TTS failures don't stop text streaming
                                for sentence in completed_sentences:
                                    if sentence.strip():
                                        try:
                                            # Generate audio with timeout to prevent blocking
                                            audio_data, audio_format_str = await asyncio.wait_for(
                                                self._generate_audio(
                                                    text=sentence.strip(),
                                                    adapter_name=adapter_name,
                                                    tts_voice=tts_voice,
                                                    language=language
                                                ),
                                                timeout=5.0  # 5 second timeout per sentence
                                            )
                                            
                                            if audio_data:
                                                import base64
                                                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                                                
                                                # Send audio chunk
                                                audio_chunk = {
                                                    "audio_chunk": audio_base64,
                                                    "audioFormat": audio_format_str or "opus",
                                                    "chunk_index": audio_chunks_sent,
                                                    "done": False
                                                }
                                                audio_chunks_sent += 1
                                                
                                                audio_chunk_json = json.dumps(audio_chunk)
                                                yield f"data: {audio_chunk_json}\n\n"
                                                await asyncio.sleep(0)  # Force immediate flush
                                                
                                                # Small pause every 5 chunks to prevent overwhelming the client
                                                if audio_chunks_sent % 5 == 0:
                                                    await asyncio.sleep(0.01)
                                                
                                                if self.verbose:
                                                    logger.info(f"Sent streaming audio chunk {audio_chunks_sent} ({len(audio_base64)} chars base64)")
                                        except asyncio.TimeoutError:
                                            logger.warning(f"TTS generation timeout for sentence, skipping audio chunk")
                                        except Exception as e:
                                            logger.warning(f"Failed to generate streaming audio for sentence: {str(e)}", exc_info=True)
                                            # Continue text streaming even if TTS fails

                        # Handle sources
                        if "sources" in chunk_data:
                            sources = chunk_data["sources"]

                    except json.JSONDecodeError:
                        # Still yield the chunk even if we can't parse it
                        yield f"data: {chunk}\n\n"
                        await asyncio.sleep(0)  # Force immediate flush
                        continue
                
                # Post-stream processing
                if accumulated_text and stream_completed_successfully:
                    # Clean response
                    final_response = fix_text_formatting(accumulated_text)
                    
                    # Check for conversation limit warning
                    warning = await self._check_conversation_limit_warning(session_id, adapter_name)
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
                            adapter_name=adapter_name,
                            user_id=user_id,
                            api_key=api_key,
                            metadata={
                                "adapter_name": adapter_name,
                                "client_ip": client_ip,
                                "pipeline_processing_time": context.processing_time
                            }
                        )
                    
                    # Log conversation (always log, not just when API key is present)
                    backend = (
                        context.inference_provider
                        or self.config.get('general', {}).get('inference_provider', 'unknown')
                    )
                    await self._log_conversation(
                        message,
                        final_response,
                        client_ip,
                        api_key,
                        session_id,
                        user_id,
                        backend,
                    )
                    
                    # Generate audio for any remaining text if streaming audio was enabled
                    audio_data = None
                    audio_format_str = None
                    if self.verbose:
                        logger.info(f"Checking audio generation: return_audio={return_audio}, final_response length={len(final_response) if final_response else 0}")
                    
                    if return_audio and final_response:
                        # Check if we already sent streaming audio chunks
                        if sentence_detector and audio_chunks_sent > 0:
                            # Generate audio for any remaining text that didn't form a complete sentence
                            remaining_text = sentence_detector.get_remaining_text()
                            if remaining_text.strip():
                                try:
                                    if self.verbose:
                                        logger.info(f"Generating audio for remaining text: {len(remaining_text)} chars")
                                    remaining_audio_data, remaining_audio_format = await self._generate_audio(
                                        text=remaining_text.strip(),
                                        adapter_name=adapter_name,
                                        tts_voice=tts_voice,
                                        language=language
                                    )

                                    # Send remaining audio as a proper audio_chunk (same format as streaming chunks)
                                    if remaining_audio_data:
                                        import base64
                                        remaining_audio_base64 = base64.b64encode(remaining_audio_data).decode('utf-8')

                                        remaining_audio_chunk = {
                                            "audio_chunk": remaining_audio_base64,
                                            "audioFormat": remaining_audio_format or "opus",
                                            "chunk_index": audio_chunks_sent,
                                            "done": False
                                        }
                                        audio_chunks_sent += 1

                                        remaining_chunk_json = json.dumps(remaining_audio_chunk)
                                        yield f"data: {remaining_chunk_json}\n\n"
                                        await asyncio.sleep(0)  # Force immediate flush

                                        if self.verbose:
                                            logger.info(f"Sent remaining audio chunk {audio_chunks_sent} ({len(remaining_audio_base64)} chars base64)")
                                except Exception as e:
                                    logger.warning(f"Failed to generate audio for remaining text: {str(e)}", exc_info=True)
                        else:
                            # No streaming audio was sent, generate full audio
                            try:
                                if self.verbose:
                                    logger.info(f"Calling _generate_audio for adapter: {adapter_name}, voice: {tts_voice}")
                                audio_data, audio_format_str = await self._generate_audio(
                                    text=final_response,
                                    adapter_name=adapter_name,
                                    tts_voice=tts_voice,
                                    language=language
                                )
                                if self.verbose:
                                    logger.info(f"Audio generation result: audio_data={audio_data is not None}, format={audio_format_str}")
                            except Exception as e:
                                logger.warning(f"Failed to generate audio: {str(e)}", exc_info=True)

                    # Send final done marker with audio if available
                    done_chunk = {"done": True}
                    if sources:
                        done_chunk["sources"] = sources

                    # Include total audio chunks count if streaming audio was used
                    if sentence_detector and audio_chunks_sent > 0:
                        done_chunk["total_audio_chunks"] = audio_chunks_sent

                    if self.verbose:
                        logger.info(f"Preparing done chunk: audio_data={audio_data is not None}, audio_format_str={audio_format_str}, total_audio_chunks={audio_chunks_sent if sentence_detector else 0}")

                    # Only include audio in done chunk for non-streaming mode (when no streaming chunks were sent)
                    if audio_data and not (sentence_detector and audio_chunks_sent > 0):
                        import base64
                        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                        done_chunk["audio"] = audio_base64
                        done_chunk["audioFormat"] = audio_format_str or "mp3"
                        if self.verbose:
                            logger.info(f"Including audio in done chunk: {len(audio_base64)} chars (base64)")

                    done_json = json.dumps(done_chunk)
                    if self.verbose:
                        logger.info(f"Yielding done chunk: {len(done_json)} bytes total")
                        logger.info(f"Done chunk keys: {list(done_chunk.keys())}, has audio: {'audio' in done_chunk}")
                        if 'audio' in done_chunk:
                            logger.info(f"Audio field present, length: {len(done_chunk['audio'])}, format: {done_chunk.get('audioFormat')}")
                        # Log first 100 chars of JSON to verify structure
                        logger.info(f"Done chunk JSON preview: {done_json[:200]}...")
                    yield f"data: {done_json}\n\n"
                
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
    
    async def _generate_audio(
        self,
        text: str,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> tuple[Optional[bytes], Optional[str]]:
        """
        Generate audio from text using the adapter's audio provider.

        Args:
            text: Text to convert to speech
            adapter_name: Adapter name to get audio provider from
            tts_voice: Optional voice to use for TTS
            language: Optional language code

        Returns:
            Tuple of (audio_data, audio_format) or (None, None) if generation fails
        """
        try:
            # Get TTS limits from config
            sound_config = self.config.get('sound', {})
            tts_limits = sound_config.get('tts_limits', {})
            max_text_length = tts_limits.get('max_text_length', 4096)
            max_audio_size_mb = tts_limits.get('max_audio_size_mb', 5)
            truncate_text = tts_limits.get('truncate_text', True)
            warn_on_truncate = tts_limits.get('warn_on_truncate', True)

            # Apply text length limit
            original_text_length = len(text)
            if original_text_length > max_text_length:
                if truncate_text:
                    # Truncate text at sentence boundary if possible
                    text = text[:max_text_length]
                    # Try to end at a sentence boundary
                    last_period = text.rfind('.')
                    last_question = text.rfind('?')
                    last_exclaim = text.rfind('!')
                    last_sentence_end = max(last_period, last_question, last_exclaim)
                    if last_sentence_end > max_text_length * 0.8:  # At least 80% of allowed length
                        text = text[:last_sentence_end + 1]

                    if warn_on_truncate:
                        logger.warning(
                            f"TTS text truncated from {original_text_length} to {len(text)} chars "
                            f"(limit: {max_text_length})"
                        )
                else:
                    logger.warning(
                        f"TTS text length ({original_text_length}) exceeds limit ({max_text_length}), "
                        f"skipping audio generation"
                    )
                    return None, None

            # Get audio provider from adapter config
            audio_provider = None
            if adapter_name and hasattr(self, 'pipeline') and self.pipeline.container.has('adapter_manager'):
                adapter_manager = self.pipeline.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if adapter_config:
                    audio_provider = adapter_config.get('audio_provider')

            # Fallback to global config if adapter doesn't specify
            if not audio_provider:
                audio_provider = sound_config.get('provider', 'openai')

            if not audio_provider:
                logger.warning("No audio provider configured")
                return None, None

            # Import audio service factory
            from ai_services.factory import AIServiceFactory
            from ai_services.base import ServiceType
            from ai_services.registry import register_all_services

            # Ensure services are registered
            register_all_services(self.config)

            # Create audio service
            audio_service = AIServiceFactory.create_service(
                ServiceType.AUDIO,
                audio_provider,
                self.config
            )

            if not audio_service:
                logger.warning(f"Failed to create audio service for provider: {audio_provider}")
                return None, None

            # Initialize service if needed
            if hasattr(audio_service, 'initialize'):
                await audio_service.initialize()

            # Generate audio
            audio_data = await audio_service.text_to_speech(
                text=text,
                voice=tts_voice,
                format=None  # Use default format
            )

            # Check audio size limit
            max_audio_size_bytes = max_audio_size_mb * 1024 * 1024
            if len(audio_data) > max_audio_size_bytes:
                logger.warning(
                    f"Generated audio size ({len(audio_data) / 1024 / 1024:.2f}MB) exceeds "
                    f"limit ({max_audio_size_mb}MB), skipping audio"
                )
                return None, None

            # Determine format from provider config
            sounds_config = self.config.get('sounds', {})
            provider_config = sounds_config.get(audio_provider, {})
            audio_format = provider_config.get('tts_format', 'mp3')

            if self.verbose:
                logger.info(f"Generated audio: {len(audio_data)} bytes, format: {audio_format}")
            return audio_data, audio_format

        except Exception as e:
            logger.error(f"Error generating audio: {str(e)}", exc_info=True)
            return None, None
