"""
Provider-specific base classes for AI services.

This package contains base classes for each AI provider that consolidate
common functionality like authentication, connection management, and
provider-specific API patterns.

Providers with missing dependencies are skipped gracefully.
"""

import logging

logger = logging.getLogger(__name__)

# Lazy import providers - only import those with installed dependencies
__all__ = []

# Try importing each provider base class
_providers = [
    ('openai_base', 'OpenAIBaseService'),
    ('openai_compatible_base', 'OpenAICompatibleBaseService'),
    ('anthropic_base', 'AnthropicBaseService'),
    ('ollama_base', 'OllamaBaseService'),
    ('cohere_base', 'CohereBaseService'),
    ('mistral_base', 'MistralBaseService'),
    ('jina_base', 'JinaBaseService'),
    ('aws_base', 'AWSBaseService'),
    ('azure_base', 'AzureBaseService'),
    ('google_base', 'GoogleBaseService'),
    ('nvidia_base', 'NVIDIABaseService'),
    ('replicate_base', 'ReplicateBaseService'),
    ('watson_base', 'WatsonBaseService'),
    ('llama_cpp_base', 'LlamaCppBaseService'),
    ('huggingface_base', 'HuggingFaceBaseService'),
]

for module_name, class_name in _providers:
    try:
        module = __import__(f'ai_services.providers.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        # Provider dependency not installed - skip it
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
