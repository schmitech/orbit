"""
Embeddings package for text embeddings.
"""

# Remove direct imports, use lazy loading instead
__all__ = [
    'EmbeddingServiceFactory',
    'OpenAIEmbeddings',
    'OllamaEmbeddings',
    'JinaEmbeddings',
    'CohereEmbeddings'
]