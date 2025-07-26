"""
Google Gemini Provider for Pipeline Architecture

This module provides a clean Google Gemini implementation for the pipeline architecture.
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class GeminiProvider(LLMProvider):
    """
    Clean Google Gemini implementation for the pipeline architecture.
    
    This provider communicates directly with Google's Gemini API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Gemini provider.
        
        Args:
            config: Configuration dictionary containing Gemini settings
        """
        self.config = config
        gemini_config = config.get("inference", {}).get("gemini", {})
        
        self.api_key = gemini_config.get("api_key")
        self.model = gemini_config.get("model", "gemini-2.0-flash")
        self.temperature = gemini_config.get("temperature", 0.1)
        self.top_p = gemini_config.get("top_p", 0.8)
        self.top_k = gemini_config.get("top_k", 20)
        self.max_tokens = gemini_config.get("max_tokens", 1024)
        self.stream = gemini_config.get("stream", True)
        
        self.genai = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Gemini client."""
        try:
            import google.generativeai as genai
            
            if not self.api_key:
                raise ValueError("Google API key is required for Gemini")
            
            genai.configure(api_key=self.api_key)
            self.genai = genai
            
            self.logger.info(f"Initialized Gemini provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("google-generativeai package not installed. Please install with: pip install google-generativeai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini client: {str(e)}")
            raise
    
    def _prepare_messages(self, prompt: str) -> list:
        """
        Prepare messages in the format expected by Gemini.
        
        Args:
            prompt: The input prompt
            
        Returns:
            List of message parts formatted for Gemini
        """
        # Extract system prompt and user message if present
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                # For Gemini, system prompts are often included as part of the user message
                combined_prompt = f"{system_part}\n\n{user_part}"
                return [{"text": combined_prompt}]
        
        # If no clear separation, use the entire prompt
        return [{"text": prompt}]
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Google Gemini.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.genai:
            await self.initialize()
        
        try:
            # Create the model with generation config
            model = self.genai.GenerativeModel(
                model_name=self.model,
                generation_config={
                    "temperature": kwargs.get("temperature", self.temperature),
                    "top_p": kwargs.get("top_p", self.top_p),
                    "top_k": kwargs.get("top_k", self.top_k),
                    "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
                }
            )
            
            # Prepare the content
            content = self._prepare_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Sending request to Gemini: model={self.model}, temperature={self.temperature}")
            
            # Generate content synchronously (Gemini SDK doesn't have async support yet)
            response = await asyncio.to_thread(model.generate_content, content)
            
            if hasattr(response, 'text') and response.text:
                return response.text
            else:
                # Handle cases where text might be in different attributes
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            return candidate.content.parts[0].text
                
                self.logger.error(f"Unexpected Gemini response format: {response}")
                raise ValueError("Could not extract text from Gemini response")
            
        except Exception as e:
            self.logger.error(f"Error generating response with Gemini: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Google Gemini.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.genai:
            await self.initialize()
        
        try:
            # Create the model with generation config
            model = self.genai.GenerativeModel(
                model_name=self.model,
                generation_config={
                    "temperature": kwargs.get("temperature", self.temperature),
                    "top_p": kwargs.get("top_p", self.top_p),
                    "top_k": kwargs.get("top_k", self.top_k),
                    "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
                }
            )
            
            # Prepare the content
            content = self._prepare_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming request to Gemini: model={self.model}")
            
            # Generate streaming content
            def _generate_stream():
                return model.generate_content(content, stream=True)
            
            response_stream = await asyncio.to_thread(_generate_stream)
            
            # Process chunks in a thread to avoid blocking
            def _process_chunks():
                chunks = []
                try:
                    for chunk in response_stream:
                        if hasattr(chunk, 'text') and chunk.text:
                            chunks.append(chunk.text)
                        elif hasattr(chunk, 'candidates') and chunk.candidates:
                            candidate = chunk.candidates[0]
                            if hasattr(candidate, 'content') and candidate.content:
                                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                                    for part in candidate.content.parts:
                                        if hasattr(part, 'text') and part.text:
                                            chunks.append(part.text)
                except Exception as e:
                    chunks.append(f"Error: {str(e)}")
                return chunks
            
            chunks = await asyncio.to_thread(_process_chunks)
            
            # Yield all chunks
            for chunk in chunks:
                yield chunk
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Gemini: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Gemini client."""
        # No specific cleanup needed for Gemini
        self.genai = None
        self.logger.info("Gemini provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Gemini configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Google API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Gemini model is missing")
                return False
            
            # Test connection with a simple request
            if not self.genai:
                await self.initialize()
            
            # Validate with a minimal test
            model = self.genai.GenerativeModel(self.model)
            
            # Test generation in a thread
            def _test_generate():
                return model.generate_content([{"text": "test"}])
            
            response = await asyncio.to_thread(_test_generate)
            
            if self.verbose:
                self.logger.info("Gemini configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("google-generativeai package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Gemini configuration validation failed: {str(e)}")
            return False