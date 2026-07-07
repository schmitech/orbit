"""
OCR service implementations.

Available providers:
    - MistralOcrService: Mistral native OCR endpoint (PDF/image-direct)
    - OpenAIOcrService / GeminiOcrService / AnthropicOcrService / ... :
      vision-backed OCR (rasterize PDF pages, reuse the vision provider)
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('mistral_ocr_service', 'MistralOcrService'),
    ('vision_ocr_service', 'OpenAIOcrService'),
    ('vision_ocr_service', 'GeminiOcrService'),
    ('vision_ocr_service', 'AnthropicOcrService'),
    ('vision_ocr_service', 'CohereOcrService'),
    ('vision_ocr_service', 'OllamaOcrService'),
    ('vision_ocr_service', 'VLLMOcrService'),
    ('vision_ocr_service', 'LlamaCppOcrService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.ocr.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
