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

from ..base_llm_client import BaseLLMClient

class MistralClient(BaseLLMClient):
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
        
        self.mistral_client = None
        
    async def initialize(self) -> None:
        """Initialize the Mistral AI client."""
        try:
            from openai import AsyncOpenAI
            
            # Initialize Mistral client using OpenAI client with custom base URL
            self.mistral_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
            
            self.logger.info(f"Initialized Mistral AI client with model {self.model}")
        except ImportError:
            self.logger.error("openai package not installed or outdated. Please install with: pip install -U openai>=1.0.0")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Mistral AI client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            if self.mistral_client and hasattr(self.mistral_client, "close"):
                await self.mistral_client.close()
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
            if not self.mistral_client:
                await self.initialize()
            
            # Simple test request to verify connection
            response = await self.mistral_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Ping"}
                ],
                max_tokens=10
            )
            
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
            # Check if the message is safe
            if self.guardrail_service and not await self.guardrail_service.is_safe(message):
                return {
                    "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
                    "sources": [],
                    "tokens": 0,
                    "processing_time": 0
                }
            
            # Query for relevant documents
            retrieved_docs = await self.retriever.get_relevant_context(
                query=message,
                collection_name=collection_name
            )
            
            # Rerank if reranker is available
            if self.reranker_service and retrieved_docs:
                retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
            # Get the system prompt
            system_prompt = "You are a helpful assistant that provides accurate information."
            if system_prompt_id and self.prompt_service:
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc and 'prompt' in prompt_doc:
                    system_prompt = prompt_doc['prompt']
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Initialize Mistral client if not already initialized
            if not self.mistral_client:
                await self.initialize()
            
            # Call the Mistral AI API
            start_time = time.time()
            
            # Prepare messages for the API call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context information:\n{context}\n\nUser Query: {message}"}
            ]
            
            response = await self.mistral_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
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
            # Check if the message is safe
            if self.guardrail_service and not await self.guardrail_service.is_safe(message):
                yield json.dumps({
                    "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
                    "sources": [],
                    "done": True
                })
                return
            
            # Query for relevant documents
            retrieved_docs = await self.retriever.get_relevant_context(
                query=message,
                collection_name=collection_name
            )
            
            # Rerank if reranker is available
            if self.reranker_service and retrieved_docs:
                retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
            # Get the system prompt
            system_prompt = "You are a helpful assistant that provides accurate information."
            if system_prompt_id and self.prompt_service:
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc and 'prompt' in prompt_doc:
                    system_prompt = prompt_doc['prompt']
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Initialize Mistral client if not already initialized
            if not self.mistral_client:
                await self.initialize()
            
            # Prepare messages for the API call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context information:\n{context}\n\nUser Query: {message}"}
            ]
            
            # Generate streaming response
            response_stream = await self.mistral_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stream=True
            )
            
            # Stream the response
            async for chunk in response_stream:
                if chunk.choices[0].delta.content is not None:
                    yield json.dumps({
                        "response": chunk.choices[0].delta.content,
                        "done": False
                    })
            
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