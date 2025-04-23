"""
Chat service for processing chat messages
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional
from bson import ObjectId  # Add this import for ObjectId

from utils.text_utils import fix_text_formatting
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
    
    async def _log_conversation(self, query: str, response: str, client_ip: str, api_key: Optional[str] = None):
        """Log conversation asynchronously without delaying the main response."""
        try:
            await self.logger_service.log_conversation(
                query=query,
                response=response,
                ip=client_ip,
                backend=self.config.get('ollama', {}).get('model', 'ollama'),
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
    
    async def process_chat(self, message: str, client_ip: str, collection_name: str, system_prompt_id: Optional[ObjectId] = None) -> Dict[str, Any]:
        """
        Process a chat message and return a response
        
        Args:
            message: The chat message
            client_ip: Client IP address
            collection_name: Collection name to use for retrieval
            system_prompt_id: Optional system prompt ID to use
        """
        try:
            # Log the incoming message
            await self._log_request(message, client_ip, collection_name)
            
            # Generate response
            response = ""
            async for chunk in self.llm_client.generate_response(
                message, 
                stream=False, 
                collection_name=collection_name,
                system_prompt_id=system_prompt_id
            ):
                response += chunk
                
            # Clean and format the response
            response = fix_text_formatting(response)
            
            # Log the response
            await self._log_response(response, client_ip)
            
            return {"response": response}
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}")
            return {"error": str(e)}
    
    async def process_chat_stream(self, message: str, client_ip: str, collection_name: str, system_prompt_id: Optional[ObjectId] = None):
        try:
            # Log the incoming message
            await self._log_request(message, client_ip, collection_name)
            
            # Generate and stream response
            response_chunks = []
            accumulated_text = ""
            
            async for chunk in self.llm_client.generate_response(
                message, 
                stream=True, 
                collection_name=collection_name,
                system_prompt_id=system_prompt_id
            ):
                # Clean and format each chunk
                cleaned_chunk = fix_text_formatting(chunk)
                response_chunks.append(cleaned_chunk)
                
                # Accumulate text
                accumulated_text += cleaned_chunk
                
                # Send the accumulated text so far, not just the new chunk
                yield f"data: {json.dumps({'text': accumulated_text})}\n\n"
                
            # Log the complete response
            complete_response = accumulated_text
            await self._log_response(complete_response, client_ip)
            
            # Send end of stream marker
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            error_json = json.dumps({"error": str(e)})
            yield f"data: {error_json}\n\n"