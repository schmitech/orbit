"""
Anthropic vision service implementation using unified architecture.

This implementation provides vision capabilities using Anthropic's Claude models.
"""

from typing import Dict, Any, Union, List
from PIL import Image

from ...base import ServiceType
from ...providers import AnthropicBaseService
from ...services import VisionService


class AnthropicVisionService(VisionService, AnthropicBaseService):
    """
    Anthropic vision service using unified architecture.

    Supports:
    - Image analysis and description
    - OCR text extraction
    - Object detection
    - Multimodal inference (image + text)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Anthropic vision service."""
        # Initialize via AnthropicBaseService first
        AnthropicBaseService.__init__(self, config, ServiceType.VISION, "anthropic")
        
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
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]

            # Call Anthropic API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=messages
            )

            # Extract text from response
            if response.content and len(response.content) > 0:
                return response.content[0].text
            else:
                raise ValueError("No content returned from Anthropic")
            
        except Exception as e:
            self._handle_anthropic_error(e, "image analysis")
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
        description = await self.analyze_image(
            image,
            prompt="List all objects, people, and items visible in this image. For each item, describe what it is and where it appears in the image."
        )
        
        # Parse the description into structured format
        objects = []
        lines = description.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                objects.append({
                    'label': line.strip(),
                    'confidence': 0.8,
                    'bbox': [0, 0, 0, 0],
                    'index': i
                })
        
        return objects

    async def multimodal_inference(
        self,
        image: Union[str, bytes, Image.Image],
        text_prompt: str,
        **kwargs
    ) -> str:
        """Perform multimodal inference with image and text."""
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
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": text_prompt
                        }
                    ]
                }
            ]

            # Build parameters
            params = {
                "model": self.model,
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "temperature": kwargs.pop('temperature', self.temperature),
                "messages": messages
            }
            params.update(kwargs)

            response = await self.client.messages.create(**params)
            
            if response.content and len(response.content) > 0:
                return response.content[0].text
            else:
                raise ValueError("No content returned from Anthropic")

        except Exception as e:
            self._handle_anthropic_error(e, "multimodal inference")
            raise

