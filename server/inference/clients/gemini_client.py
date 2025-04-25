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

class GeminiClient(BaseLLMClient):
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
            if self.guardrail_service and not await self.guardrail_service.is_safe(message):
                if self.verbose:
                    self.logger.warning("Message failed safety check")
                return {
                    "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
                    "sources": [],
                    "tokens": 0,
                    "processing_time": 0
                }
            
            # Query for relevant documents
            if self.verbose:
                self.logger.info(f"Retrieving context from collection: {collection_name}")
            retrieved_docs = await self.retriever.get_relevant_context(
                query=message,
                collection_name=collection_name
            )
            
            if self.verbose:
                self.logger.info(f"Retrieved {len(retrieved_docs)} relevant documents")
            
            # Rerank if reranker is available
            if self.reranker_service and retrieved_docs:
                if self.verbose:
                    self.logger.info("Reranking retrieved documents")
                retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
            # Get the system prompt
            system_prompt = "You are a helpful assistant that provides accurate information."
            if system_prompt_id and self.prompt_service:
                if self.verbose:
                    self.logger.info(f"Fetching system prompt with ID: {system_prompt_id}")
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc and 'prompt' in prompt_doc:
                    system_prompt = prompt_doc['prompt']
                    if self.verbose:
                        self.logger.debug(f"Using custom system prompt: {system_prompt[:100]}...")
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Prepare the prompt with context
            prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
            
            if self.verbose:
                self.logger.debug(f"Prepared prompt length: {len(prompt)} characters")
            
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
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            if self.verbose:
                self.logger.info(f"Received response in {processing_time:.2f} seconds")
            
            # Extract the response text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Estimate token count (Gemini doesn't provide this directly)
            # Rough estimate: 4 chars per token
            estimated_tokens = len(prompt) // 4 + len(response_text) // 4
            
            if self.verbose:
                self.logger.info(f"Estimated token usage: {estimated_tokens}")
            
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
            if self.guardrail_service and not await self.guardrail_service.is_safe(message):
                if self.verbose:
                    self.logger.warning("Message failed safety check")
                yield json.dumps({
                    "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
                    "sources": [],
                    "done": True
                })
                return
            
            # Query for relevant documents
            if self.verbose:
                self.logger.info(f"Retrieving context from collection: {collection_name}")
            retrieved_docs = await self.retriever.get_relevant_context(
                query=message,
                collection_name=collection_name
            )
            
            if self.verbose:
                self.logger.info(f"Retrieved {len(retrieved_docs)} relevant documents")
            
            # Rerank if reranker is available
            if self.reranker_service and retrieved_docs:
                if self.verbose:
                    self.logger.info("Reranking retrieved documents")
                retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
            # Get the system prompt
            system_prompt = "You are a helpful assistant that provides accurate information."
            if system_prompt_id and self.prompt_service:
                if self.verbose:
                    self.logger.info(f"Fetching system prompt with ID: {system_prompt_id}")
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc and 'prompt' in prompt_doc:
                    system_prompt = prompt_doc['prompt']
                    if self.verbose:
                        self.logger.debug(f"Using custom system prompt: {system_prompt[:100]}...")
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Prepare the prompt with context
            prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
            
            if self.verbose:
                self.logger.debug(f"Prepared prompt length: {len(prompt)} characters")
            
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