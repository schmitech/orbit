"""
vLLM client implementation for LLM inference.

This module provides a vLLM-specific implementation of the BaseLLMClient interface.
"""

import json
import time
import re
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging
import socket
import urllib.parse

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class QAVLLMClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for vLLM."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        # Initialize base classes properly
        BaseLLMClient.__init__(self, config, retriever, reranker_service, prompt_service, no_results_message)
        LLMClientCommon.__init__(self)  # Initialize the common client
        
        # Get vLLM specific configuration
        vllm_config = config.get('inference', {}).get('vllm', {})
        
        self.host = vllm_config.get('host', 'localhost')
        self.port = vllm_config.get('port', 8000)
        self.base_url = f"http://{self.host}:{self.port}"
        self.model = vllm_config.get('model', 'Qwen/Qwen2.5-1.5B-Instruct')
        self.temperature = vllm_config.get('temperature', 0.1)
        self.top_p = vllm_config.get('top_p', 0.8)
        self.top_k = vllm_config.get('top_k', 20)
        self.max_tokens = vllm_config.get('max_tokens', 1024)
        self.stream = vllm_config.get('stream', True)
        self.verbose = vllm_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        # Response quality control parameters
        self.max_response_length = vllm_config.get('max_response_length', 2000)
        self.repetition_threshold = vllm_config.get('repetition_threshold', 3)
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"Initialized vLLM client with base URL {self.base_url}")
    
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
        # Log detailed connection information
        self.logger.info(f"Attempting to connect to vLLM at: {self.base_url}")
        
        try:
            # First try a simple TCP socket connection to check basic connectivity
            # Parse the URL to get host and port
            parsed_url = urllib.parse.urlparse(self.base_url)
            host = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            
            self.logger.info(f"Testing TCP connection to {host}:{port}")
            
            # Create a socket connection with a short timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            try:
                sock.connect((host, port))
                self.logger.info(f"TCP connection successful to {host}:{port}")
                sock.close()
            except Exception as sock_err:
                self.logger.error(f"TCP connection failed: {str(sock_err)}")
                return False
            finally:
                sock.close()
            
            # If TCP connection works, try the API endpoints
            async with aiohttp.ClientSession() as session:
                # Try the chat endpoint first (OpenAI API format)
                try:
                    self.logger.info(f"Testing API connection to {self.base_url}/v1/chat/completions")
                    
                    async with session.post(
                        f"{self.base_url}/v1/chat/completions",
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": "Hello"}],
                            "max_tokens": 1
                        },
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        status = response.status
                        self.logger.info(f"Chat completions endpoint returned status: {status}")
                        
                        if status == 200:
                            self.logger.info("Successfully connected to vLLM server")
                            return True
                        else:
                            error_text = await response.text()
                            self.logger.error(f"Failed response from chat endpoint: {error_text}")
                            return False
                except Exception as e:
                    self.logger.error(f"Error testing chat endpoint: {str(e)}")
                    return False
                
        except Exception as e:
            self.logger.error(f"Connection verification failed: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        adapter_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using vLLM.
        
        Args:
            message: The user's message
            adapter_name: Name of the adapter to use for context retrieval
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            if self.verbose:
                self.logger.info(f"Generating response for message: {message[:100]}...")
                
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, adapter_name)
            
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
            
            # Prepare messages for the API call
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add system message if provided
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Add the current message with context
            messages.append({"role": "user", "content": f"Context information:\n{context}\n\nUser Query: {message}"})
            
            if self.verbose:
                self.logger.info(f"Calling vLLM API for inference")
                
            # Call the vLLM API
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "max_tokens": self.max_tokens,
                        "stream": False,
                        "stop": ["</answer>", "<|im_end|>"]  # Add stop sequences to prevent runaway generation
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
            response_text = choices[0].get("message", {}).get("content", "") if choices else ""
            
            # Apply quality checks to non-streaming responses too
            if len(response_text) > self.max_response_length:
                self.logger.warning(f"Response exceeded max length ({self.max_response_length} chars)")
                response_text = response_text[:self.max_response_length] + "... [Response truncated due to length]"
                
            if self._check_for_repetition(response_text):
                self.logger.warning("Detected excessive repetition in response")
                # Find a good breaking point
                sentences = response_text.split('.')
                trimmed_response = '.'.join(sentences[:min(10, len(sentences))]) + "... [Response truncated due to repetition]"
                response_text = trimmed_response
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            usage = data.get("usage", {})
            if self.verbose and usage:
                self.logger.info(f"Token usage: {usage}")
            
            # Clean the response
            cleaned_response = self._clean_response(response_text)
            
            # Wrap response with security checking
            response_dict = {
                "response": cleaned_response,
                "sources": sources,
                "tokens": usage.get("completion_tokens", 0),
                "processing_time": processing_time
            }
            
            return await self._secure_response(response_dict)
        except Exception as e:
            self.logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
    
    def _check_for_repetition(self, text: str) -> bool:
        """
        Check if the response text contains too much repetition.
        
        Args:
            text: The text to check for repetition
            
        Returns:
            True if excessive repetition detected, False otherwise
        """
        if len(text) < 100:
            return False
            
        # Check for repeating paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if len(paragraphs) > self.repetition_threshold:
            repeated_paragraphs = set()
            for p in paragraphs:
                if len(p) > 20:  # Only check substantial paragraphs
                    if p in repeated_paragraphs:
                        if self.verbose:
                            self.logger.warning(f"Detected repeated paragraph: {p[:50]}...")
                        return True
                    repeated_paragraphs.add(p)
        
        # Check for repeating sentences
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        if len(sentences) > self.repetition_threshold * 2:
            sentence_count = {}
            for s in sentences:
                if len(s) > 10:  # Only check substantial sentences
                    sentence_count[s] = sentence_count.get(s, 0) + 1
                    if sentence_count[s] > self.repetition_threshold:
                        if self.verbose:
                            self.logger.warning(f"Detected repeated sentence: {s[:50]}...")
                        return True
        
        return False

    async def generate_response_stream(
        self, 
        message: str, 
        adapter_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        # Wrap the entire streaming response with security checking
        async for chunk in self._secure_response_stream(
            self._generate_response_stream_internal(message, adapter_name, system_prompt_id, context_messages)
        ):
            yield chunk
    
    async def _generate_response_stream_internal(
        self, 
        message: str, 
        adapter_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message using vLLM.
        
        Args:
            message: The user's message
            adapter_name: Name of the adapter to use for context retrieval
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            if self.verbose:
                self.logger.info(f"Starting streaming response for message: {message[:100]}...")
                            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, adapter_name)
            
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
            
            # Prepare messages for the API call
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add system message if provided
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Add the current message with context
            messages.append({"role": "user", "content": f"Context information:\n{context}\n\nUser Query: {message}"})
            
            if self.verbose:
                self.logger.info(f"Calling vLLM API with streaming enabled")
                
            # Call the vLLM API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "max_tokens": self.max_tokens,
                        "stream": True,
                        "stop": ["</answer>", "<|im_end|>"]  # Add stop sequences to prevent runaway generation
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
                    total_tokens = 0
                    total_chars = 0
                    last_check_length = 0
                    
                    async for line in response.content:
                        chunk = line.decode('utf-8').strip()
                        if not chunk:
                            continue
                        
                        if chunk == "data: [DONE]":
                            # When stream is complete, send the sources
                            sources = self._format_sources(retrieved_docs)
                            yield json.dumps({
                                "response": "",
                                "sources": sources,
                                "done": True
                            })
                            break
                        
                        if chunk.startswith("data: "):
                            chunk = chunk[6:]  # Remove "data: " prefix
                        
                        try:
                            data = json.loads(chunk)
                            # Add defensive checks for data
                            if not data:
                                self.logger.warning(f"Received empty data in chunk: {chunk}")
                                continue
                                
                            choices = data.get("choices", [])
                            # Make sure we have at least one choice
                            choice = choices[0] if choices else {}
                            text = choice.get("delta", {}).get("content", "")
                            finished = choice.get("finish_reason") is not None
                            
                            # Check token usage with proper null handling
                            usage = data.get("usage")
                            if usage is not None:
                                total_tokens = usage.get("completion_tokens", 0)
                            
                                if total_tokens >= self.max_tokens:
                                    if self.verbose:
                                        self.logger.warning(f"Reached max_tokens limit ({self.max_tokens})")
                                    finished = True
                            
                            if text:
                                chunk_count += 1
                                buffer += text
                                total_chars += len(text)
                                
                                # Check for response length limits
                                if total_chars > self.max_response_length:
                                    self.logger.warning(f"Response exceeded max length ({self.max_response_length} chars)")
                                    buffer += "... [Response truncated due to length]"
                                    finished = True
                                
                                # Periodically check for repetition in the full response
                                if total_chars - last_check_length > 500:
                                    last_check_length = total_chars
                                    if self._check_for_repetition(buffer):
                                        self.logger.warning("Detected excessive repetition in response")
                                        buffer += "... [Response truncated due to repetition]"
                                        finished = True
                                
                                if self.verbose and chunk_count % 10 == 0:
                                    self.logger.debug(f"Received chunk {chunk_count}, tokens: {total_tokens}, chars: {total_chars}")
                                
                                yield json.dumps({
                                    "response": text,
                                    "sources": [],
                                    "done": False
                                })
                            
                            if finished:
                                if self.verbose:
                                    self.logger.info(f"Streaming complete. Received {chunk_count} chunks, total tokens: {total_tokens}")
                                    
                                # When stream is complete, send the sources
                                sources = self._format_sources(retrieved_docs)
                                yield json.dumps({
                                    "response": "",
                                    "sources": sources,
                                    "done": True
                                })
                                break
                        except json.JSONDecodeError:
                            self.logger.error(f"Error parsing JSON: {chunk}")
                            continue
        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True})

    def _clean_response(self, text: str) -> str:
        """
        Clean the response text by removing unwanted artifacts and patterns.
        
        Args:
            text: Raw response from the model
            
        Returns:
            Cleaned response text
        """
        # Remove parenthetical notes about context
        text = re.sub(r'\([^)]*context[^)]*\)', '', text)
        
        # Remove other meta-commentary in parentheses
        text = re.sub(r'\([^)]*I am [^)]*\)', '', text)
        text = re.sub(r'\([^)]*I cannot [^)]*\)', '', text)
        text = re.sub(r'\([^)]*would be [^)]*\)', '', text)
        
        # Remove citation markers at the end of sentences or paragraphs
        text = re.sub(r'\s*\[\d+\](?:\s*\.)?', '.', text)  # Replace [N] or [N]. with .
        text = re.sub(r'\s*\[\d+\]\s*$', '', text)  # Remove [N] at the end of text
        text = re.sub(r'\s*\[\d+\]\s*\n', '\n', text)  # Remove [N] at the end of lines
        
        # Clean up extra whitespace and newlines created by removals
        text = re.sub(r'\n{3,}', '\n\n', text)  # Replace 3+ newlines with 2
        text = re.sub(r' {2,}', ' ', text)      # Replace 2+ spaces with 1
        text = re.sub(r'\n +', '\n', text)      # Remove spaces at start of lines
        
        return text.strip() 