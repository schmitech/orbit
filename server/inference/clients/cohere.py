"""
Cohere client implementation for LLM inference.

This module provides a Cohere-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import logging
import os

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class CohereClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Cohere."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        # Initialize base classes properly
        BaseLLMClient.__init__(self, config, retriever, reranker_service, prompt_service, no_results_message)
        LLMClientCommon.__init__(self)  # Initialize the common client
        
        # Get Cohere specific configuration
        cohere_config = config.get('inference', {}).get('cohere', {})
        
        self.api_key = os.getenv("COHERE_API_KEY", cohere_config.get('api_key', ''))
        if not self.api_key:
            raise ValueError("Cohere API key is required. Set COHERE_API_KEY environment variable or provide in config.")
        
        # If the API key contains a variable reference like ${COHERE_API_KEY}, try to resolve it
        if isinstance(self.api_key, str) and self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]  # Remove ${ and }
            self.api_key = os.environ.get(env_var)
            if not self.api_key:
                raise ValueError(f"Environment variable {env_var} is not set")
        
        self.api_base = cohere_config.get('api_base', 'https://api.cohere.ai/v1')
        self.model = cohere_config.get('model', 'command-r-plus')
        self.temperature = cohere_config.get('temperature', 0.1)
        self.top_p = cohere_config.get('top_p', 0.8)
        self.max_tokens = cohere_config.get('max_tokens', 1024)
        self.stream = cohere_config.get('stream', True)
        self.verbose = cohere_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.cohere_client = None
        self.logger = logging.getLogger(self.__class__.__name__)
        
    async def initialize(self) -> None:
        """Initialize the Cohere client."""
        try:
            import cohere
            
            # Initialize the Cohere client
            self.cohere_client = cohere.ClientV2(api_key=self.api_key)
            
            self.logger.info(f"Initialized Cohere client with model {self.model}")
        except ImportError:
            self.logger.error("cohere package not installed. Please install with: pip install cohere")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Cohere client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            # The Cohere client doesn't need explicit cleanup
            self.cohere_client = None
            self.logger.info("Closed Cohere client session")
        except Exception as e:
            self.logger.error(f"Error closing Cohere client: {str(e)}")
        
        # Signal that cleanup is complete
        self.logger.info("Cohere client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Cohere is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.cohere_client:
                await self.initialize()
                
            # Check if API key is provided
            if not self.api_key:
                self.logger.error("No Cohere API key provided. Please set COHERE_API_KEY environment variable or configure it in the config file.")
                return False
                
            # Log masked version of the API key for debugging
            if len(self.api_key) >= 4:
                self.logger.info(f"Using Cohere API key ending with: {self.api_key[-4:]}")
            
            # Simple test request to verify connection
            response = self.cohere_client.chat(
                model=self.model,
                messages=[{"role": "user", "content": "Hello, are you there?"}],
                max_tokens=10
            )
            
            # If we get here, the connection is working
            self.logger.info("Successfully connected to Cohere API")
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Cohere API: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Cohere.
        
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
            
            # Initialize Cohere client if not already initialized
            if not self.cohere_client:
                await self.initialize()
            
            # Call the Cohere API
            start_time = time.time()
            
            if self.verbose:
                self.logger.info(f"Calling Cohere API with model: {self.model}")
            
            # Prepare messages for the API call
            messages = []
            
            # Add system message if provided (Cohere v2 API uses system messages)
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message with context
            user_content = f"Context information:\n{context}\n\nUser Query: {message}"
            messages.append({"role": "user", "content": user_content})
            
            # Prepare parameters for Cohere
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "p": self.top_p,  # Cohere uses 'p' instead of 'top_p'
                "max_tokens": self.max_tokens
            }
            
            response = self.cohere_client.chat(**params)
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text
            response_text = response.message.content[0].text
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Get token usage from the response
            tokens = {
                "prompt": getattr(response.usage, 'input_tokens', 0) if hasattr(response, 'usage') else 0,
                "completion": getattr(response.usage, 'output_tokens', 0) if hasattr(response, 'usage') else 0,
                "total": getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
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
        Generate a streaming response for a chat message using Cohere.
        
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
            
            # Initialize Cohere client if not already initialized
            if not self.cohere_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Cohere API with model: {self.model}")
            
            # Prepare messages for the API call
            messages = []
            
            # Add system message if provided (Cohere v2 API uses system messages)
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message with context
            user_content = f"Context information:\n{context}\n\nUser Query: {message}"
            messages.append({"role": "user", "content": user_content})
            
            # Prepare parameters for Cohere streaming
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "p": self.top_p,  # Cohere uses 'p' instead of 'top_p'
                "max_tokens": self.max_tokens
            }
            
            # Generate streaming response
            response_stream = self.cohere_client.chat_stream(**params)
            
            # Process the streaming response
            chunk_count = 0
            try:
                for event in response_stream:
                    if event.type == "content-delta":
                        chunk_text = event.delta.message.content.text
                        chunk_count += 1
                        
                        if self.verbose and chunk_count % 10 == 0:
                            self.logger.debug(f"Streaming chunk {chunk_count}")
                            
                        yield json.dumps({
                            "response": chunk_text,
                            "sources": [],
                            "done": False
                        })
                
                if self.verbose:
                    self.logger.info(f"Streaming complete. Sent {chunk_count} chunks")
                
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
