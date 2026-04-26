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
    - OllamaRemoteInferenceService: Ollama Remote (self-hosted) inference
    - BitNetInferenceService: BitNet (1.58-bit) inference
    - ZaiInferenceService: Z.AI inference
    - TensorRTInferenceService: TensorRT-LLM (NVIDIA) inference
    - TransformersInferenceService: Transformers (Local) inference
    - CerebrasInferenceService: Cerebras ultra-fast inference
    - DeepInfraInferenceService: DeepInfra hosted open-model inference
    - LMStudioInferenceService: LM Studio local inference
    - MoonshotInferenceService: Moonshot AI (Kimi) inference
    - MiniMaxInferenceService: MiniMax inference
    - NebiusInferenceService: Nebius AI Studio inference
    - VeniceInferenceService: Venice AI privacy-focused inference
    - ScalewayInferenceService: Scaleway European cloud inference
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
    ('ollama_remote_inference_service', 'OllamaRemoteInferenceService'),
    ('bitnet_inference_service', 'BitNetInferenceService'),
    ('zai_inference_service', 'ZaiInferenceService'),
    ('tensorrt_inference_service', 'TensorRTInferenceService'),
    ('transformers_inference_service', 'TransformersInferenceService'),
    ('cerebras_inference_service', 'CerebrasInferenceService'),
    ('deepinfra_inference_service', 'DeepInfraInferenceService'),
    ('lmstudio_inference_service', 'LMStudioInferenceService'),
    ('moonshot_inference_service', 'MoonshotInferenceService'),
    ('minimax_inference_service', 'MiniMaxInferenceService'),
    ('nebius_inference_service', 'NebiusInferenceService'),
    ('venice_inference_service', 'VeniceInferenceService'),
    ('scaleway_inference_service', 'ScalewayInferenceService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.inference.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
