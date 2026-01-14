"""
Unified AI Services Architecture

This package provides a unified, extensible architecture for all AI services
in the Orbit system. It consolidates common functionality across service types
(embeddings, inference, moderation, reranking, vision, audio) and providers
(OpenAI, Anthropic, Ollama, Cohere, Mistral, etc.).

Key Components:
    - base: Core abstract base classes (AIService, ProviderAIService)
    - connection: Connection management, retry logic, rate limiting
    - config: Configuration parsing, validation, endpoint management
    - factory: Unified service factory for creating and managing services
    - providers: Provider-specific base classes
    - services: Service-specific interfaces

Example Usage:
    >>> from ai_services import AIServiceFactory, ServiceType
    >>>
    >>> # Create an embedding service
    >>> service = await AIServiceFactory.create_and_initialize_service(
    ...     ServiceType.EMBEDDING,
    ...     "openai",
    ...     config
    ... )
    >>>
    >>> # Use the service
    >>> embedding = await service.embed_query("Hello world")
    >>>
    >>> # Clean up
    >>> await service.close()

Benefits:
    - Reduced Code Duplication: Common functionality is centralized
    - Consistent Patterns: All services follow the same architecture
    - Easy Extensibility: Adding new services or providers is straightforward
    - Configurable Endpoints: API versions can be updated via configuration
    - Better Testing: Unified mocking and testing patterns
    - Improved Maintainability: Changes apply across all services
"""

import sys

# Ensure the package is reachable via both 'server.ai_services' and 'ai_services'
if __name__ == "server.ai_services":
    sys.modules.setdefault("ai_services", sys.modules[__name__])
elif __name__ == "ai_services":
    sys.modules.setdefault("server.ai_services", sys.modules[__name__])

from .base import AIService, ProviderAIService, ServiceType
from .connection import (
    ConnectionManager,
    RetryHandler,
    ConnectionVerifier,
    RateLimiter,
    retry_on_error
)
from .config import (
    ConfigResolver,
    ConfigValidator,
    EndpointManager,
    ConfigMerger
)
from .factory import AIServiceFactory

# Provider base classes (conditionally imported based on available dependencies)
# These are imported dynamically - only providers with installed dependencies are available
_available_providers = []
try:
    from .providers import OpenAIBaseService
    _available_providers.append('OpenAIBaseService')
except ImportError:
    pass

try:
    from .providers import AnthropicBaseService
    _available_providers.append('AnthropicBaseService')
except ImportError:
    pass

try:
    from .providers import OllamaBaseService
    _available_providers.append('OllamaBaseService')
except ImportError:
    pass

try:
    from .providers import CohereBaseService
    _available_providers.append('CohereBaseService')
except ImportError:
    pass

try:
    from .providers import MistralBaseService
    _available_providers.append('MistralBaseService')
except ImportError:
    pass

# Registry functions
from .registry import (
    register_all_services,
    register_embedding_services,
    register_inference_services,
    register_moderation_services,
    register_reranking_services,
    register_vision_services,
    register_audio_services,
    get_embedding_service_legacy
)

__version__ = "2.3.0"

__all__ = [
    # Core base classes
    'AIService',
    'ProviderAIService',
    'ServiceType',

    # Connection utilities
    'ConnectionManager',
    'RetryHandler',
    'ConnectionVerifier',
    'RateLimiter',
    'retry_on_error',

    # Configuration utilities
    'ConfigResolver',
    'ConfigValidator',
    'EndpointManager',
    'ConfigMerger',

    # Factory
    'AIServiceFactory',

    # Registry functions
    'register_all_services',
    'register_embedding_services',
    'register_inference_services',
    'register_moderation_services',
    'register_reranking_services',
    'register_vision_services',
    'register_audio_services',
    'get_embedding_service_legacy',
] + _available_providers  # Add dynamically loaded provider base classes
