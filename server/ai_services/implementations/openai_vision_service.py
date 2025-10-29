"""
OpenAI vision service implementation using unified architecture.

This implementation provides vision capabilities using OpenAI's vision models.
"""

from typing import Dict, Any, Union, List
from PIL import Image
import base64
from io import BytesIO

from ..base import ServiceType
from ..providers import OpenAIBaseService
from ..services import VisionService


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

            # Call OpenAI vision API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

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

            # Merge kwargs with default parameters
            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "temperature": kwargs.pop('temperature', self.temperature)
            }
            params.update(kwargs)

            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_error(e, "multimodal inference")
            raise

