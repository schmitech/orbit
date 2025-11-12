"""
vLLM vision service implementation using unified architecture.

vLLM provides an OpenAI-compatible API for multimodal models,
so we can use OpenAICompatibleBaseService similar to the inference service.
"""

from typing import Dict, Any, Union, List
from PIL import Image

from ..base import ServiceType
from ..providers import OpenAICompatibleBaseService
from ..services import VisionService


class VLLMVisionService(VisionService, OpenAICompatibleBaseService):
    """
    vLLM vision service using unified architecture.

    Supports:
    - Image analysis and description
    - OCR text extraction
    - Object detection
    - Multimodal inference (image + text)

    Uses vLLM's OpenAI-compatible chat API with multimodal messages for vision tasks.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the vLLM vision service.

        Args:
            config: Configuration dictionary
        """
        # Initialize via OpenAICompatibleBaseService
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.VISION, "vllm")

        # Get vision-specific configuration
        provider_config = self._extract_provider_config()
        self.temperature = provider_config.get('temperature', 0.0)
        self.max_tokens = provider_config.get('max_tokens', 1000)
        self.stream = provider_config.get('stream', False)

    async def analyze_image(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context."
    ) -> str:
        """
        Analyze image content with detailed response.

        Args:
            image: Image data (path, bytes, or PIL Image)
            prompt: Optional prompt for specific analysis

        Returns:
            Detailed analysis of image content
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize vLLM vision service")

        try:
            # Convert image to base64 with data URL format
            base64_image = self._image_to_base64(image)
            image_url = f"data:image/png;base64,{base64_image}"

            # Use OpenAI-compatible API with image_url in content
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "image analysis")
            raise

    async def describe_image(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> str:
        """
        Generate description of image.

        Args:
            image: Image data (path, bytes, or PIL Image)

        Returns:
            Description of the image
        """
        return await self.analyze_image(
            image,
            prompt="Describe this image in detail. Include the main subjects, setting, colors, and any notable features."
        )

    async def extract_text_from_image(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> str:
        """
        Extract text from image using OCR.

        Args:
            image: Image data (path, bytes, or PIL Image)

        Returns:
            Extracted text from the image
        """
        return await self.analyze_image(
            image,
            prompt="Extract all text from this image. Return only the text content, preserving line breaks and structure."
        )

    async def detect_objects(
        self,
        image: Union[str, bytes, Image.Image]
    ) -> List[Dict[str, Any]]:
        """
        Detect objects in image.

        Args:
            image: Image data (path, bytes, or PIL Image)

        Returns:
            List of detected objects with labels
        """
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
        """
        Perform multimodal inference with image and text.

        Args:
            image: Image data (path, bytes, or PIL Image)
            text_prompt: Text prompt/question about the image
            **kwargs: Additional generation parameters

        Returns:
            Generated response based on both image and text
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize vLLM vision service")

        try:
            # Convert image to base64 with data URL format
            base64_image = self._image_to_base64(image)
            image_url = f"data:image/png;base64,{base64_image}"

            # Use OpenAI-compatible API with image_url in content
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', self.temperature),
                max_tokens=kwargs.get('max_tokens', self.max_tokens),
                stream=kwargs.get('stream', False)
            )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "multimodal inference")
            raise
