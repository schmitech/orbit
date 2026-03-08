"""
Gemini vision service implementation using unified architecture.

Uses the google-genai SDK (replacement for deprecated google-generativeai).
"""

from typing import Dict, Any, Union, List
from PIL import Image
from io import BytesIO
import asyncio
import logging

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import VisionService

logger = logging.getLogger(__name__)


class GeminiVisionService(VisionService, GoogleBaseService):
    """
    Gemini vision service using unified architecture.

    Supports:
    - Image analysis and description
    - OCR text extraction
    - Object detection
    - Multimodal inference (image + text)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Gemini vision service."""
        GoogleBaseService.__init__(self, config, ServiceType.VISION, "gemini")

        self.temperature = self._get_temperature(default=0.0)

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

    async def analyze_image(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context."
    ) -> str:
        """Analyze image content with detailed response."""
        if not self.initialized:
            await self.initialize()

        try:
            client = self._get_client()

            # Prepare image
            image_bytes = self._prepare_image(image)
            from PIL import Image as PILImage
            pil_image = PILImage.open(BytesIO(image_bytes))

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model,
                contents=[prompt, pil_image],
            )

            if not response.candidates or not response.candidates[0].content:
                raise ValueError("No content returned from Gemini")

            return response.candidates[0].content.parts[0].text

        except Exception as e:
            self._handle_google_error(e, "image analysis")
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
            from google.genai import types

            client = self._get_client()

            # Prepare image
            image_bytes = self._prepare_image(image)
            from PIL import Image as PILImage
            pil_image = PILImage.open(BytesIO(image_bytes))

            config = types.GenerateContentConfig(
                temperature=kwargs.get('temperature', self.temperature),
                max_output_tokens=kwargs.get('max_tokens', 1000),
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model,
                contents=[text_prompt, pil_image],
                config=config,
            )

            if not response.candidates or not response.candidates[0].content:
                raise ValueError("No content returned from Gemini")

            return response.candidates[0].content.parts[0].text

        except Exception as e:
            self._handle_google_error(e, "multimodal inference")
            raise
