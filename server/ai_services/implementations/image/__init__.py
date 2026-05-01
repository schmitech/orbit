"""
Image generation service implementations.

Available providers:
    - OpenAIImageService: OpenAI DALL-E 2/3 and GPT-Image-1
    - GeminiImageService: Google Imagen 3
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('openai_image_service', 'OpenAIImageService'),
    ('gemini_image_service', 'GeminiImageService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.image.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
