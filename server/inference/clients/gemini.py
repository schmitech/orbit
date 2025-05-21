"""
Google Gemini client implementation for LLM inference.

This module provides a Google Gemini-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging
import os

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class GeminiClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Google Gemini."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get Gemini specific configuration
        gemini_config = config.get('inference', {}).get('gemini', {})
        
        self.api_key = os.getenv("GOOGLE_API_KEY", gemini_config.get('api_key', ''))
        self.model = gemini_config.get('model', 'gemini-2.0-flash')
        self.temperature = gemini_config.get('temperature', 0.1)
        self.top_p = gemini_config.get('top_p', 0.8)
        self.top_k = gemini_config.get('top_k', 20)
        self.max_tokens = gemini_config.get('max_tokens', 1024)
        self.stream = gemini_config.get('stream', True)
        self.verbose = config.get('general', {}).get('verbose', False)
        
        self.gemini_client = None
        
    async def initialize(self) -> None:
        """Initialize the Gemini client."""
        try:
            import google.generativeai as genai
            
            # Initialize Gemini client
            genai.configure(api_key=self.api_key)
            self.gemini_client = genai
            
            if self.verbose:
                self.logger.info(f"Initialized Gemini client with model {self.model}")
                self.logger.debug(f"Gemini configuration: temperature={self.temperature}, top_p={self.top_p}, top_k={self.top_k}, max_tokens={self.max_tokens}")
        except ImportError:
            self.logger.error("google-generativeai package not installed. Please install with: pip install google-generativeai")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Gemini client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.verbose:
            self.logger.info("Closing Gemini client")
        # No specific cleanup needed for Gemini
        self.logger.info("Gemini client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Gemini is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.gemini_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Testing Gemini API connection")
            
            # Simple test request to verify connection
            model = self.gemini_client.GenerativeModel(self.model)
            response = model.generate_content("Ping")
            
            if self.verbose:
                self.logger.info("Successfully connected to Gemini API")
                self.logger.debug(f"Test response: {response.text}")
            
            # If we get here, the connection is working
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Gemini API: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Gemini.
        
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
            
            # Prepare the prompt with context
            prompt = await self._prepare_prompt_with_context(message, system_prompt, context)
            
            # Initialize Gemini client if not already initialized
            if not self.gemini_client:
                await self.initialize()
            
            # Call the Gemini API
            start_time = time.time()
            
            if self.verbose:
                self.logger.info(f"Calling Gemini API with model: {self.model}")
            
            model = self.gemini_client.GenerativeModel(
                model_name=self.model,
                generation_config={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "max_output_tokens": self.max_tokens,
                }
            )
            
            response = model.generate_content(prompt)
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Estimate token count
            estimated_tokens = self._estimate_tokens(prompt, response_text)
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": estimated_tokens,
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
        Generate a streaming response for a chat message using Gemini.
        
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
            
            # Prepare the prompt with context
            prompt = await self._prepare_prompt_with_context(message, system_prompt, context)
            
            # Initialize Gemini client if not already initialized
            if not self.gemini_client:
                await self.initialize()
            
            # Create a Gemini model with streaming configuration
            if self.verbose:
                self.logger.info(f"Initializing streaming with model: {self.model}")
            
            model = self.gemini_client.GenerativeModel(
                model_name=self.model,
                generation_config={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "max_output_tokens": self.max_tokens,
                }
            )
            
            # Generate streaming response
            if self.verbose:
                self.logger.info("Starting streaming response")
            
            response_stream = model.generate_content(prompt, stream=True)
            
            # Process the streaming response
            try:
                chunk_count = 0
                for chunk in response_stream:
                    if hasattr(chunk, 'text'):
                        chunk_text = chunk.text
                    else:
                        chunk_text = str(chunk)
                    
                    if chunk_text:
                        chunk_count += 1
                        if self.verbose:
                            self.logger.debug(f"Received chunk {chunk_count}: {chunk_text[:50]}...")
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