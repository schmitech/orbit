"""
Gemini vision service implementation using unified architecture.

This implementation provides vision capabilities using Google's Gemini models.
"""

from typing import Dict, Any, Union, List
from PIL import Image
import base64
from io import BytesIO
import asyncio

from ..base import ServiceType
from ..providers import GoogleBaseService
from ..services import VisionService


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
        # Initialize via GoogleBaseService first
        GoogleBaseService.__init__(self, config, ServiceType.VISION, "gemini")
        
        # Get vision-specific configuration
        self.temperature = self._get_temperature(default=0.0)
        self.transport = config.get('transport', 'rest')

    async def analyze_image(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context."
    ) -> str:
        """Analyze image content with detailed response."""
        if not self.initialized:
            await self.initialize()

        try:
            import google.generativeai as genai

            # Configure API
            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key, transport=self.transport)

            # Initialize model
            model = genai.GenerativeModel(self.model)

            # Prepare image
            image_bytes = self._prepare_image(image)
            
            # Convert bytes to PIL Image
            from PIL import Image as PILImage
            pil_image = PILImage.open(BytesIO(image_bytes))

            # Create content with image and prompt
            response = await model.generate_content_async(
                [prompt, pil_image]
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
            import google.generativeai as genai

            # Configure API
            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key, transport=self.transport)

            model = genai.GenerativeModel(self.model)

            # Prepare image
            image_bytes = self._prepare_image(image)
            from PIL import Image as PILImage
            pil_image = PILImage.open(BytesIO(image_bytes))

            generation_config = genai.GenerationConfig(
                temperature=kwargs.get('temperature', self.temperature),
                max_output_tokens=kwargs.get('max_tokens', 1000),
            )

            # REST transport uses synchronous methods, gRPC uses async
            if self.transport == 'rest':
                response = await asyncio.to_thread(
                    model.generate_content,
                    [text_prompt, pil_image],
                    generation_config=generation_config
                )
            else:
                response = await model.generate_content_async(
                    [text_prompt, pil_image],
                    generation_config=generation_config
                )

            if not response.candidates or not response.candidates[0].content:
                raise ValueError("No content returned from Gemini")
            
            return response.candidates[0].content.parts[0].text

        except Exception as e:
            self._handle_google_error(e, "multimodal inference")
            raise

