"""
Embedding service implementations.

Available providers:
    - OpenAIEmbeddingService: OpenAI embeddings
    - OllamaEmbeddingService: Ollama embeddings
    - CohereEmbeddingService: Cohere embeddings
    - MistralEmbeddingService: Mistral embeddings
    - JinaEmbeddingService: Jina AI embeddings
    - LlamaCppEmbeddingService: Llama.cpp embeddings
    - SentenceTransformersEmbeddingService: Sentence Transformers embeddings
    - OpenRouterEmbeddingService: OpenRouter embeddings
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('openai_embedding_service', 'OpenAIEmbeddingService'),
    ('ollama_embedding_service', 'OllamaEmbeddingService'),
    ('cohere_embedding_service', 'CohereEmbeddingService'),
    ('mistral_embedding_service', 'MistralEmbeddingService'),
    ('jina_embedding_service', 'JinaEmbeddingService'),
    ('llama_cpp_embedding_service', 'LlamaCppEmbeddingService'),
    ('sentence_transformers_embedding_service', 'SentenceTransformersEmbeddingService'),
    ('openrouter_embedding_service', 'OpenRouterEmbeddingService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.embedding.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
