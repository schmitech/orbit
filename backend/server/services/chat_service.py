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
    
    def __init__(self, config: Dict[str, Any], llm_client, logger_service):
        self.config = config
        self.llm_client = llm_client
        self.logger_service = logger_service
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
    
    async def _log_conversation(self, query: str, response: str, client_ip: str):
        """Log conversation asynchronously without delaying the main response."""
        try:
            await self.logger_service.log_conversation(
                query=query,
                response=response,
                ip=client_ip,
                backend=self.config.get('ollama', {}).get('model', 'ollama'),
                blocked=False
            )
        except Exception as e:
            logger.error(f"Error logging conversation: {str(e)}", exc_info=True)
    
    async def process_chat(self, message: str, voice_enabled: bool, client_ip: str) -> Dict[str, Any]:
        """Process a chat message and return a response"""
        try:
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            
            # Generate response using a list for more efficient concatenation
            chunks = []
            async for chunk in self.llm_client.generate_response(message, stream=False):
                chunks.append(chunk)
            response_text = "".join(chunks)
            
            # Apply text fixes
            response_text = fix_text_formatting(response_text)
            
            # Log conversation concurrently without delaying response
            asyncio.create_task(self._log_conversation(message, response_text, client_ip))
            
            if self.verbose:
                end_time = loop.time()
                logger.info(f"Chat processed in {end_time - start_time:.3f}s")
            
            # Return response
            return {
                "response": response_text,
                "audio": None  # Placeholder for future audio handling
            }
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    async def process_chat_stream(self, message: str, voice_enabled: bool, client_ip: str):
        """Process a chat message and stream the response"""
        try:
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            
            # List to accumulate full response for logging
            chunks = []
            first_token_received = False
            
            stream_enabled = _is_true_value(self.config['ollama'].get('stream', True))
            
            async for chunk in self.llm_client.generate_response(message, stream=stream_enabled):
                if not first_token_received:
                    first_token_received = True
                    first_token_time = loop.time()
                    if self.verbose:
                        logger.info(f"Time to first token: {first_token_time - start_time:.3f}s")
                
                chunks.append(chunk)
                current_text = "".join(chunks)
                fixed_text = fix_text_formatting(current_text)
                yield f"data: {json.dumps({'text': fixed_text, 'done': False})}\n\n"
            
            # Send final done message
            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
            
            if self.verbose:
                end_time = loop.time()
                logger.info(f"Stream completed in {end_time - start_time:.3f}s")
            
            # Log conversation concurrently
            full_text = "".join(chunks)
            asyncio.create_task(self._log_conversation(message, full_text, client_ip))
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'text': f'Error: {str(e)}', 'done': True})}\n\n"
