"""
Moderation service implementations.

Available providers:
    - OpenAIModerationService: OpenAI moderation
    - AnthropicModerationService: Anthropic moderation
    - OllamaModerationService: Ollama moderation
    - ShieldstralModerationService: Shieldstral via vLLM or llama.cpp
    - PrivacyFilterModerationService: Local PII detection (openai/privacy-filter)
    - PresidioModerationService: PII detection via a Presidio analyzer service
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('openai_moderation_service', 'OpenAIModerationService'),
    ('anthropic_moderation_service', 'AnthropicModerationService'),
    ('ollama_moderation_service', 'OllamaModerationService'),
    ('shieldstral_moderation_service', 'ShieldstralModerationService'),
    ('privacy_filter_moderation_service', 'PrivacyFilterModerationService'),
    ('presidio_moderation_service', 'PresidioModerationService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.moderation.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
