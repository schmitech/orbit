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

class QAVLLMClient(BaseLLMClient):
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
        
        self.logger.info(f"Initialized vLLM client with model {self.model}")
    
    async def initialize(self) -> None:
        """Initialize the vLLM client."""
        # No special initialization needed for vLLM REST API
        pass
    
    async def close(self) -> None:
        """Clean up resources."""
        # vLLM client doesn't need explicit cleanup
        pass
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to vLLM is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            # Try to get a health status from vLLM
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
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
            
            # Prepare the prompt with context
            prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
            
            # Call the vLLM API
            start_time = time.time()
            
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
                    
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Extract the response and metadata
            choices = data.get("choices", [])
            response_text = choices[0].get("text", "") if choices else ""
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": data.get("usage", {}).get("completion_tokens", 0),
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
            
            # Prepare the prompt with context
            prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
            
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
                                buffer += text
                                yield json.dumps({
                                    "response": text,
                                    "sources": [],
                                    "done": False
                                })
                            
                            if finished:
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