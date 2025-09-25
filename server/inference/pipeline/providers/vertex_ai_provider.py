"""
Google Vertex AI Provider for Pipeline Architecture

This module provides a clean Google Vertex AI implementation for the pipeline architecture.
"""

import re
import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class VertexAIProvider(LLMProvider):
    """
    Clean Google Vertex AI implementation for the pipeline architecture.
    
    This provider communicates directly with Google Vertex AI using the official SDK
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Vertex AI provider.
        
        Args:
            config: Configuration dictionary containing Vertex AI settings
        """
        self.config = config
        vertex_config = config.get("inference", {}).get("vertex", {})
        
        self.project_id = vertex_config.get("project_id")
        self.location = vertex_config.get("location", "us-central1")
        self.model = vertex_config.get("model", "gemini-1.5-pro")
        self.temperature = vertex_config.get("temperature", 0.1)
        self.top_p = vertex_config.get("top_p", 0.8)
        self.top_k = vertex_config.get("top_k", 20)
        self.max_tokens = vertex_config.get("max_tokens", 1024)
        self.credentials_path = vertex_config.get("credentials_path")
        
        self.vertex_client = None
        self.model_client = None
        self.generation_config = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Vertex AI provider."""
        try:
            import os
            import vertexai
            from vertexai.generative_models import GenerativeModel, GenerationConfig
            
            if not self.project_id:
                raise ValueError("Vertex AI project_id is required")
            
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
            
            self.logger.info(f"Initialized Vertex AI provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("google-cloud-aiplatform package not installed. Please install with: pip install google-cloud-aiplatform")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Vertex AI client: {str(e)}")
            raise
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimation: ~4 characters per token
        return len(text) // 4
    
    def _build_messages(self, prompt: str, messages: list = None) -> list:
        """
        Builds messages for Vertex AI.

        Args:
            prompt: The input prompt string (used as a fallback).
            messages: An optional list of message dictionaries.

        Returns:
            A list of message dictionaries.
        """
        if messages:
            return messages

        # Parse the raw prompt string
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                # Prepend system prompt to user message content
                return [{"role": "user", "content": f"{system_part}\n\n{user_part}"}]
        
        return [{"role": "user", "content": prompt}]
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Vertex AI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.model_client:
            await self.initialize()
        
        try:
            from vertexai.generative_models import Content, Part

            # Build messages
            messages_from_kwarg = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages_from_kwarg)

            # Convert to Vertex AI Content objects
            contents = []
            for msg in messages:
                role = msg.get("role", "user")
                # Gemini uses 'model' for assistant role
                if role == "assistant":
                    role = "model"
                contents.append(Content(role=role, parts=[Part.from_text(msg.get("content", ""))]))

            if self.verbose:
                self.logger.debug(f"Generating with Vertex AI: model={self.model}, temperature={self.temperature}")
            
            # Create generation config with any overrides
            generation_config = self.generation_config
            if kwargs:
                from vertexai.generative_models import GenerationConfig
                generation_config = GenerationConfig(
                    temperature=kwargs.get("temperature", self.temperature),
                    top_p=kwargs.get("top_p", self.top_p),
                    top_k=kwargs.get("top_k", self.top_k),
                    max_output_tokens=kwargs.get("max_tokens", self.max_tokens),
                )
            
            # Generate response in a thread to avoid blocking
            def _generate():
                return self.model_client.generate_content(
                    contents,
                    generation_config=generation_config
                )
            
            response = await asyncio.to_thread(_generate)
            
            # Extract response text
            response_text = response.text
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error generating response with Vertex AI: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Vertex AI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.model_client:
            await self.initialize()
        
        try:
            from vertexai.generative_models import Content, Part

            # Build messages
            messages_from_kwarg = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages_from_kwarg)

            # Convert to Vertex AI Content objects
            contents = []
            for msg in messages:
                role = msg.get("role", "user")
                if role == "assistant":
                    role = "model"
                contents.append(Content(role=role, parts=[Part.from_text(msg.get("content", ""))]))

            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Vertex AI")
            
            # Create generation config with any overrides
            generation_config = self.generation_config
            if kwargs:
                from vertexai.generative_models import GenerationConfig
                generation_config = GenerationConfig(
                    temperature=kwargs.get("temperature", self.temperature),
                    top_p=kwargs.get("top_p", self.top_p),
                    top_k=kwargs.get("top_k", self.top_k),
                    max_output_tokens=kwargs.get("max_tokens", self.max_tokens),
                )
            
            # Generate response with real streaming
            def _generate_stream():
                return self.model_client.generate_content(
                    contents,
                    generation_config=generation_config,
                    stream=True
                )

            stream = await asyncio.to_thread(_generate_stream)

            for chunk in stream:
                yield chunk.text
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Vertex AI: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Vertex AI provider."""
        # Vertex AI client doesn't require explicit cleanup
        self.vertex_client = None
        self.model_client = None
        self.generation_config = None
        self.logger.info("Vertex AI provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Vertex AI configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.project_id:
                self.logger.error("Vertex AI project_id is missing")
                return False
            
            if not self.model:
                self.logger.error("Vertex AI model is missing")
                return False
            
            # Test connection with a simple request
            if not self.model_client:
                await self.initialize()
            
            # Validate with a minimal test
            def _test():
                return self.model_client.generate_content(
                    "test",
                    generation_config=self.generation_config
                )
            
            response = await asyncio.to_thread(_test)
            
            if self.verbose:
                self.logger.info("Vertex AI configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("google-cloud-aiplatform package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Vertex AI configuration validation failed: {str(e)}")
            return False