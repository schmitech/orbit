"""
Mistral AI client implementation for LLM inference.

This module provides a Mistral AI-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging
import os

# Import the official Mistral client
from mistralai import Mistral

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class MistralClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Mistral AI."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get Mistral specific configuration
        mistral_config = config.get('inference', {}).get('mistral', {})
        
        self.api_key = os.getenv("MISTRAL_API_KEY", mistral_config.get('api_key', ''))
        self.api_base = mistral_config.get('api_base', 'https://api.mistral.ai/v1')
        self.model = mistral_config.get('model', 'mistral-large')
        self.temperature = mistral_config.get('temperature', 0.1)
        self.top_p = mistral_config.get('top_p', 0.8)
        self.max_tokens = mistral_config.get('max_tokens', 1024)
        self.stream = mistral_config.get('stream', True)
        self.verbose = mistral_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.client = None
        
    async def initialize(self) -> None:
        """Initialize the Mistral AI client."""
        try:
            # Initialize Mistral client
            self.client = Mistral(api_key=self.api_key)
            
            self.logger.info(f"Initialized Mistral AI client with model {self.model}")
        except ImportError:
            self.logger.error("mistralai package not installed. Please install with: pip install -U mistralai")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Mistral AI client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            # Close client session
            if self.client:
                # Use context manager in the Mistral client
                self.client = None
            self.logger.info("Closed Mistral AI client session")
        except Exception as e:
            self.logger.error(f"Error closing Mistral AI client: {str(e)}")
        
        # Signal that cleanup is complete
        self.logger.info("Mistral AI client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Mistral AI is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Testing Mistral AI API connection")
                
            # Simple test request to verify connection
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant."
                    },
                    {
                        "role": "user", 
                        "content": "Ping"
                    }
                ],
                max_tokens=10
            )
            
            if self.verbose:
                self.logger.info("Successfully connected to Mistral AI API")
                
            # If we get here, the connection is working
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Mistral AI API: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Mistral AI.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            if self.verbose:
                self.logger.info(f"Generating response for message: {message[:100]}...")
                
            # Check if the message is safe
            is_safe, refusal_message = await self._check_message_safety(message)
            if not is_safe:
                return await self._handle_unsafe_message(refusal_message)
            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Initialize Mistral client if not already initialized
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Mistral AI API with model: {self.model}")
                
            # Call the Mistral AI API
            start_time = time.time()
            
            # Prepare messages for the API call
            messages = [
                {
                    "role": "system", 
                    "content": system_prompt
                },
                {
                    "role": "user", 
                    "content": f"Context information:\n{context}\n\nUser Query: {message}"
                }
            ]
            
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens
            )
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text
            response_text = response.choices[0].message.content
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Get token usage from the response
            tokens = {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens
            }
            
            if self.verbose:
                self.logger.info(f"Token usage: {tokens}")
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": tokens["total"],
                "token_usage": tokens,
                "processing_time": processing_time
            }
        except Exception as e:
            self.logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
    
    async def generate_response_stream(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message using Mistral AI.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            if self.verbose:
                self.logger.info(f"Starting streaming response for message: {message[:100]}...")
                
            # Check if the message is safe
            is_safe, refusal_message = await self._check_message_safety(message)
            if not is_safe:
                yield await self._handle_unsafe_message_stream(refusal_message)
                return
            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Initialize Mistral client if not already initialized
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Mistral AI API with streaming enabled")
                
            # Prepare messages for the API call
            messages = [
                {
                    "role": "system", 
                    "content": system_prompt
                },
                {
                    "role": "user", 
                    "content": f"Context information:\n{context}\n\nUser Query: {message}"
                }
            ]
            
            # Generate streaming response
            chunk_count = 0
            response_text = ""
            
            # Create a direct HTTP session for streaming
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "max_tokens": self.max_tokens,
                    "stream": True
                }
                
                async with session.post(f"{self.api_base}/chat/completions", 
                                       headers=headers, 
                                       json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        self.logger.error(f"Error from Mistral API: {error_text}")
                        yield json.dumps({
                            "error": f"API error: {error_text}",
                            "done": True
                        })
                        return
                    
                    # Process the stream
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        
                        # Skip empty lines or non-data lines
                        if not line or not line.startswith('data:'):
                            continue
                            
                        # Parse the data
                        try:
                            data = line[5:].strip()  # Remove 'data:' prefix
                            
                            # Skip "[DONE]" marker
                            if data == "[DONE]":
                                break
                                
                            chunk = json.loads(data)
                            
                            # Process delta content
                            if 'choices' in chunk and chunk['choices']:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                
                                if content:
                                    chunk_count += 1
                                    response_text += content
                                    
                                    if self.verbose and chunk_count % 10 == 0:
                                        self.logger.debug(f"Received chunk {chunk_count}")
                                    
                                    yield json.dumps({
                                        "response": content,
                                        "done": False
                                    })
                                
                                # Check for finish reason
                                finish_reason = chunk['choices'][0].get('finish_reason')
                                if finish_reason is not None:
                                    break
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Failed to parse JSON from stream: {line}")
                            continue
                        except Exception as e:
                            self.logger.error(f"Error processing stream chunk: {str(e)}")
                            continue
            
            if self.verbose:
                self.logger.info(f"Streaming complete. Received {chunk_count} chunks")
                
            # Send final message with sources
            yield json.dumps({
                "sources": self._format_sources(retrieved_docs),
                "done": True
            })
            
        except Exception as e:
            self.logger.error(f"Error in streaming response: {str(e)}")
            yield json.dumps({
                "error": f"Failed to generate streaming response: {str(e)}",
                "done": True
            }) 