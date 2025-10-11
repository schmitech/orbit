# AI Services Architecture Refactoring Roadmap

## Overview

This roadmap outlines a comprehensive refactoring plan to simplify the design and reduce code duplication across AI services (embeddings, providers, moderators, rerankers) by extracting common abstractions and base modules. The goal is to create a unified, extensible architecture that will support future AI services like vision and audio.

## Current State Analysis

### Identified Issues
- **Code Duplication**: Each service type (embeddings, providers, moderators, rerankers) implements similar connection, configuration, and error handling logic
- **Inconsistent Patterns**: Different services use different patterns for API key resolution, base URL handling, and client initialization
- **Scattered Configuration**: Service configurations are spread across multiple YAML files with inconsistent structures
- **Maintenance Overhead**: Changes to common functionality require updates across multiple service implementations
- **Limited Extensibility**: Adding new AI services (vision, audio) requires duplicating existing patterns

### Current Architecture
```
server/
├── embeddings/           # Embedding services
│   ├── base.py          # EmbeddingService base class
│   ├── openai.py        # OpenAI implementation
│   ├── ollama.py        # Ollama implementation
│   └── ...
├── inference/pipeline/providers/  # LLM providers
│   ├── llm_provider.py  # LLMProvider interface
│   ├── openai_provider.py
│   ├── ollama_provider.py
│   └── ...
├── moderators/          # Moderation services
│   ├── base.py          # ModeratorService base class
│   ├── openai.py        # OpenAI implementation
│   └── ...
└── rerankers/           # Reranking services
    ├── base.py          # RerankerService base class
    ├── ollama.py        # Ollama implementation
    └── ...
```

## Target Architecture

### Unified AI Services Structure
```
server/
├── ai_services/                    # Unified AI services
│   ├── base.py                     # Core base classes
│   ├── connection.py               # Connection management
│   ├── config.py                   # Configuration utilities
│   ├── factory.py                  # Unified service factory
│   ├── providers/                  # Provider-specific base classes
│   │   ├── openai_base.py         # OpenAI common functionality
│   │   ├── anthropic_base.py      # Anthropic common functionality
│   │   ├── ollama_base.py         # Ollama common functionality
│   │   └── ...
│   └── services/                   # Service-specific interfaces
│       ├── embedding_service.py    # Embedding service interface
│       ├── inference_service.py    # Inference service interface
│       ├── moderation_service.py   # Moderation service interface
│       ├── reranking_service.py    # Reranking service interface
│       ├── vision_service.py       # Vision service interface (future)
│       └── audio_service.py        # Audio service interface (future)
├── embeddings/                     # Legacy embeddings (deprecated)
├── inference/pipeline/providers/   # Legacy providers (deprecated)
├── moderators/                     # Legacy moderators (deprecated)
└── rerankers/                      # Legacy rerankers (deprecated)
```

## Implementation Phases

### Phase 1: Core Base Abstractions 🏗️
**Duration**: 1 week  
**Priority**: High

#### 1.1 Create Base AI Service Infrastructure
- **Location**: `server/ai_services/`
- **Purpose**: Common foundation for all AI services

**Deliverables:**
- `server/ai_services/base.py` - Abstract base classes
- `server/ai_services/connection.py` - Connection management utilities
- `server/ai_services/config.py` - Configuration parsing utilities
- `server/ai_services/factory.py` - Unified service factory

**Key Features:**
- Generic `AIService` base class with common lifecycle methods
- `ProviderAIService` base class for provider-specific services
- Connection management with automatic retry and timeout handling
- Unified configuration parsing with environment variable support
- Service registry and factory pattern

#### 1.2 Provider-Specific Base Classes
- **Location**: `server/ai_services/providers/`
- **Purpose**: Provider-specific common functionality

**Deliverables:**
- `server/ai_services/providers/openai_base.py`
- `server/ai_services/providers/anthropic_base.py`
- `server/ai_services/providers/ollama_base.py`
- `server/ai_services/providers/cohere_base.py`
- `server/ai_services/providers/mistral_base.py`

**Key Features:**
- Provider-specific connection handling
- API key resolution and validation
- Base URL configuration
- Common error handling patterns
- Client initialization and management

### Phase 2: Service-Specific Abstractions 🔧
**Duration**: 1 week  
**Priority**: High

#### 2.1 Service Type Abstractions
- **Location**: `server/ai_services/services/`
- **Purpose**: Service-specific interfaces

**Deliverables:**
- `server/ai_services/services/embedding_service.py`
- `server/ai_services/services/inference_service.py`
- `server/ai_services/services/moderation_service.py`
- `server/ai_services/services/reranking_service.py`
- `server/ai_services/services/vision_service.py` (future)

**Key Features:**
- Service-specific method signatures
- Common result types and data structures
- Batch processing capabilities
- Service-specific configuration validation
- **Configurable endpoints** for easy API version updates

#### 2.2 Configuration Structure Updates
- **Location**: `config/`
- **Purpose**: Unified configuration with configurable endpoints

**Deliverables:**
- Updated `config/embeddings.yaml` with endpoint configuration
- Updated `config/inference.yaml` with endpoint configuration
- Updated `config/rerankers.yaml` with endpoint configuration
- New `config/vision.yaml` for future vision services
- New `config/audio.yaml` for future audio services

**Key Features:**
- **Configurable API endpoints** for each provider
- **Version-specific endpoint paths** (e.g., `/v1/`, `/v2/`, `/beta/`)
- **Environment-specific endpoints** (dev, staging, prod)
- **Fallback endpoint configuration** for API version changes

### Phase 3: Migration of Existing Services 🔄
**Duration**: 2 weeks  
**Priority**: High

#### 3.1 Embeddings Migration
**Week 1 of Phase 3**

**Tasks:**
- Refactor existing embedding services to use new base classes
- Maintain backward compatibility with existing interfaces
- Update embedding factory to use new architecture
- Migrate configuration parsing to unified system

**Deliverables:**
- Updated embedding services using new base classes
- Backward-compatible embedding factory
- Updated configuration structure
- Migration tests

#### 3.2 Providers Migration
**Week 1 of Phase 3**

**Tasks:**
- Refactor inference providers to use new base classes
- Consolidate common connection logic
- Update provider factory to use new architecture
- Migrate configuration parsing

**Deliverables:**
- Updated provider implementations
- Unified provider factory
- Updated configuration structure
- Migration tests

#### 3.3 Moderators Migration
**Week 2 of Phase 3**

**Tasks:**
- Refactor moderation services to use new base classes
- Consolidate API key management
- Update moderator factory
- Migrate configuration parsing

**Deliverables:**
- Updated moderator implementations
- Unified moderator factory
- Updated configuration structure
- Migration tests

#### 3.4 Rerankers Migration
**Week 2 of Phase 3**

**Tasks:**
- Refactor reranking services to use new base classes
- Consolidate connection patterns
- Update reranker factory
- Migrate configuration parsing

**Deliverables:**
- Updated reranker implementations
- Unified reranker factory
- Updated configuration structure
- Migration tests

### Phase 4: Unified Configuration & Factory ⚙️
**Duration**: 1 week  
**Priority**: Medium

#### 4.1 Unified Service Factory
**Tasks:**
- Create single factory for all AI services
- Implement service discovery and registration
- Add service lifecycle management
- Implement service caching and singleton patterns

**Deliverables:**
- `server/ai_services/factory.py` - Unified service factory
- Service registry system
- Lifecycle management utilities
- Caching and singleton implementations

#### 4.2 Configuration Updates
**Tasks:**
- Update configuration system to support unified services
- Add service-specific configuration sections
- Implement configuration validation
- Update configuration documentation

**Deliverables:**
- Updated configuration files
- Configuration validation system
- Updated documentation
- Migration guide for configuration changes

### Phase 5: Future Extensibility 🚀
**Duration**: 1 week  
**Priority**: Low

#### 5.1 Vision Services
**Tasks:**
- Add vision service support using new architecture
- Implement common vision operations
- Add vision-specific providers
- Create vision service examples

**Deliverables:**
- `server/ai_services/services/vision_service.py`
- Vision provider implementations
- Vision service examples
- Vision service documentation

#### 5.2 Audio Services
**Tasks:**
- Add audio service support
- Implement common audio operations
- Add audio-specific providers
- Create audio service examples

**Deliverables:**
- `server/ai_services/services/audio_service.py`
- Audio provider implementations
- Audio service examples
- Audio service documentation

## Detailed Implementation Plan

### Phase 1: Core Base Abstractions

#### 1.1 Base AI Service Infrastructure

**`server/ai_services/base.py`**
```python
"""
Base classes for all AI services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, Generic, TypeVar
import logging
import asyncio
from enum import Enum

T = TypeVar('T')

class ServiceType(Enum):
    EMBEDDING = "embedding"
    INFERENCE = "inference"
    MODERATION = "moderation"
    RERANKING = "reranking"
    VISION = "vision"
    AUDIO = "audio"

class AIService(ABC, Generic[T]):
    """Base class for all AI services."""
    
    def __init__(self, config: Dict[str, Any], service_type: ServiceType):
        self.config = config
        self.service_type = service_type
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.initialized = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the service."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the service and release resources."""
        pass
    
    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify the connection to the service."""
        pass

class ProviderAIService(AIService[T]):
    """Base class for provider-specific AI services."""
    
    def __init__(self, config: Dict[str, Any], service_type: ServiceType, provider_name: str):
        super().__init__(config, service_type)
        self.provider_name = provider_name
        self.api_key = None
        self.base_url = None
        self.model = None
        self.client = None
    
    def _extract_provider_config(self) -> Dict[str, Any]:
        """Extract provider-specific configuration."""
        return self.config.get(self.provider_name, {})
    
    def _resolve_api_key(self, key_name: str) -> str:
        """Resolve API key from environment or config."""
        # Implementation for API key resolution
        pass
    
    def _get_base_url(self, default_url: str) -> str:
        """Get base URL from config or use default."""
        # Implementation for base URL resolution
        pass
```

**`server/ai_services/connection.py`**
```python
"""
Connection management utilities for AI services.
"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional, Callable
from functools import wraps

class ConnectionManager:
    """Manages HTTP connections for AI services."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self.session = aiohttp.ClientSession(
                base_url=self.base_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session
    
    async def close(self):
        """Close the connection."""
        if self.session and not self.session.closed:
            await self.session.close()
```

#### 1.2 Provider-Specific Base Classes

**`server/ai_services/providers/openai_base.py`**
```python
"""
OpenAI-specific base class for all OpenAI services.
"""

from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from ..base import ProviderAIService, ServiceType

class OpenAIBaseService(ProviderAIService):
    """Base class for all OpenAI services."""
    
    def __init__(self, config: Dict[str, Any], service_type: ServiceType):
        super().__init__(config, service_type, "openai")
        self._setup_openai_config()
    
    def _setup_openai_config(self):
        """Setup OpenAI-specific configuration."""
        openai_config = self._extract_provider_config()
        self.api_key = self._resolve_api_key("OPENAI_API_KEY")
        self.base_url = openai_config.get("base_url", "https://api.openai.com/v1")
        self.model = openai_config.get("model")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
    
    async def verify_connection(self) -> bool:
        """Verify OpenAI connection."""
        try:
            # Test with a simple API call
            await self.client.models.list()
            return True
        except Exception as e:
            self.logger.error(f"OpenAI connection verification failed: {e}")
            return False
```

### Phase 2: Service-Specific Abstractions

#### 2.1 Service Type Abstractions

**`server/ai_services/services/embedding_service.py`**
```python
"""
Embedding service interface and implementations.
"""

from abc import abstractmethod
from typing import List, Dict, Any
from ..base import ProviderAIService, ServiceType

class EmbeddingService(ProviderAIService):
    """Base class for embedding services."""
    
    def __init__(self, config: Dict[str, Any], provider_name: str):
        super().__init__(config, ServiceType.EMBEDDING, provider_name)
        self.endpoint = self._load_endpoint()
    
    def _load_endpoint(self) -> str:
        """Load configurable endpoint for the service."""
        provider_config = self._extract_provider_config()
        return provider_config.get('endpoint', '/v1/embeddings')
    
    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Generate embeddings for a query string."""
        pass
    
    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents."""
        pass
    
    @abstractmethod
    async def get_dimensions(self) -> int:
        """Get the dimensionality of the embeddings."""
        pass
```

#### 2.2 Configuration Structure with Configurable Endpoints

**Updated `config/embeddings.yaml`**
```yaml
# Global embedding configuration
embedding:
  provider: "ollama"  # Default embedding provider
  enabled: true       # Whether embeddings are enabled globally

# Provider-specific configurations
embeddings:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "text-embedding-3-small"
    dimensions: 1536
    batch_size: 10
    # Configurable endpoints for easy API version updates
    endpoints:
      embeddings: "/v1/embeddings"           # Main embeddings endpoint
      models: "/v1/models"                   # Models listing endpoint
      health: "/v1/health"                   # Health check endpoint
      # Future endpoints
      vision: "/v1/vision/analyze"           # For future vision support
      audio: "/v1/audio/transcribe"          # For future audio support
    # Fallback endpoints for API version changes
    fallback_endpoints:
      embeddings: "/v1/embeddings"           # Fallback if new version fails
      models: "/v1/models"
    # Environment-specific overrides
    environments:
      development:
        base_url: "https://api-dev.openai.com"
        endpoints:
          embeddings: "/v1/embeddings"
      staging:
        base_url: "https://api-staging.openai.com"
        endpoints:
          embeddings: "/v1/embeddings"
      production:
        base_url: "https://api.openai.com"
        endpoints:
          embeddings: "/v1/embeddings"

  ollama:
    base_url: "http://localhost:11434"
    model: "nomic-embed-text"
    dimensions: 768
    # Ollama-specific endpoints
    endpoints:
      embeddings: "/api/embeddings"
      models: "/api/tags"
      health: "/api/version"
      pull: "/api/pull"
      generate: "/api/generate"
    # Retry configuration
    retry:
      enabled: true
      max_retries: 5
      initial_wait_ms: 2000
      max_wait_ms: 30000
      exponential_base: 2
    # Timeout configuration
    timeout:
      connect: 10000
      total: 60000
      warmup: 45000

  cohere:
    api_key: ${COHERE_API_KEY}
    model: "embed-english-v3.0"
    input_type: "search_document"
    dimensions: 1024
    batch_size: 32
    truncate: "NONE"
    embedding_types: ["float"]
    # Cohere-specific endpoints
    endpoints:
      embeddings: "/v1/embed"
      models: "/v1/models"
      health: "/v1/health"
    # API version management
    api_version: "v1"
    version_fallback: true  # Enable automatic fallback to previous version
```

**New `config/vision.yaml`**
```yaml
# Vision services configuration
vision:
  provider: "openai"  # Default vision provider
  enabled: false      # Disabled by default

# Provider-specific configurations
visions:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "gpt-4-vision-preview"
    max_tokens: 1000
    # Vision-specific endpoints
    endpoints:
      analyze: "/v1/chat/completions"        # Image analysis
      generate: "/v1/images/generations"     # Image generation
      variations: "/v1/images/variations"    # Image variations
      edits: "/v1/images/edits"              # Image editing
      models: "/v1/models"                   # Available models
      health: "/v1/health"                   # Health check
    # Image processing parameters
    image_processing:
      max_size: "1024x1024"
      supported_formats: ["png", "jpg", "jpeg", "gif", "webp"]
      quality: "standard"  # standard, hd
    # Batch processing
    batch_size: 5
    timeout:
      connect: 10000
      total: 60000

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-5-sonnet-20241022"
    max_tokens: 1000
    # Anthropic-specific endpoints
    endpoints:
      analyze: "/v1/messages"                # Image analysis
      models: "/v1/models"                   # Available models
      health: "/v1/health"                   # Health check
    # Image processing parameters
    image_processing:
      max_size: "2048x2048"
      supported_formats: ["png", "jpg", "jpeg", "gif", "webp"]
    batch_size: 3
    timeout:
      connect: 10000
      total: 60000
```

**New `config/audio.yaml`**
```yaml
# Audio services configuration
audio:
  provider: "openai"  # Default audio provider
  enabled: false      # Disabled by default

# Provider-specific configurations
audios:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "whisper-1"
    # Audio-specific endpoints
    endpoints:
      transcribe: "/v1/audio/transcriptions"  # Speech to text
      translate: "/v1/audio/translations"     # Speech to text with translation
      speech: "/v1/audio/speech"              # Text to speech
      models: "/v1/models"                    # Available models
      health: "/v1/health"                    # Health check
    # Audio processing parameters
    audio_processing:
      supported_formats: ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
      max_file_size: "25MB"
      max_duration: "25 minutes"
    # Language support
    languages:
      default: "auto"
      supported: ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh"]
    batch_size: 1
    timeout:
      connect: 10000
      total: 300000  # 5 minutes for audio processing

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-5-sonnet-20241022"
    # Anthropic-specific endpoints (if they add audio support)
    endpoints:
      transcribe: "/v1/audio/transcriptions"
      models: "/v1/models"
      health: "/v1/health"
    audio_processing:
      supported_formats: ["mp3", "wav", "m4a"]
      max_file_size: "10MB"
      max_duration: "10 minutes"
    batch_size: 1
    timeout:
      connect: 10000
      total: 120000  # 2 minutes
```

### Phase 3: Migration Strategy

#### 3.1 Backward Compatibility
- Keep existing interfaces working during migration
- Use adapter pattern for transition period
- Gradual migration of services
- Comprehensive testing at each step

#### 3.2 Migration Steps
1. Create new base classes and interfaces
2. Implement provider-specific base classes
3. Migrate one service type at a time
4. Update factories to use new architecture
5. Remove old implementations after successful migration

### Phase 4: Unified Factory

**`server/ai_services/factory.py`**
```python
"""
Unified factory for all AI services.
"""

from typing import Dict, Any, Type, Optional
from .base import AIService, ServiceType
from .services.embedding_service import EmbeddingService
from .services.inference_service import InferenceService
from .services.moderation_service import ModerationService
from .services.reranking_service import RerankingService

class AIServiceFactory:
    """Unified factory for all AI services."""
    
    _service_registry: Dict[tuple, Type[AIService]] = {}
    
    @classmethod
    def register_service(cls, service_type: ServiceType, provider: str, service_class: Type[AIService]):
        """Register a service implementation."""
        cls._service_registry[(service_type, provider)] = service_class
    
    @classmethod
    def create_service(cls, service_type: ServiceType, provider: str, config: Dict[str, Any]) -> AIService:
        """Create a service instance."""
        key = (service_type, provider)
        if key not in cls._service_registry:
            raise ValueError(f"No service registered for {service_type.value} with provider {provider}")
        
        service_class = cls._service_registry[key]
        return service_class(config)
```

### Phase 5: Future Extensibility

#### 5.1 Vision Services
```python
# server/ai_services/services/vision_service.py
class VisionService(ProviderAIService):
    """Base class for vision services."""
    
    @abstractmethod
    async def analyze_image(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze an image."""
        pass
    
    @abstractmethod
    async def generate_image(self, prompt: str) -> bytes:
        """Generate an image from a prompt."""
        pass
```

## Benefits of This Architecture

### 1. Reduced Code Duplication
- Common connection, configuration, and error handling logic is centralized
- Provider-specific patterns are shared across all service types
- Configuration parsing is unified and consistent

### 2. Easier Maintenance
- Changes to connection logic only need to be made in one place
- Bug fixes are automatically applied to all services
- New features can be added to the base classes and inherited by all services

### 3. Better Extensibility
- Adding new services (vision, audio) is straightforward
- New providers can be added by implementing the provider base class
- Service-specific functionality is clearly separated from common functionality

### 4. Consistent Patterns
- All services follow the same patterns and interfaces
- Configuration is handled consistently across all services
- Error handling and logging follow the same patterns

### 5. Unified Configuration
- Single configuration system for all AI services
- Consistent environment variable handling
- Centralized configuration validation

### 6. Better Testing
- Easier to mock and test services with common interfaces
- Provider-specific testing can be done at the base class level
- Service-specific testing focuses on business logic

### 7. **Configurable Endpoints** 🎯
- **Easy API Version Updates**: Endpoints are configurable, not hardcoded
- **Environment-Specific Endpoints**: Different endpoints for dev/staging/prod
- **Fallback Support**: Automatic fallback to previous API versions
- **Future-Proof**: Easy to add new endpoints for new service types
- **Provider Flexibility**: Each provider can have its own endpoint structure

## Endpoint Management System

### Key Features

#### 1. **Configurable Endpoints**
```yaml
# Example: OpenAI configuration with configurable endpoints
openai:
  api_key: ${OPENAI_API_KEY}
  base_url: "https://api.openai.com"
  endpoint: "/v1/embeddings"           # Current version
```

#### 2. **Version Management**
```yaml
# API version management - just update the endpoint
openai:
  endpoint: "/v2/embeddings"           # New version
```

#### 3. **Service-Specific Endpoints**
```yaml
# Different endpoints for different service types
embeddings:
  openai:
    endpoint: "/v1/embeddings"

vision:
  openai:
    endpoint: "/v1/chat/completions"

audio:
  openai:
    endpoint: "/v1/audio/transcriptions"
```

### Implementation Benefits

#### 1. **Easy API Updates**
- When OpenAI releases v3 API, just update the endpoint configuration
- No code changes required for endpoint updates
- Simple and straightforward configuration management

#### 2. **Provider Flexibility**
- Each provider can have its own endpoint structure
- Ollama uses `/api/embeddings` while OpenAI uses `/v1/embeddings`
- Easy to support new providers with different endpoint patterns

#### 3. **Future-Proof Architecture**
- Easy to add new service types (vision, audio) with their own endpoints
- New providers can be added with their own endpoint patterns
- Service-specific endpoints can be added without code changes

### Endpoint Resolution Logic

```python
class EndpointManager:
    """Manages endpoint resolution and fallback logic."""
    
    def __init__(self, config: Dict[str, Any], provider: str, service_type: str):
        self.config = config
        self.provider = provider
        self.service_type = service_type
    
    def get_endpoint(self) -> str:
        """Get endpoint for the service."""
        # 1. Try service-specific endpoint
        service_endpoint = self._get_service_endpoint()
        if service_endpoint:
            return service_endpoint
        
        # 2. Try provider-specific endpoint
        provider_endpoint = self._get_provider_endpoint()
        if provider_endpoint:
            return provider_endpoint
        
        # 3. Use default endpoint
        return self._get_default_endpoint()
    
    def _get_service_endpoint(self) -> Optional[str]:
        """Get endpoint from service-specific configuration."""
        service_config = self.config.get(self.service_type, {}).get(self.provider, {})
        return service_config.get('endpoint')
    
    def _get_provider_endpoint(self) -> Optional[str]:
        """Get endpoint from provider-specific configuration."""
        provider_config = self.config.get(self.provider, {})
        return provider_config.get('endpoint')
    
    def _get_default_endpoint(self) -> str:
        """Get default endpoint based on service type."""
        defaults = {
            'embeddings': '/v1/embeddings',
            'inference': '/v1/chat/completions',
            'moderation': '/v1/moderations',
            'reranking': '/v1/rerank',
            'vision': '/v1/chat/completions',
            'audio': '/v1/audio/transcriptions'
        }
        return defaults.get(self.service_type, '/v1/endpoint')
```

## Updated Configuration Structure

### Current Configuration Files
The current configuration is spread across multiple files with inconsistent structures:

- `config/embeddings.yaml` - Embedding service configuration
- `config/inference.yaml` - LLM provider configuration  
- `config/rerankers.yaml` - Reranking service configuration
- `config/moderators.yaml` - Moderation service configuration

### Target Configuration Structure
The new architecture will use a unified configuration approach with configurable endpoints:

#### 1. **Updated `config/embeddings.yaml`**
```yaml
# Global embedding configuration
embedding:
  provider: "ollama"
  enabled: true

# Provider-specific configurations with configurable endpoints
embeddings:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "text-embedding-3-small"
    dimensions: 1536
    batch_size: 10
    base_url: "https://api.openai.com"
    # Configurable endpoint for easy API version updates
    endpoint: "/v1/embeddings"

  ollama:
    base_url: "http://localhost:11434"
    model: "nomic-embed-text"
    dimensions: 768
    # Ollama-specific endpoint
    endpoint: "/api/embeddings"
    # Retry and timeout configuration
    retry:
      enabled: true
      max_retries: 5
      initial_wait_ms: 2000
      max_wait_ms: 30000
      exponential_base: 2
    timeout:
      connect: 10000
      total: 60000
      warmup: 45000

  cohere:
    api_key: ${COHERE_API_KEY}
    model: "embed-english-v3.0"
    input_type: "search_document"
    dimensions: 1024
    batch_size: 32
    truncate: "NONE"
    embedding_types: ["float"]
    base_url: "https://api.cohere.ai"
    endpoint: "/v1/embed"

  mistral:
    api_key: ${MISTRAL_API_KEY}
    base_url: "https://api.mistral.ai"
    model: "mistral-embed"
    dimensions: 1024
    endpoint: "/v1/embeddings"
```

#### 2. **Updated `config/inference.yaml`**
```yaml
inference:
  ollama:
    base_url: "http://localhost:11434"
    model: "granite4:micro"
    stream: true
    # Generation parameters
    temperature: 0.7
    top_p: 0.9
    # ... other parameters
    # Configurable endpoint
    endpoint: "/api/generate"
    # Retry and timeout configuration
    retry:
      enabled: true
      max_retries: 5
      initial_wait_ms: 2000
      max_wait_ms: 30000
      exponential_base: 2
    timeout:
      connect: 10000
      total: 120000
      warmup: 60000

  openai:
    api_key: ${OPENAI_API_KEY}
    model: "gpt-5-nano"
    temperature: 1
    top_p: 0.8
    max_tokens: 16000
    stream: true
    base_url: "https://api.openai.com"
    # Configurable endpoint
    endpoint: "/v1/chat/completions"

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-sonnet-4-20250514"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
    base_url: "https://api.anthropic.com"
    endpoint: "/v1/messages"
```

#### 3. **Updated `config/rerankers.yaml`**
```yaml
rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "xitao/bge-reranker-v2-m3:latest"
    temperature: 0.0
    batch_size: 5
    # Configurable endpoint
    endpoint: "/api/rerank"
    # Retry and timeout configuration
    retry:
      enabled: true
      max_retries: 3
      initial_wait_ms: 1000
      max_wait_ms: 15000
      exponential_base: 2
    timeout:
      connect: 5000
      total: 30000
      warmup: 10000
```

#### 4. **New `config/vision.yaml`**
```yaml
# Vision services configuration
vision:
  provider: "openai"  # Default vision provider
  enabled: false      # Disabled by default

# Provider-specific configurations
visions:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "gpt-4-vision-preview"
    max_tokens: 1000
    base_url: "https://api.openai.com"
    # Vision-specific endpoint
    endpoint: "/v1/chat/completions"
    # Image processing parameters
    image_processing:
      max_size: "1024x1024"
      supported_formats: ["png", "jpg", "jpeg", "gif", "webp"]
      quality: "standard"  # standard, hd
    # Batch processing
    batch_size: 5
    timeout:
      connect: 10000
      total: 60000

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-5-sonnet-20241022"
    max_tokens: 1000
    base_url: "https://api.anthropic.com"
    # Anthropic-specific endpoint
    endpoint: "/v1/messages"
    # Image processing parameters
    image_processing:
      max_size: "2048x2048"
      supported_formats: ["png", "jpg", "jpeg", "gif", "webp"]
    batch_size: 3
    timeout:
      connect: 10000
      total: 60000
```

#### 5. **New `config/audio.yaml`**
```yaml
# Audio services configuration
audio:
  provider: "openai"  # Default audio provider
  enabled: false      # Disabled by default

# Provider-specific configurations
audios:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "whisper-1"
    base_url: "https://api.openai.com"
    # Audio-specific endpoint
    endpoint: "/v1/audio/transcriptions"
    # Audio processing parameters
    audio_processing:
      supported_formats: ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
      max_file_size: "25MB"
      max_duration: "25 minutes"
    # Language support
    languages:
      default: "auto"
      supported: ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh"]
    batch_size: 1
    timeout:
      connect: 10000
      total: 300000  # 5 minutes for audio processing

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-5-sonnet-20241022"
    base_url: "https://api.anthropic.com"
    # Anthropic-specific endpoint (if they add audio support)
    endpoint: "/v1/audio/transcriptions"
    audio_processing:
      supported_formats: ["mp3", "wav", "m4a"]
      max_file_size: "10MB"
      max_duration: "10 minutes"
    batch_size: 1
    timeout:
      connect: 10000
      total: 120000  # 2 minutes
```

## Migration Timeline

### Week 1: Phase 1 - Core Base Abstractions
- Create base AI service infrastructure
- Implement provider-specific base classes
- Set up connection management utilities
- **Create endpoint management system**

### Week 2: Phase 2 - Service-Specific Abstractions
- Create service-specific interfaces
- Implement common service patterns
- Set up service registry system
- **Update configuration files with configurable endpoints**

### Week 3: Phase 3 - Migrate Embeddings and Providers
- Migrate embedding services to new architecture
- Migrate inference providers to new architecture
- Update factories and configuration
- **Implement endpoint resolution logic**

### Week 4: Phase 3 - Migrate Moderators and Rerankers
- Migrate moderation services to new architecture
- Migrate reranking services to new architecture
- Complete migration testing
- **Test endpoint configuration and fallback logic**

### Week 5: Phase 4 - Unified Factory and Configuration
- Implement unified service factory
- Update configuration system
- Add comprehensive testing
- **Create configuration migration tools**

### Week 6: Phase 5 - Add Vision Services and Testing
- Add vision service support
- Add audio service support
- Complete end-to-end testing
- **Test new service types with configurable endpoints**

## Risk Mitigation

### 1. Backward Compatibility
- Maintain existing interfaces during migration
- Use adapter pattern for transition
- Gradual migration with rollback capability

### 2. Testing Strategy
- Comprehensive unit tests for new base classes
- Integration tests for migrated services
- End-to-end tests for complete functionality
- Performance tests to ensure no regression

### 3. Rollback Plan
- Keep old implementations during migration
- Feature flags to switch between old and new implementations
- Database migration scripts for configuration changes
- Documentation for rollback procedures

## Success Metrics

### 1. Code Quality Metrics
- Reduction in code duplication (target: 60% reduction)
- Improved test coverage (target: 90%+)
- Reduced cyclomatic complexity
- Improved maintainability index

### 2. Performance Metrics
- No performance regression in service calls
- Improved service initialization time
- Reduced memory usage through better resource management
- Faster configuration loading

### 3. Developer Experience Metrics
- Reduced time to add new services (target: 50% reduction)
- Reduced time to add new providers (target: 70% reduction)
- Improved documentation coverage
- Reduced onboarding time for new developers

## Conclusion

This refactoring will significantly improve the maintainability, extensibility, and consistency of the AI services architecture. The staged approach ensures minimal disruption to existing functionality while gradually improving the codebase. The new architecture will make it much easier to add new AI services and maintain existing ones, while reducing code duplication and improving overall code quality.

The migration should be completed within 6 weeks, with each phase building upon the previous one. The final result will be a unified, extensible architecture that supports current and future AI service needs while maintaining backward compatibility and high performance.
