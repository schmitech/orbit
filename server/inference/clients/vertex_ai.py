"""
Google Vertex AI client implementation for LLM inference.

This module provides a Google Vertex AI-specific implementation of the BaseLLMClient interface.
"""

import json
import time
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
import logging
import os

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class VertexAIClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Google Vertex AI (Google AI Platform/Studio)."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get Vertex AI specific configuration
        vertex_config = config.get('inference', {}).get('vertex', {})
        
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", vertex_config.get('project_id', ''))
        self.location = vertex_config.get('location', 'us-central1')
        self.model = vertex_config.get('model', 'gemini-1.5-pro')
        self.temperature = vertex_config.get('temperature', 0.1)
        self.top_p = vertex_config.get('top_p', 0.8)
        self.top_k = vertex_config.get('top_k', 20)
        self.max_tokens = vertex_config.get('max_tokens', 1024)
        self.stream = vertex_config.get('stream', True)
        self.verbose = vertex_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        # Google Cloud Authentication
        self.credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", 
                                          vertex_config.get('credentials_path', ''))
        
        self.vertex_client = None
        self.model_client = None
        self.generation_config = None
        
    async def initialize(self) -> None:
        """Initialize the Vertex AI client."""
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, GenerationConfig
            
            # Set the credentials path if provided
            if self.credentials_path:
                if self.verbose:
                    self.logger.info(f"Using credentials from: {self.credentials_path}")
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path
                
            # Initialize Vertex AI
            vertexai.init(project=self.project_id, location=self.location)
            
            # Create generation config
            self.generation_config = GenerationConfig(
                temperature=self.temperature,
                top_p=self.top_p,
                top_k=self.top_k,
                max_output_tokens=self.max_tokens,
            )
            
            # Create model client
            self.model_client = GenerativeModel(self.model)
            self.vertex_client = vertexai
            
            self.logger.info(f"Initialized Vertex AI client with model {self.model}")
        except ImportError:
            self.logger.error("vertexai package not installed. Please install with: pip install google-cloud-aiplatform")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Vertex AI client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        # No specific cleanup needed for Vertex AI
        self.logger.info("Vertex AI client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Vertex AI is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.model_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Testing Vertex AI connection")
                
            # Simple test request to verify connection
            response = await asyncio.to_thread(
                self.model_client.generate_content,
                "Hello, are you there?",
                generation_config=self.generation_config
            )
            
            if self.verbose:
                self.logger.info("Successfully connected to Vertex AI")
                
            # If we get here, the connection is working
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Vertex AI: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Vertex AI.
        
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
            
            # Initialize Vertex AI client if not already initialized
            if not self.model_client:
                await self.initialize()
                
            # Prepare the chat session
            from vertexai.generative_models import ChatSession
            chat = ChatSession(model=self.model_client)
            
            if self.verbose:
                self.logger.info(f"Creating chat session with system prompt")
                
            # Add system prompt as the first message
            await asyncio.to_thread(
                chat.send_message,
                system_prompt,
                generation_config=self.generation_config
            )
            
            # Call the Vertex AI API
            start_time = time.time()
            
            # Prepare the user message with context
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            if self.verbose:
                self.logger.info(f"Sending message to Vertex AI")
                
            # Send the message to the chat session
            response = await asyncio.to_thread(
                chat.send_message,
                user_message,
                generation_config=self.generation_config
            )
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text
            response_text = response.text
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Estimate token count using helper method
            estimated_tokens = self._estimate_tokens(system_prompt + user_message, response_text)
            
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
        Generate a streaming response for a chat message using Vertex AI.
        
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
            
            # Initialize Vertex AI client if not already initialized
            if not self.model_client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Creating chat session for streaming response")
                
            # Create a chat session
            from vertexai.generative_models import ChatSession
            chat = ChatSession(model=self.model_client)
            
            # Add system prompt as the first message
            await asyncio.to_thread(
                chat.send_message,
                system_prompt,
                generation_config=self.generation_config
            )
            
            # Prepare the user message with context
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            if self.verbose:
                self.logger.info(f"Simulating streaming with Vertex AI (chunked response)")
                
            # Generate streaming response - note that Vertex AI doesn't have true streaming
            # in the same way as OpenAI, so we'll use the non-streaming API and simulate streaming
            response = await asyncio.to_thread(
                chat.send_message,
                user_message,
                generation_config=self.generation_config
            )
            
            # Get the full response text
            full_response = response.text
            
            # Simulate streaming by chunking the response
            # Split into sentences or reasonable chunks
            import re
            chunks = re.split(r'(?<=[.!?])\s+', full_response)
            
            # Stream each chunk
            chunk_count = 0
            for chunk in chunks:
                if chunk.strip():
                    chunk_count += 1
                    
                    if self.verbose and chunk_count % 5 == 0:
                        self.logger.debug(f"Streaming chunk {chunk_count} of {len(chunks)}")
                        
                    yield json.dumps({
                        "response": chunk + " ",
                        "sources": [],
                        "done": False
                    })
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.05)
            
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
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True}) 