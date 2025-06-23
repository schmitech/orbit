"""
DeepSeek client implementation for LLM inference.

This module provides a DeepSeek-specific implementation of the BaseLLMClient interface.
"""

import json
import time
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging
import os

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class DeepSeekClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for DeepSeek."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        # Initialize base classes properly
        BaseLLMClient.__init__(self, config, retriever, reranker_service, prompt_service, no_results_message)
        LLMClientCommon.__init__(self)  # Initialize the common client
        
        # Get DeepSeek specific configuration
        deepseek_config = config.get('inference', {}).get('deepseek', {})
        
        self.api_key = os.getenv("DEEPSEEK_API_KEY", deepseek_config.get('api_key', ''))
        self.api_base = deepseek_config.get('api_base', 'https://api.deepseek.com/v1')
        self.model = deepseek_config.get('model', 'deepseek-chat')
        self.temperature = deepseek_config.get('temperature', 0.1)
        self.top_p = deepseek_config.get('top_p', 0.8)
        self.max_tokens = deepseek_config.get('max_tokens', 1024)
        self.stream = deepseek_config.get('stream', True)
        self.verbose = deepseek_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.deepseek_client = None
        self.logger = logging.getLogger(self.__class__.__name__)
        
    async def initialize(self) -> None:
        """Initialize the DeepSeek client."""
        try:
            from openai import AsyncOpenAI
            
            # DeepSeek API is compatible with OpenAI client
            self.deepseek_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
            
            self.logger.info(f"Initialized DeepSeek client with model {self.model}")
        except ImportError:
            self.logger.error("openai package not installed or outdated. Please install with: pip install -U openai>=1.0.0")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing DeepSeek client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            if self.deepseek_client and hasattr(self.deepseek_client, "close"):
                await self.deepseek_client.close()
                self.logger.info("Closed DeepSeek client session")
        except Exception as e:
            self.logger.error(f"Error closing DeepSeek client: {str(e)}")
        
        # Signal that cleanup is complete
        self.logger.info("DeepSeek client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to DeepSeek is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.deepseek_client:
                await self.initialize()
            
            # Simple test request to verify connection
            response = await self.deepseek_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello, are you there?"}
                ],
                max_tokens=10
            )
            
            # If we get here, the connection is working
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to DeepSeek API: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using DeepSeek.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Returns:
            Dictionary containing response and metadata
        """
        try: 
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # If no context was found, return the default no-results message
            if context is None:
                no_results_message = self.config.get('messages', {}).get('no_results_response', 
                    "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")
                return {
                    "response": no_results_message,
                    "sources": [],
                    "tokens": 0,
                    "processing_time": 0
                }
            
            # Initialize DeepSeek client if not already initialized
            if not self.deepseek_client:
                await self.initialize()
            
            # Call the DeepSeek API
            start_time = time.time()
            
            # Prepare messages for the API call
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message with context
            messages.append({
                "role": "user", 
                "content": f"Context information:\n{context}\n\nUser Query: {message}"
            })
            
            response = await self.deepseek_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens
            )
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text
            response_text = response.choices[0].message.content
            
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
            
            # Wrap response with security checking
            response_dict = {
                "response": response_text,
                "sources": sources,
                "tokens": tokens["total"],
                "token_usage": tokens,
                "processing_time": processing_time
            }
            
            return await self._secure_response(response_dict)
        except Exception as e:
            self.logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
    
    async def generate_response_stream(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        # Wrap the entire streaming response with security checking
        async for chunk in self._secure_response_stream(
            self._generate_response_stream_internal(message, collection_name, system_prompt_id, context_messages)
        ):
            yield chunk
    
    async def _generate_response_stream_internal(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message using DeepSeek.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Yields:
            Chunks of the response as they are generated
        """
        try:            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # If no context was found, return the default no-results message
            if context is None:
                no_results_message = self.config.get('messages', {}).get('no_results_response', 
                    "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")
                yield json.dumps({
                    "response": no_results_message,
                    "sources": [],
                    "done": True
                })
                return
            
            # Initialize DeepSeek client if not already initialized
            if not self.deepseek_client:
                await self.initialize()
            
            # Prepare messages for the API call
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message with context
            messages.append({
                "role": "user", 
                "content": f"Context information:\n{context}\n\nUser Query: {message}"
            })
            
            if self.verbose:
                self.logger.info(f"Calling DeepSeek API with streaming enabled")
            
            # Generate streaming response
            response_stream = await self.deepseek_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stream=True
            )
            
            # Process the streaming response
            try:
                chunk_count = 0
                async for chunk in response_stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        chunk_text = chunk.choices[0].delta.content
                        chunk_count += 1
                        
                        if self.verbose and chunk_count % 10 == 0:
                            self.logger.debug(f"Received chunk {chunk_count}")
                        
                        yield json.dumps({
                            "response": chunk_text,
                            "sources": [],
                            "done": False
                        })
                
                if self.verbose:
                    self.logger.info(f"Streaming complete. Received {chunk_count} chunks")
                
                # When stream is complete, send the sources
                sources = self._format_sources(retrieved_docs)
                yield json.dumps({
                    "response": "",
                    "sources": sources,
                    "done": True
                })
            except Exception as e:
                self.logger.error(f"Error in streaming response: {str(e)}")
                yield json.dumps({"error": f"Error in streaming response: {str(e)}", "done": True})
                
        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True}) 