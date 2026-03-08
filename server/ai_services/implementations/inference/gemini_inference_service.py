"""
Gemini inference service implementation using unified architecture.

Uses the google-genai SDK (replacement for deprecated google-generativeai).
"""

from typing import Dict, Any, AsyncGenerator
import asyncio
import logging

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import InferenceService

logger = logging.getLogger(__name__)


class GeminiInferenceService(InferenceService, GoogleBaseService):
    """
    Gemini inference service using unified architecture.

    Gemini is Google's latest multimodal AI model with:
    - Advanced reasoning capabilities
    - Long context windows
    - Multimodal understanding (text, images, video, audio)
    - Native code generation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Gemini inference service."""
        GoogleBaseService.__init__(self, config, ServiceType.INFERENCE, "gemini")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)
        self.top_k = self._get_top_k(default=40)
        self.disable_safety = config.get('disable_safety', False)

        self._genai_client = None

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._genai_client is None:
            from google import genai
            import os

            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key

            self._genai_client = genai.Client()
        return self._genai_client

    def _build_config(self, **kwargs):
        """Build GenerateContentConfig from parameters."""
        from google.genai import types

        config_params = {
            "temperature": kwargs.get('temperature', self.temperature),
            "max_output_tokens": kwargs.get('max_tokens', self.max_tokens),
            "top_p": kwargs.get('top_p', self.top_p),
            "top_k": kwargs.get('top_k', self.top_k),
        }

        if self.disable_safety:
            config_params["safety_settings"] = [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ]

        return types.GenerateContentConfig(**config_params)

    def _extract_text(self, response) -> str:
        """Extract text from a Gemini response, with error checking."""
        if not response.candidates:
            raise ValueError("No candidates returned from Gemini")

        candidate = response.candidates[0]

        # Check finish reason
        finish_reason = getattr(candidate, 'finish_reason', None)
        if finish_reason == 2:  # SAFETY
            raise ValueError("Response blocked due to safety concerns")
        elif finish_reason == 3:  # RECITATION
            raise ValueError("Response blocked due to recitation concerns")
        elif finish_reason == 4:  # OTHER
            raise ValueError("Response blocked for other reasons")

        if not candidate.content or not candidate.content.parts:
            raise ValueError("No content parts in response")

        first_part = candidate.content.parts[0]
        if not hasattr(first_part, 'text') or not first_part.text:
            raise ValueError("No text content in response part")

        return first_part.text

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            # Pop api_key to avoid passing it to config builder;
            # client uses env-var-based auth set in _get_client()
            kwargs.pop('api_key', None)
            client = self._get_client()
            config = self._build_config(**kwargs)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model,
                contents=prompt,
                config=config,
            )

            return self._extract_text(response)

        except Exception as e:
            self._handle_google_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            kwargs.pop('api_key', None)
            client = self._get_client()
            config = self._build_config(**kwargs)

            # Use synchronous streaming wrapped in to_thread for each chunk
            response_iter = client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=config,
            )

            for chunk in response_iter:
                if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                    part = chunk.candidates[0].content.parts[0]
                    if hasattr(part, 'text') and part.text:
                        yield part.text
                        await asyncio.sleep(0)

        except Exception as e:
            self._handle_google_error(e, "streaming generation")
            yield f"Error: {str(e)}"
