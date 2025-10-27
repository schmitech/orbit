"""
Gemini inference service implementation using unified architecture.

This is a migrated version of the Gemini inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/gemini_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator
import asyncio

from ..base import ServiceType
from ..providers import GoogleBaseService
from ..services import InferenceService


class GeminiInferenceService(InferenceService, GoogleBaseService):
    """
    Gemini inference service using unified architecture.

    Old implementation: ~279 lines (gemini_provider.py)
    New implementation: ~80 lines
    Reduction: ~71%

    Gemini is Google's latest multimodal AI model with:
    - Advanced reasoning capabilities
    - Long context windows
    - Multimodal understanding (text, images, video, audio)
    - Native code generation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Gemini inference service."""
        # Initialize via GoogleBaseService first, which will call ProviderAIService
        # This ensures the model is properly extracted from config
        GoogleBaseService.__init__(self, config, ServiceType.INFERENCE, "gemini")

        # Get inference-specific configuration (these will override the defaults from InferenceService)
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)
        self.top_k = self._get_top_k(default=40)
        self.transport = config.get('transport', 'rest')  # Use REST to avoid gRPC/ALTS warnings

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            import google.generativeai as genai

            # Configure API
            api_key = kwargs.pop('api_key', None) or self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key, transport=self.transport)

            # Initialize model
            model = genai.GenerativeModel(self.model)

            generation_config = genai.GenerationConfig(
                temperature=kwargs.get('temperature', self.temperature),
                max_output_tokens=kwargs.get('max_tokens', self.max_tokens),
                top_p=kwargs.get('top_p', self.top_p),
                top_k=kwargs.get('top_k', self.top_k),
            )

            # REST transport uses synchronous methods, gRPC uses async
            if self.transport == 'rest':
                response = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=generation_config
                )
            else:
                response = await model.generate_content_async(
                    prompt,
                    generation_config=generation_config
                )

            # Handle different response scenarios
            if not response.candidates:
                raise ValueError("No candidates returned from Gemini")
            
            candidate = response.candidates[0]
            
            # Check finish reason
            if candidate.finish_reason == 2:  # SAFETY
                raise ValueError("Response blocked due to safety concerns")
            elif candidate.finish_reason == 3:  # RECITATION
                raise ValueError("Response blocked due to recitation concerns")
            elif candidate.finish_reason == 4:  # OTHER
                raise ValueError("Response blocked for other reasons")
            
            # Check if response has content
            if not candidate.content or not candidate.content.parts:
                raise ValueError("No content parts in response")
            
            # Extract text from the first part
            first_part = candidate.content.parts[0]
            if not hasattr(first_part, 'text') or not first_part.text:
                raise ValueError("No text content in response part")
            
            return first_part.text

        except Exception as e:
            self._handle_google_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            import google.generativeai as genai

            # Configure API
            api_key = kwargs.pop('api_key', None) or self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key, transport=self.transport)

            model = genai.GenerativeModel(self.model)

            generation_config = genai.GenerationConfig(
                temperature=kwargs.get('temperature', self.temperature),
                max_output_tokens=kwargs.get('max_tokens', self.max_tokens),
                top_p=kwargs.get('top_p', self.top_p),
                top_k=kwargs.get('top_k', self.top_k),
            )

            # REST transport uses synchronous methods, gRPC uses async
            if self.transport == 'rest':
                # Use synchronous streaming with REST
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    stream=True
                )
                for chunk in response:
                    # Check if chunk has valid content
                    if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                        part = chunk.candidates[0].content.parts[0]
                        if hasattr(part, 'text') and part.text:
                            yield part.text
                            # Allow other tasks to run
                            await asyncio.sleep(0)
            else:
                # Use async streaming with gRPC
                response = await model.generate_content_async(
                    prompt,
                    generation_config=generation_config,
                    stream=True
                )
                async for chunk in response:
                    # Check if chunk has valid content
                    if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                        part = chunk.candidates[0].content.parts[0]
                        if hasattr(part, 'text') and part.text:
                            yield part.text

        except Exception as e:
            self._handle_google_error(e, "streaming generation")
            yield f"Error: {str(e)}"
