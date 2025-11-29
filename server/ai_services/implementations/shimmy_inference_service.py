"""
Shimmy inference service implementation using unified architecture.

Shimmy is a 100% OpenAI-compatible inference server for GGUF models.
It only supports API mode (no direct model loading).

Compare with: server/ai_services/implementations/llama_cpp_inference_service.py
"""

import logging
from typing import Dict, Any, AsyncGenerator
from ..base import ServiceType
from ..services import InferenceService
from ..providers.shimmy_base import ShimmyBaseService

logger = logging.getLogger(__name__)


class ShimmyInferenceService(InferenceService, ShimmyBaseService):
    """
    Shimmy inference service using unified architecture.
    
    Shimmy provides a 100% OpenAI-compatible API for local GGUF model serving.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Shimmy inference service."""
        # Cooperative initialization - call both base classes explicitly
        ShimmyBaseService.__init__(self, config, ServiceType.INFERENCE, "shimmy")
        InferenceService.__init__(self, config, "shimmy")
        
        # Get configuration
        provider_config = self._extract_provider_config()
        
        # Stop tokens (optional)
        self.stop_tokens = provider_config.get("stop_tokens", [])
        
        # Get inference-specific configuration from provider config
        self.temperature = provider_config.get("temperature", 0.7)
        self.max_tokens = provider_config.get("max_tokens", 1024)
        self.top_p = provider_config.get("top_p", 0.95)

    async def initialize(self) -> bool:
        """Initialize the Shimmy service."""
        if self.initialized:
            return True
        
        try:
            # Initialize via base service
            result = await super().initialize()
            if result:
                logger.info(f"Shimmy inference service initialized at {self.base_url}")
            return result
        except Exception as e:
            logger.error(f"Failed to initialize Shimmy inference service: {str(e)}")
            return False

    def _build_messages(self, prompt: str, messages: list = None) -> list:
        """Build messages in the format expected by OpenAI-compatible API."""
        if messages:
            return messages
        return [{"role": "user", "content": prompt}]

    def _clean_response_text(self, text: str) -> str:
        """Clean up response text by removing special tokens."""
        if not text:
            return text
        
        # Clean up stop tokens if any
        if self.stop_tokens:
            for token in self.stop_tokens:
                text = text.replace(token, "")
        
        return text.strip()

    def _build_request_params(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Build the request parameters for the OpenAI-compatible API."""
        messages = kwargs.pop('messages', None)
        messages = self._build_messages(prompt, messages)

        # Build parameters for OpenAI-compatible API
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        # Add optional parameters
        if self.stop_tokens:
            params["stop"] = self.stop_tokens

        # Add any other kwargs passed in
        params.update(kwargs)

        return params

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Shimmy (API mode only)."""
        if not self.initialized:
            await self.initialize()

        try:
            # This method is for non-streaming generation, so ensure stream is disabled.
            kwargs.pop("stream", None)
            params = self._build_request_params(prompt, **kwargs)
            # Explicitly set stream to False for non-streaming requests
            params["stream"] = False
            
            # Use OpenAI-compatible client
            response = await self.client.chat.completions.create(**params)

            # Validate response type
            if isinstance(response, str):
                # Shimmy sometimes returns SSE format even with stream=False
                # Try to parse it as SSE and extract the final content
                logger.debug("Shimmy returned string response, attempting to parse as SSE format")
                return self._parse_sse_response(response)
            
            # Check if response has expected structure
            if not hasattr(response, 'choices') or not response.choices:
                logger.error(f"Shimmy response missing choices: {response}")
                raise ValueError(f"Invalid response structure from Shimmy: {response}")

            # Extract and clean response text
            response_text = response.choices[0].message.content
            if not response_text:
                logger.warning("Shimmy returned empty response content")
                return ""
            
            return self._clean_response_text(response_text)

        except Exception as e:
            self._handle_shimmy_error(e, "text generation")
            raise

    def _parse_sse_response(self, sse_text: str) -> str:
        """
        Parse Server-Sent Events (SSE) format response from Shimmy.
        
        Sometimes Shimmy returns SSE format even when stream=False.
        This method extracts the content from SSE chunks.
        
        Args:
            sse_text: The SSE-formatted response string
            
        Returns:
            Concatenated content from all chunks
        """
        import json
        import re
        
        content_parts = []
        
        # Split by lines and process each data line
        for line in sse_text.split('\n'):
            line = line.strip()
            if not line or line == 'data: [DONE]':
                continue
            
            # Extract JSON from "data: {...}" format
            if line.startswith('data: '):
                json_str = line[6:]  # Remove "data: " prefix
                try:
                    chunk = json.loads(json_str)
                    if chunk.get('choices') and len(chunk['choices']) > 0:
                        delta = chunk['choices'][0].get('delta', {})
                        content = delta.get('content')
                        if content:
                            content_parts.append(content)
                except json.JSONDecodeError:
                    logger.debug(f"Failed to parse SSE chunk: {json_str}")
                    continue
        
        result = ''.join(content_parts)
        return self._clean_response_text(result) if result else ""

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Shimmy (API mode only)."""
        if not self.initialized:
            await self.initialize()

        try:
            params = self._build_request_params(prompt, **kwargs)
            params["stream"] = True
            
            # Use OpenAI-compatible streaming client
            stream = await self.client.chat.completions.create(**params)

            # Process stream chunks
            async for chunk in stream:
                if chunk and chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    if choice.delta and choice.delta.content:
                        text = choice.delta.content
                        if text:
                            # Clean up the text
                            text = self._clean_response_text(text)
                            if text:
                                yield text

        except Exception as e:
            self._handle_shimmy_error(e, "streaming generation")
            yield f"Error: {str(e)}"

