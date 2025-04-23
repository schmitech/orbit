"""
Base Ollama Client - Abstract class for Ollama API interactions
==============================================================

This module provides a flexible, extensible base class for communicating with Ollama.
Specialized clients can extend this base class to implement domain-specific functionality
while sharing common Ollama interaction logic.
"""

import os
import json
import asyncio
import logging
import aiohttp
from typing import Dict, Any, Tuple, Optional, List, Generator
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseOllamaClient(ABC):
    """
    Abstract base class for Ollama API clients.
    
    This class handles the core Ollama interaction logic including:
    - Connection management
    - Request formatting
    - Response streaming
    - Configuration management
    
    Subclasses should implement domain-specific methods for:
    - Creating prompts
    - Processing retrieved context
    - Formatting responses
    """

    def __init__(
        self,
        config: Dict[str, Any]
    ):
        """
        Initialize the base Ollama client.
        
        Args:
            config: Configuration dictionary containing Ollama settings
        """
        self.config = config
        self.base_url = config["ollama"]["base_url"]
        self.model = config["ollama"]["model"]
        self.verbose = self._is_true_value(config.get("general", {}).get("verbose", False))
        
        # Ollama parameters with defaults
        ollama_config = config.get("ollama", {})
        self.temperature = ollama_config.get("temperature", 0.1)
        self.top_p = ollama_config.get("top_p", 0.8)
        self.top_k = ollama_config.get("top_k", 20)
        self.repeat_penalty = ollama_config.get("repeat_penalty", 1.1)
        self.num_predict = ollama_config.get("num_predict", 1024)
        self.num_ctx = ollama_config.get("num_ctx", 8192)
        self.num_threads = ollama_config.get("num_threads", 8)
        
        # Initialize session to None
        self.session: Optional[aiohttp.ClientSession] = None
    
    @staticmethod
    def _is_true_value(value: Any) -> bool:
        """
        Determine if a value should be considered as 'true'
        for configuration purposes.
        
        Args:
            value: The value to check
            
        Returns:
            True if the value should be considered 'true', False otherwise
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ["true", "yes", "1", "on", "enabled"]
        if isinstance(value, int):
            return value != 0
        return bool(value)
        
    async def initialize(self) -> None:
        """
        Initialize the aiohttp session with timeout and TCP connector settings.
        """
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config["ollama"].get("timeout", 30))
            connector = aiohttp.TCPConnector(limit=self.config["ollama"].get("connector_limit", 20))
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            
            if self.verbose:
                logger.info(f"Initialized aiohttp session with timeout {timeout.total}s")

    async def close(self) -> None:
        """
        Close the aiohttp session.
        """
        if self.session:
            await self.session.close()
            self.session = None
            if self.verbose:
                logger.info("Closed aiohttp session")

    async def verify_connection(self) -> bool:
        """
        Verify connection to the Ollama service.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self.initialize()
            async with self.session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            return False

    @abstractmethod
    async def create_prompt(self, query: str, context: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Create a prompt for Ollama based on the query and context.
        
        Args:
            query: The user's query
            context: Optional retrieved context
            
        Returns:
            Formatted prompt string
        """
        pass

    async def _call_ollama_api(self, prompt: str, stream: bool = True) -> Generator[str, None, None]:
        """
        Call the Ollama API with the given prompt.
        
        Args:
            prompt: The formatted prompt to send to Ollama
            stream: Whether to stream the response
            
        Yields:
            Response chunks if streaming, or the complete response
        """
        try:
            await self.initialize()
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "repeat_penalty": self.repeat_penalty,
                "num_predict": self.num_predict,
                "num_ctx": self.num_ctx,
                "num_threads": self.num_threads,
                "stream": stream,
            }

            if self.verbose:
                logger.info("=== Ollama API Call ===")
                logger.info(f"Model: {self.model}")
                logger.info(f"Temperature: {self.temperature}")
                logger.info(f"Stream: {stream}")
                logger.info("=====================")

            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {response.status} - {error_text}")
                    yield f"Error: Failed to get response from LLM (status code {response.status})"
                    return
                
                if stream:
                    last_chunk = ""
                    async for line in response.content:
                        line_text = line.decode("utf-8").strip()
                        if not line_text or not line_text.startswith("{"):
                            continue
                        try:
                            response_data = json.loads(line_text)
                        except json.JSONDecodeError:
                            continue
                        if response_data.get("response"):
                            chunk = response_data["response"]
                            # Smart spacing logic between chunks
                            if last_chunk and last_chunk[-1] in ".!?,:;" and chunk and chunk[0].isalnum():
                                chunk = " " + chunk
                            elif last_chunk and last_chunk[-1].islower() and chunk and chunk[0].isupper():
                                chunk = " " + chunk
                            last_chunk = chunk
                            yield chunk
                else:
                    response_data = await response.json()
                    response_text = response_data.get(
                        "response", "I'm sorry, I couldn't generate a response."
                    )
                    yield response_text
                    
        except aiohttp.ClientError as e:
            logger.error(f"Ollama API client error: {str(e)}")
            yield "I'm sorry, there was a connection error with the LLM service."
        except Exception as e:
            logger.error(f"Unexpected error in Ollama API call: {str(e)}")
            yield "I'm sorry, an unexpected error occurred while generating a response."

    @abstractmethod
    async def get_context(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for the given query.
        
        Args:
            query: The user's query
            **kwargs: Additional arguments for context retrieval
            
        Returns:
            List of context items
        """
        pass

    async def generate_response(self, query: str, stream: bool = True, **kwargs) -> Generator[str, None, None]:
        """
        Generate a response for the given query.
        
        Args:
            query: The user's query
            stream: Whether to stream the response
            **kwargs: Additional arguments for response generation
            
        Yields:
            Response chunks if streaming, or the complete response
        """
        try:
            # Get context for the query
            context = await self.get_context(query, **kwargs)
            
            # Create prompt with context
            prompt = await self.create_prompt(query, context)
            
            # Call Ollama API
            async for chunk in self._call_ollama_api(prompt, stream):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."