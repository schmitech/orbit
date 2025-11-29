"""
Cohere vision service implementation using unified architecture.

This implementation provides vision capabilities using Cohere's multimodal models.
"""

from typing import Dict, Any, Union, List
from PIL import Image
import base64
from io import BytesIO
import logging

from ...base import ServiceType
from ...providers import CohereBaseService
from ...services import VisionService

logger = logging.getLogger(__name__)


class CohereVisionService(VisionService, CohereBaseService):
    """
    Cohere vision service using unified architecture.

    Supports:
    - Image analysis and description
    - OCR text extraction
    - Object detection
    - Multimodal inference (image + text)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Cohere vision service."""
        # Initialize via CohereBaseService first
        CohereBaseService.__init__(self, config, ServiceType.VISION, "cohere")
        
        # Get vision-specific configuration
        self.temperature = self._get_temperature(default=0.0)
        self.max_tokens = self._get_max_tokens(default=1000)
        self.top_p = self._get_top_p(default=1.0)

    def _get_temperature(self, default: float = 0.0) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 1000) -> int:
        """Get max_tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

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
            
            # Get image MIME type
            mime_type = self._get_image_mime_type(image)
            
            # Check API version and use appropriate format
            if hasattr(self, 'api_version') and self.api_version == 'v2':
                # Cohere v2 API format for images - using image_url format
                # According to https://docs.cohere.com/docs/aya-vision
                # Format: data:image/{format};base64,{base64_encoded_image}
                base64_image_url = f"data:{mime_type};base64,{image_base64}"
                
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
                                    "url": base64_image_url
                                }
                            }
                        ]
                    }
                ]

                logger.debug(f"Calling Cohere chat API with model={self.model}, image_size={len(image_base64)}, prompt_length={len(prompt)}")
                
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    p=self.top_p
                )
                
                logger.debug(f"Cohere response type: {type(response)}, has message: {hasattr(response, 'message')}")
                if hasattr(response, 'message'):
                    logger.debug(f"Response message type: {type(response.message)}, has content: {hasattr(response.message, 'content')}")
                    if hasattr(response.message, 'content'):
                        logger.debug(f"Response content type: {type(response.message.content)}, length: {len(response.message.content) if response.message.content else 0}")

                # v2 API response structure: message.content is an array of content blocks
                if response.message and response.message.content:
                    # Extract text from all content blocks
                    text_parts = []
                    for content_block in response.message.content:
                        if hasattr(content_block, 'text') and content_block.text:
                            text_parts.append(content_block.text)
                        elif isinstance(content_block, dict) and 'text' in content_block:
                            text_parts.append(content_block['text'])
                    
                    if text_parts:
                        return '\n'.join(text_parts)
                    else:
                        # Fallback: try to get text directly
                        if hasattr(response.message.content[0], 'text'):
                            return response.message.content[0].text
                        raise ValueError(f"No text content in response. Response structure: {type(response.message.content[0])}")
                else:
                    raise ValueError(f"No content returned from Cohere. Response: {response}")
            else:
                # v1 API - images may not be supported, but try anyway
                # For v1, we'll use the chat endpoint with a message containing the image
                # Note: v1 may have limited image support
                response = await self.client.chat(
                    model=self.model,
                    message=f"{prompt}\n\n[Image data: {image_base64[:50]}...]",
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    p=self.top_p
                )

                return response.text

        except Exception as e:
            logger.error(f"Cohere vision error: {str(e)}")
            logger.error(f"Image base64 length: {len(image_base64) if 'image_base64' in locals() else 'N/A'}")
            logger.error(f"API version: {getattr(self, 'api_version', 'unknown')}")
            logger.error(f"Model: {getattr(self, 'model', 'unknown')}")
            # Log the actual exception type and details
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            self._handle_cohere_error(e, "image analysis")
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
                    'confidence': 0.8,  # Placeholder - Cohere doesn't provide explicit confidence
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
            
            # Get image MIME type
            mime_type = self._get_image_mime_type(image)
            
            # Check API version and use appropriate format
            if hasattr(self, 'api_version') and self.api_version == 'v2':
                # Cohere v2 API format for images - using image_url format
                # According to https://docs.cohere.com/docs/aya-vision
                # Format: data:image/{format};base64,{base64_encoded_image}
                base64_image_url = f"data:{mime_type};base64,{image_base64}"
                
                # v2 API supports multimodal messages
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
                                    "url": base64_image_url
                                }
                            }
                        ]
                    }
                ]

                # Build parameters
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.pop('temperature', self.temperature),
                    "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                    "p": kwargs.pop('top_p', self.top_p),
                }
                params.update(kwargs)

                response = await self.client.chat(**params)

                # v2 API response structure: message.content is an array of content blocks
                if response.message and response.message.content:
                    # Extract text from all content blocks
                    text_parts = []
                    for content_block in response.message.content:
                        if hasattr(content_block, 'text') and content_block.text:
                            text_parts.append(content_block.text)
                        elif isinstance(content_block, dict) and 'text' in content_block:
                            text_parts.append(content_block['text'])
                    
                    if text_parts:
                        return '\n'.join(text_parts)
                    else:
                        # Fallback: try to get text directly
                        if hasattr(response.message.content[0], 'text'):
                            return response.message.content[0].text
                        raise ValueError(f"No text content in response. Response structure: {type(response.message.content[0])}")
                else:
                    raise ValueError(f"No content returned from Cohere. Response: {response}")
            else:
                # v1 API - use chat with combined prompt
                params = {
                    "model": self.model,
                    "message": f"{text_prompt}\n\n[Image data: {image_base64[:50]}...]",
                    "temperature": kwargs.pop('temperature', self.temperature),
                    "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                    "p": kwargs.pop('top_p', self.top_p),
                }
                params.update(kwargs)

                response = await self.client.chat(**params)
                return response.text

        except Exception as e:
            self._handle_cohere_error(e, "multimodal inference")
            raise

