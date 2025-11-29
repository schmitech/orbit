"""
Moderation service implementations.

Available providers:
    - OpenAIModerationService: OpenAI moderation
    - AnthropicModerationService: Anthropic moderation
    - OllamaModerationService: Ollama moderation
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('openai_moderation_service', 'OpenAIModerationService'),
    ('anthropic_moderation_service', 'AnthropicModerationService'),
    ('ollama_moderation_service', 'OllamaModerationService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.moderation.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
