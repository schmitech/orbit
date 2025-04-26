"""
vLLM client implementation for LLM inference.

This module provides a vLLM-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging

from ..base_llm_client import BaseLLMClient
from ..llm_client_mixin import LLMClientMixin

class QAVLLMClient(BaseLLMClient, LLMClientMixin):
    """LLM client implementation for vLLM."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get vLLM specific configuration
        vllm_config = config.get('inference', {}).get('vllm', {})
        
        self.host = vllm_config.get('host', 'localhost')
        self.port = vllm_config.get('port', 8000)
        self.base_url = f"http://{self.host}:{self.port}"
        self.model = vllm_config.get('model', 'llama3:8b')
        self.temperature = vllm_config.get('temperature', 0.1)
        self.top_p = vllm_config.get('top_p', 0.8)
        self.top_k = vllm_config.get('top_k', 20)
        self.max_tokens = vllm_config.get('max_tokens', 1024)
        self.stream = vllm_config.get('stream', True)
        self.verbose = vllm_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.logger.info(f"Initialized vLLM client with model {self.model}")
    
    async def initialize(self) -> None:
        """Initialize the vLLM client."""
        # No special initialization needed for vLLM REST API
        if self.verbose:
            self.logger.info(f"vLLM client using REST API at {self.base_url}")
    
    async def close(self) -> None:
        """Clean up resources."""
        # vLLM client doesn't need explicit cleanup
        if self.verbose:
            self.logger.info("vLLM client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to vLLM is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if self.verbose:
                self.logger.info(f"Checking connection to vLLM server at {self.base_url}")
                
            # Try to get a health status from vLLM
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        if self.verbose:
                            self.logger.info("Successfully connected to vLLM server")
                        return True
                    else:
                        self.logger.error(f"Failed to connect to vLLM: {response.status}")
                        return False
        except Exception as e:
            self.logger.error(f"Error connecting to vLLM: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using vLLM.
        
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
            if not await self._check_message_safety(message):
                return await self._handle_unsafe_message()
            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Prepare the prompt with context
            prompt = await self._prepare_prompt_with_context(message, system_prompt, context)
            
            # Call the vLLM API
            start_time = time.time()
            
            if self.verbose:
                self.logger.info(f"Calling vLLM API for inference")
                
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/completions",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "max_tokens": self.max_tokens,
                        "stream": False
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"vLLM error: {error_text}")
                        return {"error": f"Failed to generate response: {error_text}"}
                    
                    data = await response.json()
                    
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response and metadata
            choices = data.get("choices", [])
            response_text = choices[0].get("text", "") if choices else ""
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            usage = data.get("usage", {})
            if self.verbose and usage:
                self.logger.info(f"Token usage: {usage}")
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": usage.get("completion_tokens", 0),
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
        Generate a streaming response for a chat message using vLLM.
        
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
            if not await self._check_message_safety(message):
                yield await self._handle_unsafe_message_stream()
                return
            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Prepare the prompt with context
            prompt = await self._prepare_prompt_with_context(message, system_prompt, context)
            
            if self.verbose:
                self.logger.info(f"Calling vLLM API with streaming enabled")
                
            # Call the vLLM API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/completions",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "max_tokens": self.max_tokens,
                        "stream": True
                    },
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"vLLM error: {error_text}")
                        yield json.dumps({"error": f"Failed to generate response: {error_text}", "done": True})
                        return
                    
                    # Parse the streaming response
                    buffer = ""
                    chunk_count = 0
                    async for line in response.content:
                        chunk = line.decode('utf-8').strip()
                        if not chunk or chunk == "data: [DONE]":
                            continue
                        
                        if chunk.startswith("data: "):
                            chunk = chunk[6:]  # Remove "data: " prefix
                        
                        try:
                            data = json.loads(chunk)
                            choice = data.get("choices", [{}])[0]
                            text = choice.get("text", "")
                            finished = choice.get("finish_reason") is not None
                            
                            if text:
                                chunk_count += 1
                                buffer += text
                                
                                if self.verbose and chunk_count % 10 == 0:
                                    self.logger.debug(f"Received chunk {chunk_count}")
                                
                                yield json.dumps({
                                    "response": text,
                                    "sources": [],
                                    "done": False
                                })
                            
                            if finished:
                                if self.verbose:
                                    self.logger.info(f"Streaming complete. Received {chunk_count} chunks")
                                    
                                # When stream is complete, send the sources
                                sources = self._format_sources(retrieved_docs)
                                yield json.dumps({
                                    "response": "",
                                    "sources": sources,
                                    "done": True
                                })
                        except json.JSONDecodeError:
                            self.logger.error(f"Error parsing JSON: {chunk}")
                            continue
        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True}) 