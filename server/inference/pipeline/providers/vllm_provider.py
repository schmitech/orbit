"""
vLLM Provider for Pipeline Architecture

This module provides a clean vLLM implementation for the pipeline architecture.
"""

import json
import re
import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class VLLMProvider(LLMProvider):
    """
    Clean vLLM implementation for the pipeline architecture.
    
    This provider communicates directly with vLLM's OpenAI-compatible REST API
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the vLLM provider.
        
        Args:
            config: Configuration dictionary containing vLLM settings
        """
        self.config = config
        vllm_config = config.get("inference", {}).get("vllm", {})
        
        self.host = vllm_config.get("host", "localhost")
        self.port = vllm_config.get("port", 8000)
        self.base_url = f"http://{self.host}:{self.port}"
        self.model = vllm_config.get("model", "Qwen/Qwen2.5-1.5B-Instruct")
        self.temperature = vllm_config.get("temperature", 0.1)
        self.top_p = vllm_config.get("top_p", 0.8)
        self.top_k = vllm_config.get("top_k", 20)
        self.max_tokens = vllm_config.get("max_tokens", 1024)
        self.stream = vllm_config.get("stream", True)
        
        # Response quality control parameters
        self.max_response_length = vllm_config.get("max_response_length", 2000)
        self.repetition_threshold = vllm_config.get("repetition_threshold", 3)
        self.stop_sequences = vllm_config.get("stop_sequences", ["</answer>", "<|im_end|>"])
        
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the vLLM provider."""
        try:
            # Test connection to vLLM server
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 1
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ConnectionError(f"Failed to connect to vLLM server: {error_text}")
            
            self.logger.info(f"Initialized vLLM provider at {self.base_url} with model: {self.model}")
            
        except ImportError:
            self.logger.error("aiohttp package not installed. Please install with: pip install aiohttp")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize vLLM client: {str(e)}")
            raise
    
    def _clean_response_text(self, text: str) -> str:
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
                        return True
        
        return False
    
    def _build_messages(self, prompt: str) -> list:
        """
        Build messages in the format expected by vLLM.
        
        Args:
            prompt: The input prompt
            
        Returns:
            List of message dictionaries
        """
        # Extract system prompt and user message if present
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                messages = []
                if system_part:
                    messages.append({"role": "system", "content": system_part})
                messages.append({"role": "user", "content": user_part})
                return messages
        
        # If no clear separation, treat entire prompt as user message
        return [{"role": "user", "content": prompt}]
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using vLLM.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        try:
            import aiohttp
            
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Generating with vLLM: model={self.model}, temperature={self.temperature}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": kwargs.get("temperature", self.temperature),
                        "top_p": kwargs.get("top_p", self.top_p),
                        "top_k": kwargs.get("top_k", self.top_k),
                        "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                        "stream": False,
                        "stop": self.stop_sequences,
                        **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "top_k", "max_tokens"]}
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"vLLM API error: {error_text}")
                    
                    data = await response.json()
            
            # Extract response text
            choices = data.get("choices", [])
            response_text = choices[0].get("message", {}).get("content", "") if choices else ""
            
            # Apply quality checks
            if len(response_text) > self.max_response_length:
                self.logger.warning(f"Response exceeded max length ({self.max_response_length} chars)")
                response_text = response_text[:self.max_response_length] + "... [Response truncated due to length]"
                
            if self._check_for_repetition(response_text):
                self.logger.warning("Detected excessive repetition in response")
                sentences = response_text.split('.')
                trimmed_response = '.'.join(sentences[:min(10, len(sentences))]) + "... [Response truncated due to repetition]"
                response_text = trimmed_response
            
            # Clean up the response
            response_text = self._clean_response_text(response_text)
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error generating response with vLLM: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using vLLM.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        try:
            import aiohttp
            
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with vLLM")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": kwargs.get("temperature", self.temperature),
                        "top_p": kwargs.get("top_p", self.top_p),
                        "top_k": kwargs.get("top_k", self.top_k),
                        "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                        "stream": True,
                        "stop": self.stop_sequences,
                        **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "top_k", "max_tokens", "stream"]}
                    },
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"vLLM API error: {error_text}")
                    
                    # Parse the streaming response
                    buffer = ""
                    total_chars = 0
                    last_check_length = 0
                    
                    async for line in response.content:
                        chunk = line.decode('utf-8').strip()
                        if not chunk:
                            continue
                        
                        if chunk == "data: [DONE]":
                            break
                        
                        if chunk.startswith("data: "):
                            chunk = chunk[6:]  # Remove "data: " prefix
                        
                        try:
                            data = json.loads(chunk)
                            if not data:
                                continue
                                
                            choices = data.get("choices", [])
                            choice = choices[0] if choices else {}
                            text = choice.get("delta", {}).get("content", "")
                            finished = choice.get("finish_reason") is not None
                            
                            # Check token usage
                            usage = data.get("usage")
                            if usage is not None:
                                total_tokens = usage.get("completion_tokens", 0)
                                if total_tokens >= self.max_tokens:
                                    finished = True
                            
                            if text:
                                buffer += text
                                total_chars += len(text)
                                
                                # Check for response length limits
                                if total_chars > self.max_response_length:
                                    self.logger.warning(f"Response exceeded max length ({self.max_response_length} chars)")
                                    yield "... [Response truncated due to length]"
                                    break
                                
                                # Periodically check for repetition
                                if total_chars - last_check_length > 500:
                                    last_check_length = total_chars
                                    if self._check_for_repetition(buffer):
                                        self.logger.warning("Detected excessive repetition in response")
                                        yield "... [Response truncated due to repetition]"
                                        break
                                
                                yield text
                            
                            if finished:
                                break
                                
                        except json.JSONDecodeError:
                            continue
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with vLLM: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the vLLM provider."""
        # vLLM provider doesn't need explicit cleanup
        self.logger.info("vLLM provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the vLLM configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            import aiohttp
            
            if not self.host or not self.port:
                self.logger.error("vLLM host and port are required")
                return False
            
            if not self.model:
                self.logger.error("vLLM model is required")
                return False
            
            # Test connection with a simple request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 1,
                        "temperature": 0
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"vLLM validation failed: {error_text}")
                        return False
            
            if self.verbose:
                self.logger.info("vLLM configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("aiohttp package not installed")
            return False
        except Exception as e:
            self.logger.error(f"vLLM configuration validation failed: {str(e)}")
            return False