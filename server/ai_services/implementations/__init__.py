"""
Concrete implementations of AI services using the unified architecture.

This package contains migrated and new service implementations that use
the unified AI services architecture. These implementations demonstrate
the benefits of code consolidation and reusability.

Available Embedding Services:
    - OpenAIEmbeddingService: OpenAI embeddings (migrated)
    - OllamaEmbeddingService: Ollama embeddings (migrated)
    - CohereEmbeddingService: Cohere embeddings (migrated)
    - MistralEmbeddingService: Mistral embeddings (migrated)
    - JinaEmbeddingService: Jina AI embeddings (migrated)
    - LlamaCppEmbeddingService: Llama.cpp embeddings (migrated)

Available Inference Services:
    - OpenAIInferenceService: OpenAI inference (migrated)
    - AnthropicInferenceService: Anthropic inference (migrated)
    - OllamaInferenceService: Ollama inference (migrated)
    - GroqInferenceService: Groq inference (migrated)
    - MistralInferenceService: Mistral inference (migrated)
    - DeepSeekInferenceService: DeepSeek inference (migrated)
    - FireworksInferenceService: Fireworks inference (migrated)
    - PerplexityInferenceService: Perplexity inference (migrated)
    - TogetherInferenceService: Together inference (migrated)
    - OpenRouterInferenceService: OpenRouter inference (migrated)
    - XAIInferenceService: xAI (Grok) inference (migrated)
    - AWSBedrockInferenceService: AWS Bedrock inference (migrated)
    - AzureOpenAIInferenceService: Azure OpenAI inference (migrated)
    - VertexAIInferenceService: Vertex AI inference (migrated)
    - GeminiInferenceService: Gemini inference (migrated)
    - CohereInferenceService: Cohere inference (migrated)
    - NVIDIAInferenceService: NVIDIA NIM inference (migrated)
    - ReplicateInferenceService: Replicate inference (migrated)
    - WatsonInferenceService: IBM Watson inference (migrated)
    - VLLMInferenceService: vLLM inference (migrated)
    - LlamaCppInferenceService: Llama.cpp inference (migrated)
    - HuggingFaceInferenceService: Hugging Face inference (migrated)
    - OllamaCloudInferenceService: Ollama Cloud inference (migrated)

Available Moderation Services:
    - OpenAIModerationService: OpenAI moderation (migrated)
    - AnthropicModerationService: Anthropic moderation (migrated)
    - OllamaModerationService: Ollama moderation (migrated)

Available Reranking Services:
    - OllamaRerankingService: Ollama reranking (migrated)

More implementations will be added as migration progresses.
"""

# Embedding Services
from .openai_embedding_service import OpenAIEmbeddingService
from .ollama_embedding_service import OllamaEmbeddingService
from .cohere_embedding_service import CohereEmbeddingService
from .mistral_embedding_service import MistralEmbeddingService
from .jina_embedding_service import JinaEmbeddingService
from .llama_cpp_embedding_service import LlamaCppEmbeddingService

# Inference Services
from .openai_inference_service import OpenAIInferenceService
from .anthropic_inference_service import AnthropicInferenceService
from .ollama_inference_service import OllamaInferenceService
from .groq_inference_service import GroqInferenceService
from .mistral_inference_service import MistralInferenceService
from .deepseek_inference_service import DeepSeekInferenceService
from .fireworks_inference_service import FireworksInferenceService
from .perplexity_inference_service import PerplexityInferenceService
from .together_inference_service import TogetherInferenceService
from .openrouter_inference_service import OpenRouterInferenceService
from .xai_inference_service import XAIInferenceService
from .aws_bedrock_inference_service import AWSBedrockInferenceService
from .azure_openai_inference_service import AzureOpenAIInferenceService
from .vertexai_inference_service import VertexAIInferenceService
from .gemini_inference_service import GeminiInferenceService
from .cohere_inference_service import CohereInferenceService
from .nvidia_inference_service import NVIDIAInferenceService
from .replicate_inference_service import ReplicateInferenceService
from .watson_inference_service import WatsonInferenceService
from .vllm_inference_service import VLLMInferenceService
from .llama_cpp_inference_service import LlamaCppInferenceService
from .huggingface_inference_service import HuggingFaceInferenceService
from .ollama_cloud_inference_service import OllamaCloudInferenceService

# Moderation Services
from .openai_moderation_service import OpenAIModerationService
from .anthropic_moderation_service import AnthropicModerationService
from .ollama_moderation_service import OllamaModerationService

# Reranking Services
from .ollama_reranking_service import OllamaRerankingService

__all__ = [
    # Embedding Services
    'OpenAIEmbeddingService',
    'OllamaEmbeddingService',
    'CohereEmbeddingService',
    'MistralEmbeddingService',
    'JinaEmbeddingService',
    'LlamaCppEmbeddingService',
    # Inference Services
    'OpenAIInferenceService',
    'AnthropicInferenceService',
    'OllamaInferenceService',
    'GroqInferenceService',
    'MistralInferenceService',
    'DeepSeekInferenceService',
    'FireworksInferenceService',
    'PerplexityInferenceService',
    'TogetherInferenceService',
    'OpenRouterInferenceService',
    'XAIInferenceService',
    'AWSBedrockInferenceService',
    'AzureOpenAIInferenceService',
    'VertexAIInferenceService',
    'GeminiInferenceService',
    'CohereInferenceService',
    'NVIDIAInferenceService',
    'ReplicateInferenceService',
    'WatsonInferenceService',
    'VLLMInferenceService',
    'LlamaCppInferenceService',
    'HuggingFaceInferenceService',
    'OllamaCloudInferenceService',
    # Moderation Services
    'OpenAIModerationService',
    'AnthropicModerationService',
    'OllamaModerationService',
    # Reranking Services
    'OllamaRerankingService',
]
