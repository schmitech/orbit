"""
Inference service implementations.

Available providers:
    - OpenAIInferenceService: OpenAI inference
    - AnthropicInferenceService: Anthropic inference
    - OllamaInferenceService: Ollama inference
    - GroqInferenceService: Groq inference
    - MistralInferenceService: Mistral inference
    - DeepSeekInferenceService: DeepSeek inference
    - FireworksInferenceService: Fireworks inference
    - PerplexityInferenceService: Perplexity inference
    - TogetherInferenceService: Together inference
    - OpenRouterInferenceService: OpenRouter inference
    - XAIInferenceService: xAI (Grok) inference
    - AWSBedrockInferenceService: AWS Bedrock inference
    - AzureOpenAIInferenceService: Azure OpenAI inference
    - VertexAIInferenceService: Vertex AI inference
    - GeminiInferenceService: Gemini inference
    - CohereInferenceService: Cohere inference
    - NVIDIAInferenceService: NVIDIA NIM inference
    - ReplicateInferenceService: Replicate inference
    - WatsonInferenceService: IBM Watson inference
    - VLLMInferenceService: vLLM inference
    - LlamaCppInferenceService: Llama.cpp inference
    - ShimmyInferenceService: Shimmy inference
    - HuggingFaceInferenceService: Hugging Face inference
    - OllamaCloudInferenceService: Ollama Cloud inference
    - BitNetInferenceService: BitNet (1.58-bit) inference
    - ZaiInferenceService: Z.AI inference
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
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
    ('shimmy_inference_service', 'ShimmyInferenceService'),
    ('huggingface_inference_service', 'HuggingFaceInferenceService'),
    ('ollama_cloud_inference_service', 'OllamaCloudInferenceService'),
    ('bitnet_inference_service', 'BitNetInferenceService'),
    ('zai_inference_service', 'ZaiInferenceService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.inference.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
