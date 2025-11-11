"""
Ollama vision service implementation using unified architecture.

This implementation provides vision capabilities using Ollama's multimodal models
like qwen3-vl. It follows the existing Ollama service patterns and implements
the VisionService interface.
"""

from typing import Dict, Any, Union, List
from PIL import Image

from ..base import ServiceType
from ..providers import OllamaBaseService
from ..services import VisionService


class OllamaVisionService(VisionService, OllamaBaseService):
    """
    Ollama vision service using unified architecture.

    Supports:
    - Image analysis and description
    - OCR text extraction
    - Object detection
    - Multimodal inference (image + text)

    Uses Ollama's chat API with multimodal messages for vision tasks.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama vision service.

        Args:
            config: Configuration dictionary
        """
        # Initialize via OllamaBaseService
        OllamaBaseService.__init__(self, config, ServiceType.VISION, "ollama")

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
                raise ValueError("Failed to initialize Ollama vision service")

        async def _analyze():
            session = await self.session_manager.get_session()

            # Convert image to base64
            base64_image = self._image_to_base64(image)

            # Use Ollama's chat endpoint with images field
            # Ollama format: content is a string, images is a separate array
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [base64_image]
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                }
            }

            # Add max_tokens if specified
            if self.max_tokens > 0:
                payload["options"]["num_predict"] = self.max_tokens

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Ollama vision error: {error_text}")

                data = await response.json()
                return data.get('message', {}).get('content', '')

        # Use Ollama's retry handler
        return await self.execute_with_retry(_analyze)

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
                raise ValueError("Failed to initialize Ollama vision service")

        async def _inference():
            session = await self.session_manager.get_session()

            # Convert image to base64
            base64_image = self._image_to_base64(image)

            # Use Ollama's chat endpoint with images field
            # Ollama format: content is a string, images is a separate array
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": text_prompt,
                        "images": [base64_image]
                    }
                ],
                "stream": kwargs.get('stream', False),
                "options": {
                    "temperature": kwargs.get('temperature', self.temperature),
                }
            }

            # Add max_tokens if specified
            max_tokens = kwargs.get('max_tokens', self.max_tokens)
            if max_tokens > 0:
                payload["options"]["num_predict"] = max_tokens

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Ollama vision error: {error_text}")

                data = await response.json()
                return data.get('message', {}).get('content', '')

        # Use Ollama's retry handler
        return await self.execute_with_retry(_inference)
