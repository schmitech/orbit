"""
Vision service implementations.

Available providers:
    - OpenAIVisionService: OpenAI vision (GPT-5, multimodal)
    - GeminiVisionService: Gemini vision (multimodal, OCR)
    - AnthropicVisionService: Anthropic Claude vision (multimodal analysis)
    - OllamaVisionService: Ollama vision (qwen3-vl, local multimodal)
    - VLLMVisionService: vLLM vision (LLaVA, local multimodal)
    - LlamaCppVisionService: Llama.cpp vision (LLaVA GGUF, local multimodal)
    - CohereVisionService: Cohere vision (command-r-plus, multimodal)
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('openai_vision_service', 'OpenAIVisionService'),
    ('gemini_vision_service', 'GeminiVisionService'),
    ('anthropic_vision_service', 'AnthropicVisionService'),
    ('ollama_vision_service', 'OllamaVisionService'),
    ('vllm_vision_service', 'VLLMVisionService'),
    ('llama_cpp_vision_service', 'LlamaCppVisionService'),
    ('cohere_vision_service', 'CohereVisionService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.vision.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
