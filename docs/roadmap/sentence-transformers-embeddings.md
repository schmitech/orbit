# Add Sentence Transformers Embedding Service

## Overview

Add a new embedding service using the `sentence-transformers` library to support popular open-source embedding models for RAG pipelines. This will enable users to work with high-performance models like BAAI/bge-m3, bge-large-en-v1.5, and all-MiniLM-L6-v2 locally or via Hugging Face API.

## Implementation Strategy

### 1. Create Base Provider Class

**File**: `server/ai_services/providers/sentence_transformers_base.py`

Create a new base class `SentenceTransformersBaseService` that:

- Extends `ProviderAIService`
- Handles model initialization and loading
- Auto-detects GPU availability and uses CUDA if available
- Manages model caching using sentence-transformers defaults
- Supports both local model loading and remote Hugging Face API
- Provides retry logic and connection verification

Key configuration parameters:

- `model`: Model identifier (e.g., "BAAI/bge-m3")
- `device`: Optional device override ("cuda", "cpu", or auto-detect)
- `cache_folder`: Optional cache directory for models
- `normalize_embeddings`: Whether to L2 normalize embeddings
- `mode`: "local" or "remote" (for Hugging Face API)

### 2. Create Embedding Service Implementation

**File**: `server/ai_services/implementations/sentence_transformers_embedding_service.py`

Implement `SentenceTransformersEmbeddingService` that:

- Inherits from both `EmbeddingService` and `SentenceTransformersBaseService`
- Implements `embed_query()` for single text embedding
- Implements `embed_documents()` with batch processing
- Implements `get_dimensions()` to return model dimensionality
- Handles both local model inference and remote API calls
- Respects batch size configuration for efficient processing

Follow the pattern from `ollama_embedding_service.py` (~230 lines):

- Use cooperative initialization from base classes
- Implement retry logic for API calls
- Handle fallback to zero vectors on errors
- Log progress for large batches

### 3. Update Configuration Files

**File**: `config/embeddings.yaml`

Add new section:

```yaml
sentence_transformers:
  mode: "local"  # or "remote" for HF API
  model: "BAAI/bge-m3"
  device: "auto"  # auto-detect GPU, or "cuda"/"cpu"
  cache_folder: null  # Use default ~/.cache/huggingface
  normalize_embeddings: true
  dimensions: 1024  # bge-m3 uses 1024
  batch_size: 32
  # For remote mode only:
  api_key: ${HUGGINGFACE_API_KEY}
  base_url: "https://api-inference.huggingface.co/models"
```

### 4. Update Dependencies

**File**: `install/dependencies.toml`

The `sentence-transformers>=5.1.1` dependency is already in the `torch` profile (line 74), so no changes needed here.

### 5. Register Service in Factory

**File**: `server/ai_services/implementations/__init__.py`

Add to imports list:

- Add `('sentence_transformers_embedding_service', 'SentenceTransformersEmbeddingService')` to `_implementations` list after line 69

Since sentence-transformers is in the torch profile, we don't need to add it to `_required_packages` (it will be available when torch profile is installed).

### 6. Update Provider Exports

**File**: `server/ai_services/providers/__init__.py`

Export the new base class so it can be imported by implementations.

## Key Features

1. **Popular Model Support**: BAAI/bge-m3 (1024d), BAAI/bge-large-en-v1.5 (1024d), all-MiniLM-L6-v2 (384d), and any sentence-transformers compatible model
2. **Dual Mode**: Local inference (models loaded in memory) or remote via Hugging Face Inference API
3. **Smart Device Detection**: Auto-detect and use GPU if available, fallback to CPU
4. **Model Caching**: Automatic download and caching using sentence-transformers/Hugging Face hub defaults
5. **Batch Processing**: Efficient batch embedding with configurable batch sizes
6. **Normalization**: Optional L2 normalization for better similarity search

## Files to Create

1. `server/ai_services/providers/sentence_transformers_base.py` (~150 lines)
2. `server/ai_services/implementations/sentence_transformers_embedding_service.py` (~250 lines)

## Files to Modify

1. `config/embeddings.yaml` - Add sentence_transformers configuration section
2. `server/ai_services/implementations/__init__.py` - Register new service
3. `server/ai_services/providers/__init__.py` - Export base class