"""
OpenAI vision service implementation using unified architecture.

This implementation provides vision capabilities using OpenAI's vision models.
"""

from typing import Dict, Any, Union, List
from PIL import Image
import base64
from io import BytesIO

from ...base import ServiceType
from ...providers import OpenAIBaseService
from ...services import VisionService


class OpenAIVisionService(VisionService, OpenAIBaseService):
    """
    OpenAI vision service using unified architecture.

    Supports:
    - Image analysis and description
    - OCR text extraction
    - Object detection
    - Multimodal inference (image + text)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the OpenAI vision service."""
        # Initialize via OpenAIBaseService first
        OpenAIBaseService.__init__(self, config, ServiceType.VISION, "openai")
        
        # Get vision-specific configuration
        self.temperature = self._get_temperature(default=0.0)
        self.max_tokens = self._get_max_tokens(default=1000)

    async def analyze_image(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context."
    ) -> str:
        """Analyze image content with detailed response."""
        if not self.initialized:
            await self.initialize()

        try:
            # Convert image to base64
            image_base64 = self._image_to_base64(image)
            
            # Create messages with image content
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]

            # Handle max_tokens-style variants for different models/endpoints
            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, {})

            # Build parameters
            params = {
                "model": self.model,
                "messages": messages,
                **{token_param: token_value},
            }

            # Only include temperature if the model supports it
            if self._supports_temperature():
                params["temperature"] = self.temperature

            # Call OpenAI vision API
            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_error(e, "image analysis")
            raise

    async def describe_image(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> str:
        """Generate description of image."""
        return await self.analyze_image(
            image,
            prompt="Describe this image in detail. Include the main subjects, setting, colors, and any notable features."
        )

    async def extract_text_from_image(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> str:
        """Extract text from image using OCR."""
        return await self.analyze_image(
            image,
            prompt="Extract all text from this image. Return only the text content, preserving line breaks and structure."
        )

    async def detect_objects(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> List[Dict[str, Any]]:
        """Detect objects in image."""
        # OpenAI vision doesn't provide explicit object detection API,
        # so we use vision analysis to infer objects
        description = await self.analyze_image(
            image,
            prompt="List all objects, people, and items visible in this image. For each item, describe what it is and where it appears in the image."
        )
        
        # Parse the description into structured format
        # This is a simplified implementation - in practice you might use structured output
        objects = []
        lines = description.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                objects.append({
                    'label': line.strip(),
                    'confidence': 0.8,  # Placeholder - OpenAI doesn't provide explicit confidence
                    'bbox': [0, 0, 0, 0],  # Placeholder
                    'index': i
                })
        
        return objects

    async def multimodal_inference(
        self,
        image: Union[str, bytes, Image.Image],
        text_prompt: str,
        **kwargs
    ) -> str:
        """
        Perform multimodal inference with image and text.

        Args:
            image: Image data
            text_prompt: Text prompt/question about the image
            **kwargs: Additional generation parameters
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Convert image to base64
            image_base64 = self._image_to_base64(image)
            
            # Create messages with image and text
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": text_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]

            # Handle max_tokens-style variants for different models/endpoints
            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, kwargs)

            # Merge kwargs with default parameters
            params = {
                "model": self.model,
                "messages": messages,
                token_param: token_value,
            }

            # Only include temperature if the model supports it
            if self._supports_temperature():
                params["temperature"] = kwargs.pop('temperature', self.temperature)

            params.update(kwargs)

            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_error(e, "multimodal inference")
            raise

    def _get_token_parameter_name(self) -> str:
        """Return the correct token-count parameter name for the active model."""
        provider_config = self._extract_provider_config()

        # Allow explicit configuration override
        configured_name = provider_config.get("token_parameter_name") or provider_config.get("token_parameter")
        if isinstance(configured_name, str):
            configured_name = configured_name.strip()
            if configured_name:
                return configured_name

        model_name = (self.model or "").lower()

        # Newer OpenAI chat models expect max_completion_tokens when using the chat.completions API
        modern_prefixes = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        if model_name.startswith(modern_prefixes):
            return "max_completion_tokens"

        # Default to the legacy chat.completions parameter name
        return "max_tokens"

    def _resolve_token_value(self, token_param: str, kwargs: Dict[str, Any]) -> int:
        """Determine the token limit value while respecting caller overrides."""
        # Pop all known token parameter variants so they don't leak into kwargs
        overrides = {
            "max_tokens": kwargs.pop("max_tokens", None),
            "max_completion_tokens": kwargs.pop("max_completion_tokens", None),
            "max_output_tokens": kwargs.pop("max_output_tokens", None),
        }

        # Caller provided the exact parameter we plan to use
        param_override = overrides.get(token_param)
        if param_override is not None:
            return param_override

        # Fall back to whichever override was provided, regardless of naming
        for value in overrides.values():
            if value is not None:
                return value

        # No override found; use configured default
        return self.max_tokens

    def _supports_temperature(self) -> bool:
        """Return whether the current model supports custom temperature values."""
        model_name = (self.model or "").lower()

        # Newer OpenAI models (gpt-5, o-series) only support default temperature (1.0)
        # and will error if you pass temperature=0.0 or any other value
        unsupported_prefixes = (
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        return not model_name.startswith(unsupported_prefixes)

