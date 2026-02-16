"""
Vision service interface and base implementations.

This module defines the common interface for all vision services,
providing a unified API for image understanding regardless of the underlying provider.
"""

from abc import abstractmethod
from typing import Dict, Any, List, Optional, Union
from PIL import Image
import base64
from io import BytesIO

from ..base import ProviderAIService, ServiceType


class VisionService(ProviderAIService):
    """
    Base class for all vision services.

    This class defines the common interface that all vision service
    implementations must follow, regardless of provider (OpenAI, Gemini,
    Anthropic, etc.).

    Key Methods:
        - analyze_image: Analyze image content with detailed response
        - describe_image: Generate description of image
        - extract_text_from_image: OCR capabilities
        - detect_objects: Object detection
        - multimodal_inference: Vision-enhanced LLM inference

    Configuration Support:
        - Configurable vision models via config
        - Multimodal support (image + text)
        - OCR and visual understanding
    """

    # Class attribute for service type
    service_type = ServiceType.VISION

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the vision service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'openai', 'gemini')
        """
        super().__init__(config, ServiceType.VISION, provider_name)

    @abstractmethod
    async def analyze_image(
        self, 
        image: Union[str, bytes, Image.Image], 
        prompt: Optional[str] = None
    ) -> str:
        """
        Analyze image content with detailed response.

        This method analyzes image content and returns detailed information
        about what's in the image.

        Args:
            image: Image data (path, bytes, or PIL Image)
            prompt: Optional prompt for specific analysis

        Returns:
            Detailed analysis of image content

        Example:
            >>> service = OpenAIVisionService(config)
            >>> await service.initialize()
            >>> analysis = await service.analyze_image("image.png")
            >>> print(analysis)
            "This image shows a sunset over mountains..."
        """
        pass

    @abstractmethod
    async def describe_image(
        self, 
        image: Union[str, bytes, Image.Image]
    ) -> str:
        """
        Generate description of image.

        This method generates a natural language description of the image content.

        Args:
            image: Image data (path, bytes, or PIL Image)

        Returns:
            Description of the image

        Example:
            >>> description = await service.describe_image("image.png")
            >>> print(description)
            "A red sports car parked in front of a modern building"
        """
        pass

    @abstractmethod
    async def extract_text_from_image(
        self, 
        image: Union[str, bytes, Image.Image]
    ) -> str:
        """
        Extract text from image using OCR.

        This method performs optical character recognition on the image
        to extract any text content.

        Args:
            image: Image data (path, bytes, or PIL Image)

        Returns:
            Extracted text from the image

        Example:
            >>> text = await service.extract_text_from_image("document.jpg")
            >>> print(text)
            "The quick brown fox jumps over the lazy dog"
        """
        pass

    @abstractmethod
    async def detect_objects(
        self, 
        image: Union[str, bytes, Image.Image]
    ) -> List[Dict[str, Any]]:
        """
        Detect objects in image.

        This method detects and identifies objects in the image.

        Args:
            image: Image data (path, bytes, or PIL Image)

        Returns:
            List of detected objects with bounding boxes and labels

        Example:
            >>> objects = await service.detect_objects("image.jpg")
            >>> print(objects)
            [{'label': 'car', 'confidence': 0.95, 'bbox': [10, 20, 100, 200]}, ...]
        """
        pass

    @abstractmethod
    async def multimodal_inference(
        self, 
        image: Union[str, bytes, Image.Image],
        text_prompt: str,
        **kwargs
    ) -> str:
        """
        Perform multimodal inference with image and text.

        This method combines image understanding with text generation,
        enabling queries about image content.

        Args:
            image: Image data (path, bytes, or PIL Image)
            text_prompt: Text prompt/question about the image
            **kwargs: Additional generation parameters

        Returns:
            Generated response based on both image and text

        Example:
            >>> response = await service.multimodal_inference(
            ...     "chart.png",
            ...     "What does this chart show?"
            ... )
            >>> print(response)
            "This chart shows sales data trending upward over the past quarter..."
        """
        pass

    def _prepare_image(self, image: Union[str, bytes, Image.Image]) -> bytes:
        """
        Prepare image for processing.

        Args:
            image: Image data in various formats

        Returns:
            Image as bytes
        """
        if isinstance(image, str):
            # Assume it's a path
            with open(image, 'rb') as f:
                return f.read()
        elif isinstance(image, bytes):
            return image
        elif isinstance(image, Image.Image):
            # Convert PIL Image to bytes
            buf = BytesIO()
            image.save(buf, format='PNG')
            return buf.getvalue()
        else:
            raise ValueError(f"Unsupported image type: {type(image)}")

    def _image_to_base64(self, image: Union[str, bytes, Image.Image]) -> str:
        """
        Convert image to base64 string.

        Args:
            image: Image data

        Returns:
            Base64 encoded image string
        """
        image_bytes = self._prepare_image(image)
        return base64.b64encode(image_bytes).decode('utf-8')

    def _get_image_mime_type(self, image: Union[str, bytes, Image.Image]) -> str:
        """
        Get MIME type for image.

        Args:
            image: Image data

        Returns:
            MIME type string
        """
        # Default to PNG
        return "image/png"


class VisionResult:
    """
    Structured result for vision operations.

    This class provides a standardized way to return vision results
    with metadata.
    """

    def __init__(
        self,
        content: str,
        extracted_text: Optional[str] = None,
        detected_objects: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
        provider: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize vision result.

        Args:
            content: Main vision analysis content
            extracted_text: Extracted text from image
            detected_objects: List of detected objects
            description: Image description
            provider: Provider name
            metadata: Optional metadata
        """
        self.content = content
        self.extracted_text = extracted_text
        self.detected_objects = detected_objects or []
        self.description = description
        self.provider = provider
        self.metadata = metadata or {}

    def __str__(self) -> str:
        """Return the content text."""
        return self.content

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.content,
            'extracted_text': self.extracted_text,
            'detected_objects': self.detected_objects,
            'description': self.description,
            'provider': self.provider,
            'metadata': self.metadata
        }


# Helper function for service creation
def create_vision_service(
    provider: str,
    config: Dict[str, Any]
) -> VisionService:
    """
    Factory function to create a vision service.

    This is a convenience function that will use the AIServiceFactory
    once services are registered.

    Args:
        provider: Provider name (e.g., 'openai', 'gemini')
        config: Configuration dictionary

    Returns:
        Vision service instance

    Example:
        >>> service = create_vision_service('openai', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.VISION,
        provider,
        config
    )

