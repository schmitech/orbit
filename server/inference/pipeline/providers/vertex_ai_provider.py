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
    
    def _build_content(self, prompt: str) -> str:
        """
        Build content for Vertex AI generation.
        
        Args:
            prompt: The input prompt
            
        Returns:
            Formatted content string
        """
        # For Vertex AI, we can pass the prompt directly as content
        # The system prompt will be handled separately if needed
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                # Combine system and user parts
                if system_part:
                    return f"{system_part}\n\nUser: {user_part}"
                else:
                    return user_part
        
        # If no clear separation, return the entire prompt
        return prompt
    
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
            # Build content from prompt
            content = self._build_content(prompt)
            
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
                    content,
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
        
        Note: Vertex AI doesn't have true streaming like OpenAI, so we simulate
        streaming by chunking the response.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.model_client:
            await self.initialize()
        
        try:
            # Build content from prompt
            content = self._build_content(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Vertex AI (simulated)")
            
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
            
            # Generate response in a thread
            def _generate():
                return self.model_client.generate_content(
                    content,
                    generation_config=generation_config
                )
            
            response = await asyncio.to_thread(_generate)
            
            # Get the full response text
            full_response = response.text
            
            # Simulate streaming by chunking the response
            # Split into sentences or reasonable chunks
            chunks = re.split(r'(?<=[.!?])\s+', full_response)
            
            # Stream each chunk
            for chunk in chunks:
                if chunk.strip():
                    yield chunk + " "
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.05)
                    
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