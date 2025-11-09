"""
Concrete implementations of AI services using the unified architecture.

This package contains migrated and new service implementations that use
the unified AI services architecture. These implementations demonstrate
the benefits of code consolidation and reusability.

Services with missing dependencies are skipped gracefully.

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
    - ZaiInferenceService: Z.AI inference (new)

Available Moderation Services:
    - OpenAIModerationService: OpenAI moderation (migrated)
    - AnthropicModerationService: Anthropic moderation (migrated)
    - OllamaModerationService: Ollama moderation (migrated)

Available Reranking Services:
    - OllamaRerankingService: Ollama reranking (local, free)
    - CohereRerankingService: Cohere Rerank API (excellent quality, multilingual)
    - JinaRerankingService: Jina AI Reranker (fast, good quality)
    - OpenAIRerankingService: OpenAI GPT-based reranking (complex queries)
    - AnthropicRerankingService: Anthropic Claude-based reranking (nuanced)
    - VoyageRerankingService: Voyage AI Reranker (cost-effective)

Available Vision Services:
    - OpenAIVisionService: OpenAI vision (GPT-4o, multimodal)
    - GeminiVisionService: Gemini vision (multimodal, OCR)
    - AnthropicVisionService: Anthropic Claude vision (multimodal analysis)

More implementations will be added as migration progresses.
"""

import logging

logger = logging.getLogger(__name__)

# Lazy import implementations - only import those with installed dependencies
__all__ = []

# Define all implementations to try importing
_implementations = [
    # Embedding Services
    ('openai_embedding_service', 'OpenAIEmbeddingService'),
    ('ollama_embedding_service', 'OllamaEmbeddingService'),
    ('cohere_embedding_service', 'CohereEmbeddingService'),
    ('mistral_embedding_service', 'MistralEmbeddingService'),
    ('jina_embedding_service', 'JinaEmbeddingService'),
    ('llama_cpp_embedding_service', 'LlamaCppEmbeddingService'),
    ('sentence_transformers_embedding_service', 'SentenceTransformersEmbeddingService'),

    # Inference Services
    ('openai_inference_service', 'OpenAIInferenceService'),
    ('anthropic_inference_service', 'AnthropicInferenceService'),
    ('ollama_inference_service', 'OllamaInferenceService'),
    ('groq_inference_service', 'GroqInferenceService'),
    ('mistral_inference_service', 'MistralInferenceService'),
    ('deepseek_inference_service', 'DeepSeekInferenceService'),
    ('fireworks_inference_service', 'FireworksInferenceService'),
    ('perplexity_inference_service', 'PerplexityInferenceService'),
    ('together_inference_service', 'TogetherInferenceService'),
    ('openrouter_inference_service', 'OpenRouterInferenceService'),
    ('xai_inference_service', 'XAIInferenceService'),
    ('aws_bedrock_inference_service', 'AWSBedrockInferenceService'),
    ('azure_openai_inference_service', 'AzureOpenAIInferenceService'),
    ('vertexai_inference_service', 'VertexAIInferenceService'),
    ('gemini_inference_service', 'GeminiInferenceService'),
    ('cohere_inference_service', 'CohereInferenceService'),
    ('nvidia_inference_service', 'NVIDIAInferenceService'),
    ('replicate_inference_service', 'ReplicateInferenceService'),
    ('watson_inference_service', 'WatsonInferenceService'),
    ('vllm_inference_service', 'VLLMInferenceService'),
    ('llama_cpp_inference_service', 'LlamaCppInferenceService'),
    ('huggingface_inference_service', 'HuggingFaceInferenceService'),
    ('ollama_cloud_inference_service', 'OllamaCloudInferenceService'),
    ('bitnet_inference_service', 'BitNetInferenceService'),
    ('zai_inference_service', 'ZaiInferenceService'),

    # Moderation Services
    ('openai_moderation_service', 'OpenAIModerationService'),
    ('anthropic_moderation_service', 'AnthropicModerationService'),
    ('ollama_moderation_service', 'OllamaModerationService'),

    # Reranking Services
    ('ollama_reranking_service', 'OllamaRerankingService'),
    ('cohere_reranking_service', 'CohereRerankingService'),
    ('jina_reranking_service', 'JinaRerankingService'),
    ('openai_reranking_service', 'OpenAIRerankingService'),
    ('anthropic_reranking_service', 'AnthropicRerankingService'),
    ('voyage_reranking_service', 'VoyageRerankingService'),
    
    # Vision Services
    ('openai_vision_service', 'OpenAIVisionService'),
    ('gemini_vision_service', 'GeminiVisionService'),
    ('anthropic_vision_service', 'AnthropicVisionService'),
]

# Map service classes to their required SDK packages for commercial/cloud providers
# Services not in this map don't require validation (they use packages in default dependencies)
# Note: openai SDK is in default dependencies for local OpenAI-compatible servers (vLLM, Ollama Cloud, NVIDIA NIM)
_required_packages = {
    # Commercial OpenAI services (require API keys)
    'OpenAIEmbeddingService': 'anthropic',  # Dummy check - we want to disable commercial OpenAI
    'OpenAIInferenceService': 'anthropic',  # Dummy check - we want to disable commercial OpenAI
    'OpenAIModerationService': 'anthropic',  # Dummy check - we want to disable commercial OpenAI

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

    # Commercial OpenAI-compatible services (require API keys from commercial providers)
    'FireworksInferenceService': 'anthropic',  # Dummy check - commercial service
    'PerplexityInferenceService': 'anthropic',  # Dummy check - commercial service
    'OpenRouterInferenceService': 'anthropic',  # Dummy check - commercial service
    'XAIInferenceService': 'anthropic',  # Dummy check - commercial service

    # Note: VLLMInferenceService, OllamaCloudInferenceService, NVIDIAInferenceService are NOT in this list
    # They use openai SDK (in default dependencies) to connect to local/self-hosted servers
    # Ollama, Llama.cpp, Jina also don't need validation - they use packages in default dependencies
    
    # Vision services
    'OpenAIVisionService': 'openai',
    'GeminiVisionService': 'google.generativeai',
    'AnthropicVisionService': 'anthropic',
}

# Try importing each implementation
for module_name, class_name in _implementations:
    try:
        # First check if the required SDK package is available
        if class_name in _required_packages:
            required_package = _required_packages[class_name]
            try:
                __import__(required_package)
            except ImportError:
                logger.debug(f"Skipping {class_name} - required package '{required_package}' not installed")
                continue

        # Import the service class
        module = __import__(f'ai_services.implementations.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        # Service dependency not installed - skip it
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
