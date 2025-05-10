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
        # Initialize language detector
        self.language_detector = LanguageDetector(verbose=self.verbose)
    
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
                    enhanced_prompt = f"""IMPORTANT: The user's message is in {language_name}. You MUST respond in {language_name} only.

{original_prompt}"""
                    
                    if self.verbose:
                        logger.info(f"Enhanced prompt with language instruction for: {language_name}")
                    
                    # Create a temporary system prompt with the enhanced content
                    try:
                        temp_prompt_name = f"temp_lang_{detected_lang}_{str(system_prompt_id)[-6:]}"
                        temp_prompt_id = await self.llm_client.prompt_service.create_prompt(
                            name=temp_prompt_name,
                            prompt_text=enhanced_prompt,
                            version="temp"
                        )
                        return temp_prompt_id
                    except Exception as e:
                        logger.error(f"Failed to create temporary language-enhanced prompt: {str(e)}")
                        # Fall back to original prompt ID if enhancement fails
                        return system_prompt_id
            
        # Return original prompt ID if no modification was made
        return system_prompt_id
    
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
            response_data = await self.llm_client.generate_response(
                message=message,
                collection_name=collection_name,
                system_prompt_id=enhanced_prompt_id
            )
            
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
            
            # Generate and stream response
            accumulated_text = ""
            
            async for chunk in self.llm_client.generate_response_stream(
                message=message,
                collection_name=collection_name,
                system_prompt_id=enhanced_prompt_id
            ):
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
                                
                except json.JSONDecodeError:
                    logger.error(f"Error parsing chunk as JSON: {chunk}")
                    continue
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            error_json = json.dumps({"error": str(e)})
            yield f"data: {error_json}\n\n"