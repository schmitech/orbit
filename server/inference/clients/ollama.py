"""
Ollama client implementation for LLM inference.

This module provides an Ollama-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class OllamaClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Ollama."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get Ollama specific configuration
        ollama_config = config.get('inference', {}).get('ollama', {})
        if not ollama_config:
            ollama_config = config.get('ollama', {})  # Backward compatibility
            
        self.base_url = ollama_config.get('base_url', 'http://localhost:11434')
        self.model = ollama_config.get('model', 'gemma3:1b')
        self.temperature = ollama_config.get('temperature', 0.1)
        self.top_p = ollama_config.get('top_p', 0.8)
        self.top_k = ollama_config.get('top_k', 20)
        self.repeat_penalty = ollama_config.get('repeat_penalty', 1.1)
        self.num_predict = ollama_config.get('num_predict', 1024)
        self.num_ctx = ollama_config.get('num_ctx', 8192)
        self.stream = ollama_config.get('stream', True)
        self.verbose = ollama_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.ollama_client = None
        
    async def initialize(self) -> None:
        """Initialize the Ollama client."""
        try:
            from langchain_ollama import OllamaLLM
            
            # Initialize Ollama client
            self.ollama_client = OllamaLLM(
                base_url=self.base_url,
                model=self.model,
                temperature=self.temperature,
                top_p=self.top_p,
                top_k=self.top_k,
                repeat_penalty=self.repeat_penalty,
                num_predict=self.num_predict,
                num_ctx=self.num_ctx
            )
            
            self.logger.info(f"Initialized Ollama client with model {self.model}")
        except ImportError:
            self.logger.error("langchain_ollama package not installed. Please install with: pip install langchain_ollama")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Ollama client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        # Close any open aiohttp sessions
        try:
            # This is a simple implementation - you may need to adapt this
            # based on how aiohttp sessions are managed in your codebase
            if hasattr(self, '_session') and self._session is not None:
                await self._session.close()
                self._session = None
                self.logger.info("Closed Ollama client session")
        except Exception as e:
            self.logger.error(f"Error closing Ollama client: {str(e)}")
        
        # Signal that cleanup is complete
        self.logger.info("Ollama client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Ollama is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            # Try to get a simple response from Ollama
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        return True
                    else:
                        self.logger.error(f"Failed to connect to Ollama: {response.status}")
                        return False
        except Exception as e:
            self.logger.error(f"Error connecting to Ollama: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Ollama.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
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
            
            # Prepare the prompt with context
            prompt = await self._prepare_prompt_with_context(message, system_prompt, context)
            
            # Call the Ollama API
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "repeat_penalty": self.repeat_penalty,
                        "num_predict": self.num_predict
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama error: {error_text}")
                        return {"error": f"Failed to generate response: {error_text}"}
                    
                    data = await response.json()
                    
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response and metadata
            response_text = data.get("response", "")
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": data.get("eval_count", 0),
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
        Generate a streaming response for a chat message using Ollama.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
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
            
            # Prepare the prompt with context
            prompt = await self._prepare_prompt_with_context(message, system_prompt, context)
            
            # Call the Ollama API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": True,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "repeat_penalty": self.repeat_penalty,
                        "num_predict": self.num_predict
                    },
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama error: {error_text}")
                        yield json.dumps({"error": f"Failed to generate response: {error_text}", "done": True})
                        return
                    
                    # Parse the streaming response
                    buffer = ""
                    async for line in response.content:
                        chunk = line.decode('utf-8').strip()
                        if not chunk:
                            continue
                        
                        try:
                            data = json.loads(chunk)
                            if "response" in data:
                                buffer += data["response"]
                                yield json.dumps({
                                    "response": data["response"],
                                    "sources": [],
                                    "done": False
                                })
                            
                            if data.get("done", False):
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