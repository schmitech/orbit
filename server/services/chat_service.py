"""
Chat service for processing chat messages
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional
from bson import ObjectId  # Add this import for ObjectId

from utils.text_utils import fix_text_formatting, mask_api_key
from utils.language_detector import LanguageDetector
from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)

class ChatService:
    """Handles chat-related functionality"""
    
    def __init__(self, config: Dict[str, Any], llm_client, logger_service):
        self.config = config
        self.llm_client = llm_client
        self.logger_service = logger_service
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        # Initialize language detector only if enabled
        self.language_detection_enabled = _is_true_value(config.get('general', {}).get('language_detection', True))
        if self.language_detection_enabled:
            self.language_detector = LanguageDetector(verbose=self.verbose)
            if self.verbose:
                logger.info("Language detection enabled")
        else:
            self.language_detector = None
            if self.verbose:
                logger.info("Language detection disabled")
    
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
    
    async def _detect_and_enhance_prompt(self, message: str, system_prompt_id: Optional[ObjectId] = None) -> Optional[ObjectId]:
        """
        Detect message language and enhance the system prompt if needed
        
        Args:
            message: The chat message to detect language from
            system_prompt_id: Optional ID of the original system prompt
            
        Returns:
            The original system_prompt_id (if no language detection enhancements needed)
            or None if the prompt was enhanced in-place and doesn't need to be fetched again
        """
        # Skip language detection if disabled
        if not self.language_detection_enabled:
            return system_prompt_id
            
        # Don't modify anything if there's no prompt service
        if not hasattr(self.llm_client, 'prompt_service') or not self.llm_client.prompt_service:
            return system_prompt_id
            
        # Detect the language of the message
        detected_lang = self.language_detector.detect(message)
        
        if self.verbose:
            logger.info(f"Detected language: {detected_lang}")
            
        # Only proceed if we have a system prompt ID and a detected language
        if system_prompt_id and detected_lang:
            # Get the original prompt
            prompt_doc = await self.llm_client.prompt_service.get_prompt_by_id(system_prompt_id)
            if prompt_doc and 'prompt' in prompt_doc:
                original_prompt = prompt_doc['prompt']
                
                # Add language instruction if it's not English
                if detected_lang != 'en':
                    # Get language name from ISO code in a more dynamic way
                    try:
                        # Try to use the pycountry library if available
                        import pycountry
                        try:
                            language = pycountry.languages.get(alpha_2=detected_lang)
                            language_name = language.name if language else f"the language with code '{detected_lang}'"
                        except (AttributeError, KeyError):
                            # Fallback if the language code is not found
                            language_name = f"the language with code '{detected_lang}'"
                    except ImportError:
                        # Fallback to common languages if pycountry is not available
                        language_names = {
                            'en': 'English',
                            'es': 'Spanish',
                            'fr': 'French',
                            'de': 'German',
                            'it': 'Italian',
                            'pt': 'Portuguese',
                            'ru': 'Russian',
                            'zh': 'Chinese',
                            'ja': 'Japanese',
                            'ko': 'Korean',
                            'ar': 'Arabic',
                            'hi': 'Hindi'
                        }
                        language_name = language_names.get(detected_lang, f"the language with code '{detected_lang}'")
                    
                    # Create enhanced prompt with language instruction
                    enhanced_prompt = f"""{original_prompt}

IMPORTANT: The user's message is in {language_name}. You MUST respond in {language_name} only."""
                    
                    if self.verbose:
                        logger.info(f"Enhanced prompt with language instruction for: {language_name}")
                        logger.info(f"Full enhanced prompt:\n{enhanced_prompt}")
                    
                    # Set the enhanced prompt directly on the LLM client
                    self.llm_client.override_system_prompt = enhanced_prompt
                    return None
            
        # Return original prompt ID if no modification was made
        return system_prompt_id
    
    async def _process_chat_base(self, message: str, client_ip: str, collection_name: str, system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None):
        """
        Base method for processing chat messages, handling common functionality.
        
        Args:
            message: The chat message
            client_ip: Client IP address
            collection_name: Collection name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
            api_key: Optional API key for authentication
            
        Returns:
            Tuple of (enhanced_prompt_id, response_data)
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
            if system_prompt_id:
                # Log the prompt details if we have a prompt service on the LLM client
                if hasattr(self.llm_client, 'prompt_service') and self.llm_client.prompt_service:
                    prompt_doc = await self.llm_client.prompt_service.get_prompt_by_id(system_prompt_id)
                    if prompt_doc:
                        logger.info(f"Using system prompt: {prompt_doc.get('name', 'Unknown')}")
                        logger.info(f"Prompt content (first 100 chars): {prompt_doc.get('prompt', '')[:100]}...")
                    else:
                        logger.warning(f"System prompt ID {system_prompt_id} not found")
        
        # Detect language and enhance the system prompt if needed
        enhanced_prompt_id = await self._detect_and_enhance_prompt(message, system_prompt_id)
        
        # Generate response
        if enhanced_prompt_id is None:
            # If enhanced_prompt_id is None, we've set an override prompt in memory
            response_data = await self.llm_client.generate_response(
                message=message,
                collection_name=collection_name
            )
            # Clear the override after use
            if hasattr(self.llm_client, 'clear_override_system_prompt'):
                self.llm_client.clear_override_system_prompt()
            elif hasattr(self.llm_client, 'override_system_prompt'):
                self.llm_client.override_system_prompt = None
        else:
            response_data = await self.llm_client.generate_response(
                message=message,
                collection_name=collection_name,
                system_prompt_id=enhanced_prompt_id
            )
            
        return enhanced_prompt_id, response_data

    async def process_chat(self, message: str, client_ip: str, collection_name: str, system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a chat message and return a response
        
        Args:
            message: The chat message
            client_ip: Client IP address
            collection_name: Collection name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
            api_key: Optional API key for authentication
        """
        try:
            # Use base processing
            _, response_data = await self._process_chat_base(message, client_ip, collection_name, system_prompt_id, api_key)
            
            # Check if the response was blocked by moderation
            if "error" in response_data:
                # Log the blocked response
                await self._log_response(response_data["error"], client_ip)
                
                # Log conversation if API key is provided
                if api_key:
                    await self._log_conversation(message, response_data["error"], client_ip, api_key)
                
                # Format moderation error in MCP protocol format
                return {
                    "error": {
                        "code": -32603,
                        "message": response_data["error"]
                    }
                }
            
            response = response_data.get("response", "")
            # Clean and format the response
            response = fix_text_formatting(response)
            
            # Log the response
            await self._log_response(response, client_ip)
            
            # Log conversation if API key is provided
            if api_key:
                await self._log_conversation(message, response, client_ip, api_key)
            
            return response_data
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}")
            return {"error": str(e)}
    
    async def process_chat_stream(self, message: str, client_ip: str, collection_name: str, system_prompt_id: Optional[ObjectId] = None, api_key: Optional[str] = None):
        try:
            # Use base processing
            enhanced_prompt_id, _ = await self._process_chat_base(message, client_ip, collection_name, system_prompt_id, api_key)
            
            # Generate and stream response
            accumulated_text = ""
            
            # Choose the correct call based on whether we're using an in-memory override or a prompt ID
            if enhanced_prompt_id is None:
                # If enhanced_prompt_id is None, we've set an override prompt in memory
                stream_generator = self.llm_client.generate_response_stream(
                    message=message,
                    collection_name=collection_name
                )
            else:
                stream_generator = self.llm_client.generate_response_stream(
                    message=message,
                    collection_name=collection_name,
                    system_prompt_id=enhanced_prompt_id
                )
                
            async for chunk in stream_generator:
                try:
                    chunk_data = json.loads(chunk)
                    
                    # If there's an error in the chunk, yield it and stop
                    if "error" in chunk_data:
                        yield f"data: {chunk}\n\n"
                        break
                        
                    # If there's a response, process it
                    if "response" in chunk_data:
                        # Clean and format the response
                        cleaned_chunk = fix_text_formatting(chunk_data["response"])
                        accumulated_text += cleaned_chunk
                        
                        # Send the accumulated text so far
                        yield f"data: {json.dumps({'text': accumulated_text})}\n\n"
                    
                    # If we have sources or done marker, pass them through
                    if chunk_data.get("done", False) or "sources" in chunk_data:
                        yield f"data: {chunk}\n\n"
                        
                        if chunk_data.get("done", False):
                            # Log the complete response when done
                            await self._log_response(accumulated_text, client_ip)
                            
                            # Log conversation to Elasticsearch if API key is provided
                            if api_key:
                                await self._log_conversation(message, accumulated_text, client_ip, api_key)
                            
                            # Clear the override after use if we used in-memory override
                            if enhanced_prompt_id is None:
                                if hasattr(self.llm_client, 'clear_override_system_prompt'):
                                    self.llm_client.clear_override_system_prompt()
                                elif hasattr(self.llm_client, 'override_system_prompt'):
                                    self.llm_client.override_system_prompt = None
                                
                except json.JSONDecodeError:
                    logger.error(f"Error parsing chunk as JSON: {chunk}")
                    continue
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            error_json = json.dumps({"error": str(e)})
            yield f"data: {error_json}\n\n"