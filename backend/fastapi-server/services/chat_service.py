"""
Chat service for processing chat messages
"""

import json
import asyncio
import logging
from typing import Dict, Any
from fastapi import HTTPException

from utils.text_utils import fix_text_formatting
from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)


class ChatService:
    """Handles chat-related functionality"""
    
    def __init__(self, config: Dict[str, Any], llm_client, logger_service=None):
        self.config = config
        self.llm_client = llm_client
        self.logger_service = logger_service
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
    
    async def process_chat(self, message: str, voice_enabled: bool, client_ip: str) -> Dict[str, Any]:
        """Process a chat message and return a response"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Generate response
            response_text = ""
            async for chunk in self.llm_client.generate_response(message, stream=False):
                response_text += chunk
            
            # Apply text fixes
            response_text = fix_text_formatting(response_text)
            
            # Log conversation if logger service is available
            if self.logger_service:
                await self.logger_service.log_conversation(message, response_text, client_ip)
            
            if self.verbose:
                end_time = asyncio.get_event_loop().time()
                logger.info(f"Chat processed in {end_time - start_time:.3f}s")
            
            # Return response
            result = {
                "response": response_text,
                "audio": None  # We'll leave audio handling as a future enhancement
            }
            
            return result
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def process_chat_stream(self, message: str, voice_enabled: bool, client_ip: str):
        """Process a chat message and stream the response"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Keep track of the full response for post-processing
            full_text = ""
            first_token_received = False
            
            # Get stream setting from config or default to true
            # Handle both string and boolean values
            stream_enabled = _is_true_value(self.config['ollama'].get('stream', True))
            
            # Collect chunks to build the response
            async for chunk in self.llm_client.generate_response(message, stream=stream_enabled):
                if not first_token_received:
                    first_token_received = True
                    first_token_time = asyncio.get_event_loop().time()
                    if self.verbose:
                        logger.info(f"Time to first token: {first_token_time - start_time:.3f}s")
                
                full_text += chunk
                
                # Apply text fixes (add spaces where needed)
                fixed_text = fix_text_formatting(full_text)
                
                # Send the current fixed text
                yield f"data: {json.dumps({'text': fixed_text, 'done': False})}\n\n"
            
            # Send final done message
            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
            
            if self.verbose:
                end_time = asyncio.get_event_loop().time()
                logger.info(f"Stream completed in {end_time - start_time:.3f}s")
            
            # Log conversation if logger service is available
            if self.logger_service:
                await self.logger_service.log_conversation(message, full_text, client_ip)
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            yield f"data: {json.dumps({'text': f'Error: {str(e)}', 'done': True})}\n\n"