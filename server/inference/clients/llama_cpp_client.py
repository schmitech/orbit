"""
llama.cpp client implementation for LLM inference.

This module provides a llama.cpp-specific implementation of the BaseLLMClient interface.
"""

import json
import time
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
import logging

from ..base_llm_client import BaseLLMClient

class QALlamaCppClient(BaseLLMClient):
    """LLM client implementation for llama.cpp."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get LlamaCpp specific configuration
        llama_cpp_config = config.get('inference', {}).get('llama_cpp', {})
        
        self.model_path = llama_cpp_config.get('model_path', '')
        self.temperature = llama_cpp_config.get('temperature', 0.1)
        self.top_p = llama_cpp_config.get('top_p', 0.8)
        self.top_k = llama_cpp_config.get('top_k', 20)
        self.max_tokens = llama_cpp_config.get('max_tokens', 1024)
        self.n_ctx = llama_cpp_config.get('n_ctx', 8192)
        self.n_threads = llama_cpp_config.get('n_threads', 8)
        
        self.llama_model = None
        
    async def initialize(self) -> None:
        """Initialize the LlamaCpp client."""
        try:
            from llama_cpp import Llama
            
            self.llama_model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads
            )
            
            self.logger.info(f"Initialized llama.cpp client with model at {self.model_path}")
        except ImportError:
            self.logger.error("llama_cpp package not installed. Please install with: pip install llama-cpp-python")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing llama.cpp client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        # llama.cpp model doesn't need explicit cleanup
        pass
    
    async def verify_connection(self) -> bool:
        """
        Verify that the llama.cpp model is loaded properly.
        
        Returns:
            True if model is loaded, False otherwise
        """
        return self.llama_model is not None
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using llama.cpp.
        
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
            
            # Call the llama.cpp model
            start_time = time.time()
            
            # We need to convert the async call to sync using ThreadPoolExecutor
            loop = asyncio.get_event_loop()
            
            def generate():
                return self.llama_model(
                    prompt=prompt,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    echo=False
                )
            
            response = await loop.run_in_executor(None, generate)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Extract the response and metadata
            response_text = response.get("choices", [{}])[0].get("text", "")
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": response.get("usage", {}).get("completion_tokens", 0),
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
        Generate a streaming response for a chat message using llama.cpp.
        
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
            
            # Use a thread to run the CPU-bound llama.cpp inference
            loop = asyncio.get_event_loop()
            
            def stream_generate():
                return self.llama_model(
                    prompt=prompt,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    echo=False,
                    stream=True
                )
            
            # Start streaming in a separate thread
            stream = await loop.run_in_executor(None, stream_generate)
            
            # Stream response chunks
            buffer = ""
            for chunk in stream:
                if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                    text = chunk["choices"][0].get("text", "")
                    if text:
                        buffer += text
                        yield json.dumps({
                            "response": text,
                            "sources": [],
                            "done": False
                        })
            
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