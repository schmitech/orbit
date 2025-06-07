"""
Chat service for processing chat messages
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
from bson import ObjectId  # Add this import for ObjectId
import threading
from queue import Queue

from utils.text_utils import fix_text_formatting, mask_api_key
from utils.language_detector import LanguageDetector
from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)

class ChatService:
    """Handles chat-related functionality"""
    
    def __init__(self, config: Dict[str, Any], llm_client, logger_service, chat_history_service=None):
        self.config = config
        self.llm_client = llm_client
        self.logger_service = logger_service
        self.chat_history_service = chat_history_service
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        
        # Chat history configuration
        self.chat_history_config = config.get('chat_history', {})
        self.chat_history_enabled = _is_true_value(self.chat_history_config.get('enabled', True))
        
        # Messages configuration
        self.messages_config = config.get('messages', {})
        
        # Initialize language detector only if enabled
        self.language_detection_enabled = _is_true_value(config.get('general', {}).get('language_detection', True))
        if self.language_detection_enabled:
            try:
                self.language_detector = LanguageDetector(verbose=self.verbose)
                if self.verbose:
                    logger.info("Language detection enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize language detector: {str(e)}, disabling language detection")
                self.language_detection_enabled = False
                self.language_detector = None
        else:
            self.language_detector = None
            if self.verbose:
                logger.info("Language detection disabled")
                
        # Thread-safe queue for streaming responses
        self._stream_queues = {}
        self._stream_locks = {}
    
    async def _get_conversation_context(self, session_id: Optional[str]) -> List[Dict[str, str]]:
        """
        Get conversation context from history for the current session
        
        Args:
            session_id: The session identifier
            
        Returns:
            List of previous messages formatted for LLM context
        """
        if not self.chat_history_enabled or not self.chat_history_service or not session_id:
            return []
            
        try:
            # IMPORTANT: Check conversation limits BEFORE retrieving context
            # This ensures archiving happens before we get the history for this request
            await self.chat_history_service._check_conversation_limits(session_id)
            
            # Get context messages from chat history (now after any archiving)
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
        Store a conversation turn in chat history
        
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
    
    async def _log_conversation(self, query: str, response: str, client_ip: str, api_key: Optional[str] = None):
        """Log conversation asynchronously without delaying the main response."""
        try:
            await self.logger_service.log_conversation(
                query=query,
                response=response,
                ip=client_ip,
                backend=None,
                blocked=False,
                api_key=api_key
            )
        except Exception as e:
            logger.error(f"Error logging conversation: {str(e)}", exc_info=True)
    
    async def _log_request(self, message: str, client_ip: str, collection_name: str):
        """Log an incoming request"""
        if self.verbose:
            logger.info(f"Processing chat message from {client_ip}, collection: {collection_name}")
            logger.info(f"Message: {message}")
    
    async def _log_response(self, response: str, client_ip: str):
        """Log a response"""
        if self.verbose:
            logger.info(f"Generated response for {client_ip}")
            logger.info(f"Response: {response[:100]}...")  # Log just the beginning to avoid huge logs
    
    async def _detect_and_enhance_prompt(self, message: str, system_prompt_id: Optional[ObjectId] = None) -> tuple[Optional[ObjectId], Optional[str]]:
        """
        Detect message language and prepare language enhancement
        
        Args:
            message: The chat message to detect language from
            system_prompt_id: Optional ID of the original system prompt
            
        Returns:
            Tuple of (system_prompt_id, language_instruction):
            - system_prompt_id: Original or None if enhanced in-place
            - language_instruction: Language instruction to add, or None if not needed
        """
        try:
            # Skip language detection if disabled
            if not self.language_detection_enabled:
                return system_prompt_id, None
                
            # Don't modify anything if the language detector is not available
            if not self.language_detector:
                if self.verbose:
                    logger.warning("Language detector not available, skipping language enhancement")
                return system_prompt_id, None
                
            # Detect the language of the message
            try:
                detected_lang = self.language_detector.detect(message)
            except Exception as lang_error:
                logger.warning(f"Language detection failed: {str(lang_error)}, defaulting to English")
                detected_lang = "en"
            
            if self.verbose:
                logger.info(f"Language detection result: '{detected_lang}' for message: '{message[:50]}...'")
                
            # Only enhance if language is not English
            if detected_lang != 'en':
                # Get language name from ISO code
                try:
                    import pycountry
                    try:
                        language = pycountry.languages.get(alpha_2=detected_lang)
                        language_name = language.name if language else f"the language with code '{detected_lang}'"
                    except (AttributeError, KeyError):
                        language_name = f"the language with code '{detected_lang}'"
                except ImportError:
                    language_names = {
                        'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
                        'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
                        'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'hi': 'Hindi'
                    }
                    language_name = language_names.get(detected_lang, f"the language with code '{detected_lang}'")
                
                # Create language instruction
                language_instruction = f"\n\nIMPORTANT: The user's message is in {language_name}. You MUST respond in {language_name} only."
                
                # Check if we're in inference-only mode
                inference_only = self.config.get('general', {}).get('inference_only', False)
                
                if inference_only:
                    # Inference-only mode: language instruction goes to user message
                    if self.verbose:
                        logger.info(f"Inference-only mode: Will append language instruction for {language_name}")
                        logger.info(f"Language instruction content: '{language_instruction[:100]}...'")
                    return None, language_instruction
                    
                else:
                    # Full mode: language instruction goes to system prompt
                    if self.verbose:
                        logger.info(f"Full mode: Language instruction will be added to system prompt for: {language_name}")
                    
                    # If we have a stored prompt, enhance it
                    if (hasattr(self.llm_client, 'prompt_service') and 
                        self.llm_client.prompt_service and 
                        system_prompt_id):
                        
                        try:
                            prompt_doc = await self.llm_client.prompt_service.get_prompt_by_id(system_prompt_id)
                            if prompt_doc and 'prompt' in prompt_doc:
                                enhanced_prompt = prompt_doc['prompt'] + language_instruction
                                self.llm_client.override_system_prompt = enhanced_prompt
                                
                                if self.verbose:
                                    logger.info(f"Enhanced stored system prompt with language instruction")
                                return None, None
                        except Exception as prompt_error:
                            logger.warning(f"Failed to retrieve/enhance system prompt: {str(prompt_error)}")
                    
                    # If no stored prompt available, just return the language instruction
                    # The LLM client will use its default empty system prompt
                    return system_prompt_id, language_instruction
                
            # No language enhancement needed
            return system_prompt_id, None
            
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {str(e)}")
            return system_prompt_id, None
    
    async def _process_chat_base(self, message: str, client_ip: str, collection_name: str, 
                                 system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                                 session_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Base method for processing chat messages, handling common functionality.
        
        Args:
            message: The chat message
            client_ip: Client IP address
            collection_name: Collection name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
            api_key: Optional API key for authentication
            session_id: Optional session identifier for chat history
            user_id: Optional user identifier
            
        Returns:
            Tuple of (enhanced_prompt_id, response_data, metadata)
        """
        # Log the incoming message and parameters
        await self._log_request(message, client_ip, collection_name)
        
        if self.verbose:
            # Mask API key for logging
            masked_api_key = "None"
            if api_key:
                masked_api_key = mask_api_key(api_key, show_last=True)
            
            logger.info(f"System prompt ID: {system_prompt_id}")
            logger.info(f"API key: {masked_api_key}")
            logger.info(f"Session ID: {session_id}")
            logger.info(f"User ID: {user_id}")
            if system_prompt_id:
                # Log the prompt details if we have a prompt service on the LLM client
                if hasattr(self.llm_client, 'prompt_service') and self.llm_client.prompt_service:
                    prompt_doc = await self.llm_client.prompt_service.get_prompt_by_id(system_prompt_id)
                    if prompt_doc:
                        logger.info(f"Using system prompt: {prompt_doc.get('name', 'Unknown')}")
                        logger.info(f"Prompt content (first 100 chars): {prompt_doc.get('prompt', '')[:100]}...")
                    else:
                        logger.warning(f"System prompt ID {system_prompt_id} not found")
        
        # Get conversation context if session is provided
        context_messages = await self._get_conversation_context(session_id)
        
        # Detect language and get enhancement instructions
        enhanced_prompt_id, language_instruction = await self._detect_and_enhance_prompt(message, system_prompt_id)
        
        # Prepare the message (add language instruction if for inference-only mode)
        final_message = message
        if language_instruction and self.config.get('general', {}).get('inference_only', False):
            if self.verbose:
                logger.info(f"Original user message: '{message}'")
                logger.info(f"Language instruction to append: '{language_instruction[:100]}...'")
            final_message = message + language_instruction
            if self.verbose:
                logger.info(f"Final combined message: '{final_message[:200]}...'")
        else:
            if self.verbose:
                logger.info(f"No language instruction needed - using original message: '{message}'")
        
        # Prepare metadata for storage
        metadata = {
            "collection_name": collection_name,
            "client_ip": client_ip
        }
        
        # Generate response with context
        if enhanced_prompt_id is None:
            # Using override system prompt (full mode with language enhancement) or no system prompt (inference-only)
            response_data = await self.llm_client.generate_response(
                message=final_message,
                collection_name=collection_name,
                context_messages=context_messages
            )
            # Clear any overrides after use
            if hasattr(self.llm_client, 'clear_override_system_prompt'):
                self.llm_client.clear_override_system_prompt()
            elif hasattr(self.llm_client, 'override_system_prompt'):
                self.llm_client.override_system_prompt = None
        else:
            # Using stored system prompt
            response_data = await self.llm_client.generate_response(
                message=final_message,
                collection_name=collection_name,
                system_prompt_id=enhanced_prompt_id,
                context_messages=context_messages
            )
            
        return enhanced_prompt_id, response_data, metadata

    async def process_chat(self, message: str, client_ip: str, collection_name: str, 
                          system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                          session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a chat message and return a response
        
        Args:
            message: The chat message
            client_ip: Client IP address
            collection_name: Collection name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
            api_key: Optional API key for authentication
            session_id: Optional session identifier for chat history
            user_id: Optional user identifier
        """
        try:
            # Use base processing
            _, response_data, metadata = await self._process_chat_base(
                message, client_ip, collection_name, system_prompt_id, api_key, session_id, user_id
            )
            
            # Ensure response_data is a dictionary
            if not isinstance(response_data, dict):
                logger.error(f"Invalid response format: {response_data}")
                return {"error": "Invalid response format from LLM client"}
            
            # Check if the response was blocked by moderation
            if response_data.get("error"):
                error_msg = response_data["error"]
                # Log the blocked response
                await self._log_response(error_msg, client_ip)
                
                # Log conversation if API key is provided
                if api_key:
                    await self._log_conversation(message, error_msg, client_ip, api_key)
                
                # Store blocked message in history if enabled
                if session_id:
                    await self._store_conversation_turn(
                        session_id=session_id,
                        user_message=message,
                        assistant_response=f"[BLOCKED] {error_msg}",
                        user_id=user_id,
                        api_key=api_key,
                        metadata={**metadata, "blocked": True}
                    )
                
                # Format moderation error in MCP protocol format
                return {
                    "error": {
                        "code": -32603,
                        "message": error_msg
                    }
                }
            
            # Get response text and ensure it exists
            response = response_data.get("response")
            if not response:
                logger.error("No response text in LLM response")
                return {"error": "No response generated"}
                
            # Clean and format the response
            response = fix_text_formatting(response)
            
            # Check for conversation limit warning BEFORE storing conversation
            # This ensures we catch the warning before the count changes
            warning = await self._check_conversation_limit_warning(session_id)
            if warning:
                # Append warning to the response
                response = f"{response}\n\n---\n{warning}"
                # Update the response in response_data
                response_data["response"] = response
                
                if self.verbose:
                    logger.info(f"Added conversation limit warning for session {session_id}")
            
            # Log the response
            await self._log_response(response, client_ip)
            
            # Store conversation turn in history if enabled
            if session_id:
                await self._store_conversation_turn(
                    session_id=session_id,
                    user_message=message,
                    assistant_response=response,
                    user_id=user_id,
                    api_key=api_key,
                    metadata=metadata
                )
            
            # Log conversation if API key is provided
            if api_key:
                await self._log_conversation(message, response, client_ip, api_key)
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}")
            return {"error": str(e)}
    
    async def process_chat_stream(self, message: str, client_ip: str, collection_name: str, 
                                 system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None,
                                 session_id: Optional[str] = None, user_id: Optional[str] = None):
        try:
            # Get conversation context and language detection
            context_messages = await self._get_conversation_context(session_id)
            enhanced_prompt_id, language_instruction = await self._detect_and_enhance_prompt(message, system_prompt_id)
            
            # Prepare the message (add language instruction if for inference-only mode)
            final_message = message
            if language_instruction and self.config.get('general', {}).get('inference_only', False):
                if self.verbose:
                    logger.info(f"STREAMING - Original user message: '{message}'")
                    logger.info(f"STREAMING - Language instruction to append: '{language_instruction[:100]}...'")
                final_message = message + language_instruction
                if self.verbose:
                    logger.info(f"STREAMING - Final combined message: '{final_message[:200]}...'")
            else:
                if self.verbose:
                    logger.info(f"STREAMING - No language instruction needed - using original message: '{message}'")
            
            # Prepare metadata for storage
            metadata = {
                "collection_name": collection_name,
                "client_ip": client_ip
            }
            
            # Create a unique stream ID for this session
            stream_id = f"{session_id}_{id(message)}"
            
            # Initialize thread-safe queue and lock for this stream
            self._stream_queues[stream_id] = Queue()
            self._stream_locks[stream_id] = threading.Lock()
            
            # Generate and stream response
            accumulated_text = ""
            
            try:
                # Generate the streaming response
                if enhanced_prompt_id is None:
                    # Using override system prompt (full mode with language enhancement) or no system prompt (inference-only)
                    if self.verbose:
                        logger.info(f"STREAMING - Calling generate_response_stream with enhanced_prompt_id=None")
                    stream_generator = self.llm_client.generate_response_stream(
                        message=final_message,
                        collection_name=collection_name,
                        context_messages=context_messages
                    )
                else:
                    # Using stored system prompt
                    if self.verbose:
                        logger.info(f"STREAMING - Calling generate_response_stream with system_prompt_id={enhanced_prompt_id}")
                    stream_generator = self.llm_client.generate_response_stream(
                        message=final_message,
                        collection_name=collection_name,
                        system_prompt_id=enhanced_prompt_id,
                        context_messages=context_messages
                    )
                
                if self.verbose:
                    logger.info(f"STREAMING - Stream generator created, starting to iterate")
                    
                async for chunk in stream_generator:
                    try:
                        if self.verbose:
                            logger.info(f"STREAMING - Received chunk: {chunk[:200]}...")
                        
                        chunk_data = json.loads(chunk)
                        
                        if self.verbose:
                            logger.info(f"STREAMING - Parsed chunk data keys: {list(chunk_data.keys())}")
                        
                        # If there's an error in the chunk, yield it and stop
                        if "error" in chunk_data:
                            if self.verbose:
                                logger.info(f"STREAMING - Error in chunk: {chunk_data['error']}")
                            yield f"data: {chunk}\n\n"
                            
                            # Store blocked message in history if enabled
                            if session_id:
                                await self._store_conversation_turn(
                                    session_id=session_id,
                                    user_message=message,
                                    assistant_response=f"[BLOCKED] {chunk_data['error']}",
                                    user_id=user_id,
                                    api_key=api_key,
                                    metadata={**metadata, "blocked": True}
                                )
                            break
                            
                        # Track if we've processed a response in this chunk
                        response_processed = False
                        
                        # If there's a response, process it
                        if "response" in chunk_data:
                            if self.verbose:
                                logger.info(f"STREAMING - Processing response chunk: '{chunk_data['response'][:100]}...'")
                            
                            # Clean and format the response
                            cleaned_chunk = fix_text_formatting(chunk_data["response"])
                            
                            # Thread-safe accumulation
                            with self._stream_locks[stream_id]:
                                accumulated_text += cleaned_chunk
                            
                            # Create a proper chunk response for MCP protocol compatibility
                            chunk_response = {
                                "response": cleaned_chunk,
                                "done": False
                            }
                            yield f"data: {json.dumps(chunk_response)}\n\n"
                            response_processed = True
                        
                        # Handle done marker and sources - but avoid duplicating response content
                        if chunk_data.get("done", False):
                            if self.verbose:
                                logger.info(f"STREAMING - Received done marker, response_processed: {response_processed}")
                            
                            if not response_processed:
                                # Only yield the original chunk if we haven't already processed its response
                                yield f"data: {chunk}\n\n"
                            else:
                                # Send a clean done marker without duplicating the response
                                done_chunk = {"done": True}
                                if "sources" in chunk_data:
                                    done_chunk["sources"] = chunk_data["sources"]
                                yield f"data: {json.dumps(done_chunk)}\n\n"
                            
                            # Log the complete response when done
                            await self._log_response(accumulated_text, client_ip)
                            
                            # Check for conversation limit warning BEFORE storing conversation
                            # This ensures we catch the warning before the count changes
                            warning = await self._check_conversation_limit_warning(session_id)
                            if warning:
                                # Send the warning as a separate chunk in the correct format
                                warning_text = f"\n\n---\n{warning}"
                                accumulated_text += warning_text
                                # Use the correct format the client expects
                                warning_chunk = json.dumps({
                                    "response": warning_text,
                                    "done": False
                                })
                                yield f"data: {warning_chunk}\n\n"
                                
                                if self.verbose:
                                    logger.info(f"Added conversation limit warning to stream for session {session_id}")
                            
                            # Store conversation turn in history if enabled
                            if session_id and accumulated_text:
                                await self._store_conversation_turn(
                                    session_id=session_id,
                                    user_message=message,
                                    assistant_response=accumulated_text,
                                    user_id=user_id,
                                    api_key=api_key,
                                    metadata=metadata
                                )
                            
                            # Log conversation to Elasticsearch if API key is provided
                            if api_key:
                                await self._log_conversation(message, accumulated_text, client_ip, api_key)
                            
                            # Clear the override after use if we used in-memory override
                            if enhanced_prompt_id is None and hasattr(self.llm_client, 'override_system_prompt'):
                                if hasattr(self.llm_client, 'clear_override_system_prompt'):
                                    self.llm_client.clear_override_system_prompt()
                                else:
                                    self.llm_client.override_system_prompt = None
                            
                            if self.verbose:
                                logger.info(f"STREAMING - Breaking out of loop after done=True")
                            # Break out of the loop when done=True
                            break
                                    
                        elif "sources" in chunk_data and not response_processed:
                            # Only yield sources if we haven't processed a response in this chunk
                            if self.verbose:
                                logger.info(f"STREAMING - Yielding sources chunk")
                            yield f"data: {chunk}\n\n"
                                
                    except json.JSONDecodeError:
                        logger.error(f"Error parsing chunk as JSON: {chunk}")
                        continue
                        
            except Exception as stream_error:
                logger.error(f"Error in stream generation: {str(stream_error)}")
                # Send error as a proper JSON chunk
                error_chunk = json.dumps({
                    "error": f"Stream generation failed: {str(stream_error)}",
                    "done": True
                })
                yield f"data: {error_chunk}\n\n"
                        
            finally:
                # Clean up stream resources
                if stream_id in self._stream_queues:
                    del self._stream_queues[stream_id]
                if stream_id in self._stream_locks:
                    del self._stream_locks[stream_id]
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            error_json = json.dumps({"error": str(e), "done": True})
            yield f"data: {error_json}\n\n"

    async def _check_conversation_limit_warning(self, session_id: Optional[str]) -> Optional[str]:
        """
        Check if the conversation is approaching the limit and return a warning if needed
        
        Args:
            session_id: The session identifier
            
        Returns:
            Warning message if approaching limit, None otherwise
        """
        if not self.chat_history_enabled or not self.chat_history_service or not session_id:
            return None
            
        try:
            # Use in-memory session message counts for accurate current count
            # This reflects the count after any archiving that may have occurred
            current_count = self.chat_history_service._session_message_counts.get(session_id, 0)
            
            # Get the maximum allowed messages for this session
            max_messages = self.chat_history_service.max_conversation_messages
            
            # Only warn when we're about to hit the limit for the FIRST time
            # After archiving, we should have room again and not keep warning
            # The warning should trigger when: current + 2 (next exchange) = max_messages
            if current_count + 2 == max_messages:
                # Get the warning message from config with fallback
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