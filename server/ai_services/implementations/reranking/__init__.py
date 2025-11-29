"""
Reranking service implementations.

Available providers:
    - OllamaRerankingService: Ollama reranking (local, free)
    - CohereRerankingService: Cohere Rerank API (excellent quality, multilingual)
    - JinaRerankingService: Jina AI Reranker (fast, good quality)
    - OpenAIRerankingService: OpenAI GPT-based reranking (complex queries)
    - AnthropicRerankingService: Anthropic Claude-based reranking (complex queries)
    - VoyageRerankingService: Voyage AI Reranker (cost-effective)
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('ollama_reranking_service', 'OllamaRerankingService'),
    ('cohere_reranking_service', 'CohereRerankingService'),
    ('jina_reranking_service', 'JinaRerankingService'),
    ('openai_reranking_service', 'OpenAIRerankingService'),
    ('anthropic_reranking_service', 'AnthropicRerankingService'),
    ('voyage_reranking_service', 'VoyageRerankingService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.reranking.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
