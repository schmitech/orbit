"""
Concrete implementations of AI services using the unified architecture.

This package contains service implementations organized by category:
- inference/: LLM inference services (26 providers)
- embedding/: Text embedding services (7 providers)
- vision/: Vision/multimodal services (7 providers)
- audio/: Audio TTS/STT services (10 providers)
- reranking/: Document reranking services (6 providers)
- moderation/: Content moderation services (3 providers)

Services with missing dependencies are skipped gracefully.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

# Import from subpackages
try:
    from .inference import *
    from .inference import __all__ as inference_all
    __all__.extend(inference_all)
except ImportError as e:
    logger.debug(f"Could not import inference implementations: {e}")

try:
    from .embedding import *
    from .embedding import __all__ as embedding_all
    __all__.extend(embedding_all)
except ImportError as e:
    logger.debug(f"Could not import embedding implementations: {e}")

try:
    from .vision import *
    from .vision import __all__ as vision_all
    __all__.extend(vision_all)
except ImportError as e:
    logger.debug(f"Could not import vision implementations: {e}")

try:
    from .audio import *
    from .audio import __all__ as audio_all
    __all__.extend(audio_all)
except ImportError as e:
    logger.debug(f"Could not import audio implementations: {e}")

try:
    from .reranking import *
    from .reranking import __all__ as reranking_all
    __all__.extend(reranking_all)
except ImportError as e:
    logger.debug(f"Could not import reranking implementations: {e}")

try:
    from .moderation import *
    from .moderation import __all__ as moderation_all
    __all__.extend(moderation_all)
except ImportError as e:
    logger.debug(f"Could not import moderation implementations: {e}")

# Map service classes to their required SDK packages for commercial/cloud providers
# Services not in this map don't require validation (they use packages in default dependencies)
_required_packages = {
    # Commercial OpenAI services (require API keys)
    'OpenAIEmbeddingService': 'anthropic',
    'OpenAIInferenceService': 'anthropic',
    'OpenAIModerationService': 'anthropic',

    # Other commercial providers
    'AnthropicInferenceService': 'anthropic',
    'AnthropicModerationService': 'anthropic',
    'CohereEmbeddingService': 'cohere',
    'CohereInferenceService': 'cohere',
    'MistralEmbeddingService': 'mistralai',
    'MistralInferenceService': 'mistralai',
    'GroqInferenceService': 'groq',
    'DeepSeekInferenceService': 'deepseek',
    'TogetherInferenceService': 'together',
    'AWSBedrockInferenceService': 'boto3',
    'AzureOpenAIInferenceService': 'azure.ai.inference',
    'VertexAIInferenceService': 'google.cloud.aiplatform',
    'GeminiInferenceService': 'google.generativeai',
    'ReplicateInferenceService': 'replicate',
    'WatsonInferenceService': 'ibm_watsonx_ai',
    'HuggingFaceInferenceService': 'transformers',
    'ZaiInferenceService': 'zai',

    # Commercial OpenAI-compatible services
    'FireworksInferenceService': 'anthropic',
    'PerplexityInferenceService': 'anthropic',
    'OpenRouterInferenceService': 'anthropic',
    'XAIInferenceService': 'anthropic',

    # Vision services
    'OpenAIVisionService': 'openai',
    'GeminiVisionService': 'google.generativeai',
    'AnthropicVisionService': 'anthropic',
    'CohereVisionService': 'cohere',

    # Audio services
    'OpenAIAudioService': 'openai',
    'GoogleAudioService': 'google.cloud.speech',
    'GeminiAudioService': 'google.genai',
    'AnthropicAudioService': 'anthropic',
    'CohereAudioService': 'cohere',
}
