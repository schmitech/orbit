"""
Anthropic client implementation for LLM inference.

This module provides an Anthropic-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging
import os

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class AnthropicClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Anthropic."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        # Initialize base classes properly
        BaseLLMClient.__init__(self, config, retriever, reranker_service, prompt_service, no_results_message)
        LLMClientCommon.__init__(self)  # Initialize the common client
        
        # Get Anthropic specific configuration
        anthropic_config = config.get('inference', {}).get('anthropic', {})
        
        self.api_key = os.getenv("ANTHROPIC_API_KEY", anthropic_config.get('api_key', ''))
        self.api_base = anthropic_config.get('api_base', 'https://api.anthropic.com/v1')
        self.model = anthropic_config.get('model', 'claude-3-opus-20240229')
        self.temperature = anthropic_config.get('temperature', 0.1)
        self.top_p = anthropic_config.get('top_p', 0.8)
        self.max_tokens = anthropic_config.get('max_tokens', 1024)
        self.stream = anthropic_config.get('stream', True)
        self.verbose = anthropic_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.anthropic_client = None
        self.logger = logging.getLogger(self.__class__.__name__)
        
    async def initialize(self) -> None:
        """Initialize the Anthropic client."""
        try:
            from anthropic import AsyncAnthropic
            
            # Initialize Anthropic client
            self.anthropic_client = AsyncAnthropic(api_key=self.api_key)
            
            self.logger.info(f"Initialized Anthropic client with model {self.model}")
        except ImportError:
            self.logger.error("anthropic package not installed or outdated. Please install with: pip install anthropic>=0.50.0")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Anthropic client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            if self.anthropic_client and hasattr(self.anthropic_client, "close"):
                await self.anthropic_client.close()
                self.logger.info("Closed Anthropic client session")
        except Exception as e:
            self.logger.error(f"Error closing Anthropic client: {str(e)}")
        
        # Signal that cleanup is complete
        self.logger.info("Anthropic client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Anthropic is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.anthropic_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Testing Anthropic API connection")
                
            # Simple test request to verify connection
            response = await self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Ping"}
                ]
            )
            
            if self.verbose:
                self.logger.info("Successfully connected to Anthropic API")
                
            # If we get here, the connection is working
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Anthropic API: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Anthropic.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            if self.verbose:
                self.logger.info(f"Generating response for message: {message[:100]}...")
                
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
            
            # Initialize Anthropic client if not already initialized
            if not self.anthropic_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Anthropic API with model: {self.model}")
                
            # Call the Anthropic API
            start_time = time.time()
            
            # For Claude, we use a structured user message with the context and query
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            # Prepare messages for the API call using the recommended format
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message
            messages.append({"role": "user", "content": user_message})
            
            try:
                response = await self.anthropic_client.messages.create(
                    model=self.model,
                    messages=messages,
                    system=system_prompt,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens
                )
            except Exception as api_error:
                self.logger.error(f"Anthropic API error: {str(api_error)}")
                if self.verbose:
                    self.logger.debug(f"Request: model={self.model}, system={system_prompt[:50]}..., messages={messages}")
                raise
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text
            if not hasattr(response, 'content') or not response.content:
                self.logger.error("Unexpected response format from Anthropic API: missing content")
                if self.verbose:
                    self.logger.debug(f"Response: {response}")
                return {"error": "Failed to get valid response from Anthropic API"}
                
            response_text = response.content[0].text
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Get token usage from the response
            tokens = {
                "prompt": response.usage.input_tokens,
                "completion": response.usage.output_tokens,
                "total": response.usage.input_tokens + response.usage.output_tokens
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
        Generate a streaming response for a chat message using Anthropic.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            if self.verbose:
                self.logger.info(f"Starting streaming response for message: {message[:100]}...")
                
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
            
            # Initialize Anthropic client if not already initialized
            if not self.anthropic_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Anthropic API with streaming enabled")
                
            # For Claude, we use a structured user message with the context and query
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            # Prepare messages for the API call using the recommended format
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message
            messages.append({"role": "user", "content": user_message})
            
            chunk_count = 0
            # Generate streaming response
            try:
                async with self.anthropic_client.messages.stream(
                    model=self.model,
                    messages=messages,
                    system=system_prompt,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens
                ) as stream:
                    async for chunk in stream:
                        if chunk.type == "content_block_delta":
                            chunk_count += 1
                            
                            if self.verbose and chunk_count % 10 == 0:
                                self.logger.debug(f"Received chunk {chunk_count}")
                                
                            yield json.dumps({
                                "response": chunk.delta.text,
                                "done": False
                            })
            except Exception as stream_error:
                self.logger.error(f"Anthropic streaming error: {str(stream_error)}")
                if self.verbose:
                    self.logger.debug(f"Stream request: model={self.model}, system={system_prompt[:50]}..., messages={messages}")
                yield json.dumps({
                    "error": f"Error in streaming response: {str(stream_error)}",
                    "done": True
                })
                return
            
            if self.verbose:
                self.logger.info(f"Streaming complete. Received {chunk_count} chunks")
                
            # Send final message with sources
            yield json.dumps({
                "sources": self._format_sources(retrieved_docs),
                "done": True
            })
            
        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({
                "error": f"Failed to generate response: {str(e)}",
                "done": True
            }) 