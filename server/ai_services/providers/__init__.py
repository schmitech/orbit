"""
Provider-specific base classes for AI services.

This package contains base classes for each AI provider that consolidate
common functionality like authentication, connection management, and
provider-specific API patterns.
"""

from .openai_base import OpenAIBaseService
from .openai_compatible_base import OpenAICompatibleBaseService
from .anthropic_base import AnthropicBaseService
from .ollama_base import OllamaBaseService
from .cohere_base import CohereBaseService
from .mistral_base import MistralBaseService
from .jina_base import JinaBaseService
from .aws_base import AWSBaseService
from .azure_base import AzureBaseService
from .google_base import GoogleBaseService
from .nvidia_base import NVIDIABaseService
from .replicate_base import ReplicateBaseService
from .watson_base import WatsonBaseService
from .llama_cpp_base import LlamaCppBaseService
from .huggingface_base import HuggingFaceBaseService

__all__ = [
    'OpenAIBaseService',
    'OpenAICompatibleBaseService',
    'AnthropicBaseService',
    'OllamaBaseService',
    'CohereBaseService',
    'MistralBaseService',
    'JinaBaseService',
    'AWSBaseService',
    'AzureBaseService',
    'GoogleBaseService',
    'NVIDIABaseService',
    'ReplicateBaseService',
    'WatsonBaseService',
    'LlamaCppBaseService',
    'HuggingFaceBaseService',
]
