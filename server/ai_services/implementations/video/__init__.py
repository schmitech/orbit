"""
Video generation service implementations.

Available providers:
    - GeminiVideoService: Google Veo 2
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('gemini_video_service', 'GeminiVideoService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.video.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
