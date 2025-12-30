# Configuration Guide

## Overview

ORBIT uses a modular configuration system combining YAML files with environment variables. Configuration is managed by `config_manager.py`, which provides:

- Default configuration values
- Environment variable substitution (`${VAR_NAME}` syntax)
- Configuration validation and secure credential handling
- Import support for splitting configuration into multiple files
- Logging of configuration changes with sensitive value masking

## Configuration Files

The main `config.yaml` imports specialized configuration files:

```yaml
import:
  - "ollama.yaml"          # Ollama-specific inference settings
  - "adapters.yaml"        # Retriever adapter definitions
  - "inference.yaml"       # LLM inference providers
  - "datasources.yaml"     # Database connections
  - "embeddings.yaml"      # Embedding providers
  - "rerankers.yaml"       # Reranking providers
  - "stores.yaml"          # Vector store layer
  - "moderators.yaml"      # Content moderation
  - "guardrails.yaml"      # Safety guardrails
  - "vision.yaml"          # Vision/image processing
  - "tts.yaml"             # Text-to-speech
  - "stt.yaml"             # Speech-to-text
```

## Core Configuration Sections

### General Settings

```yaml
general:
  port: 3000                      # HTTP server port
  https:
    enabled: false                # Enable HTTPS
    port: 3443                    # HTTPS port
    cert_file: "./cert.pem"       # SSL certificate path
    key_file: "./key.pem"         # SSL private key path
  session_id:
    header_name: "X-Session-ID"   # Session ID header name
    required: true                # Whether session ID is required
  inference_provider: "ollama"    # Default AI model provider
```

### Performance Configuration

```yaml
performance:
  workers: 4                          # Number of worker processes
  keep_alive_timeout: 30              # Keep-alive timeout in seconds
  adapter_preload_timeout: 120        # Max time to wait for adapter initialization (seconds)
  thread_pools:
    io_workers: 50                    # I/O-bound task workers
    cpu_workers: 30                   # CPU-bound task workers
    inference_workers: 20             # Model inference workers
    embedding_workers: 15             # Embedding generation workers
    db_workers: 25                    # Database operation workers
```

### Language Detection

```yaml
language_detection:
  enabled: true
  backends:
    - "langdetect"
    - "langid"
    - "pycld2"
  backend_weights:
    langdetect: 1.0
    langid: 1.2
    pycld2: 1.5
  min_confidence: 0.7               # Minimum detection confidence
  min_margin: 0.2                   # Minimum margin between top languages
  prefer_english_for_ascii: true    # Boost English for ASCII text
  enable_stickiness: false          # Keep detected language across messages
  fallback_language: "en"           # Default when detection fails
  backend_timeout: 10.0             # Timeout per backend (seconds)
  
  # Heuristic adjustments
  heuristic_nudges:
    en_boost: 0.2                   # Boost for English in ASCII text
    es_penalty: 0.1                 # Penalty for Spanish in pure ASCII
    script_boost: 0.2               # Boost when script matches ensemble winner
  
  # Mixed language detection
  mixed_language_threshold: 0.3     # Min confidence for secondary language
  
  # Chat history language prior
  use_chat_history_prior: true
  chat_history_prior_weight: 0.3
  chat_history_messages_count: 5
  
  # RAG retrieval language boosting
  retrieval_match_boost: 0.1        # Boost for matching language docs
  retrieval_mismatch_penalty: 0.05  # Penalty for non-matching docs
  retrieval_min_confidence: 0.7
```

### Fault Tolerance

```yaml
fault_tolerance:
  circuit_breaker:
    failure_threshold: 5              # Failures before circuit opens
    recovery_timeout: 30              # Seconds before attempting recovery
    success_threshold: 3              # Successes to close circuit
    timeout: 30                       # Operation timeout
    max_recovery_timeout: 300.0       # Maximum recovery timeout
    enable_exponential_backoff: true  # Enable exponential backoff
  execution:
    strategy: "all"                   # "all", "first_success", "best_effort"
    timeout: 35                       # Execution timeout
    max_retries: 3                    # Maximum retry attempts
    retry_delay: 1                    # Delay between retries
```

### Authentication

```yaml
auth:
  session_duration_hours: 12
  default_admin_username: admin
  default_admin_password: ${ORBIT_DEFAULT_ADMIN_PASSWORD}
  pbkdf2_iterations: 600000
  # Credential storage: "keyring" (system keychain) or "file" (~/.orbit/.env)
  credential_storage: file
```

### API Key Management

```yaml
api_keys:
  header_name: "X-API-Key"     # HTTP header for API key
  prefix: "orbit_"             # Prefix for generated keys
```

### Clock Service

```yaml
clock_service:
  enabled: true
  default_timezone: "America/Toronto"
  format: "%A, %B %d, %Y at %I:%M:%S %p %Z"
```

### Prompt Service

```yaml
prompt_service:
  cache:
    ttl_seconds: 3600          # How long to cache prompts in Redis
```

### Messages

```yaml
messages:
  no_results_response: "I'm sorry, but I don't have any specific information about that topic in my knowledge base."
  collection_not_found: "I couldn't find the requested collection. Please make sure the collection exists before querying it."
```

### Logging

```yaml
logging:
  level: "INFO"                      # DEBUG, INFO, WARNING, ERROR
  handlers:
    file:
      enabled: true
      directory: "logs"
      filename: "orbit.log"
      max_size_mb: 10
      backup_count: 30
      rotation: "midnight"           # midnight, hourly, daily
      format: "text"                 # text, json
    console:
      enabled: false
      format: "text"
  capture_warnings: true
  propagate: false
  loggers:
    # Suppress specific loggers
    py.warnings:
      level: "ERROR"
      propagate: false
      disabled: true
    uvicorn:
      level: "WARNING"
      propagate: false
    httpx:
      level: "WARNING"
    # Add more loggers as needed
```

### Chat History

```yaml
chat_history:
  enabled: true
  collection_name: "chat_history"
  store_metadata: true
  retention_days: 90
  max_tracked_sessions: 10000
  session:
    auto_generate: false
    required: true
    header_name: "X-Session-ID"
  user:
    header_name: "X-User-ID"
    required: false
```

### Conversation Threading

```yaml
conversation_threading:
  enabled: true
  dataset_ttl_hours: 24              # TTL for stored datasets
  storage_backend: "sqlite"          # redis, sqlite, mongodb
  redis_key_prefix: "thread_dataset:"
```

### Monitoring

```yaml
monitoring:
  enabled: true
  metrics:
    collection_interval: 5           # Seconds between metric collections
    time_window: 300                 # Seconds of historical data (5 min)
    prometheus:
      enabled: true                  # Enable /metrics endpoint
    dashboard:
      enabled: true                  # Enable /dashboard web UI
      websocket_update_interval: 5   # WebSocket update frequency
  alerts:
    cpu_threshold: 90
    memory_threshold: 85
    error_rate_threshold: 5
    response_time_threshold: 5000
```

## Internal Services

### Backend Database

```yaml
internal_services:
  backend:
    type: "sqlite"                   # sqlite or mongodb
    sqlite:
      database_path: "orbit.db"      # SQLite file path
```

### Audit Trail

```yaml
internal_services:
  audit:
    enabled: true
    storage_backend: "database"      # elasticsearch, sqlite, mongodb, database
    collection_name: "audit_logs"
    compress_responses: false        # Gzip compression for response field
    clear_on_startup: true           # WARNING: Deletes all logs on startup
```

### MongoDB

```yaml
internal_services:
  mongodb:
    host: ${INTERNAL_SERVICES_MONGODB_HOST}
    port: ${INTERNAL_SERVICES_MONGODB_PORT}
    username: ${INTERNAL_SERVICES_MONGODB_USERNAME}
    password: ${INTERNAL_SERVICES_MONGODB_PASSWORD}
    database: ${INTERNAL_SERVICES_MONGODB_DB}
    users_collection: users
    sessions_collection: sessions
    apikey_collection: api_keys
    prompts_collection: system_prompts
```

### Redis

```yaml
internal_services:
  redis:
    enabled: true
    host: ${INTERNAL_SERVICES_REDIS_HOST}
    port: ${INTERNAL_SERVICES_REDIS_PORT}
    db: 0
    username: ${INTERNAL_SERVICES_REDIS_USERNAME}
    password: ${INTERNAL_SERVICES_REDIS_PASSWORD}
    use_ssl: false
    ttl: 3600                        # 1 hour
```

### Elasticsearch

```yaml
internal_services:
  elasticsearch:
    enabled: false
    node: ${INTERNAL_SERVICES_ELASTICSEARCH_NODE}
    index: 'orbit'
    username: ${INTERNAL_SERVICES_ELASTICSEARCH_USERNAME}
    password: ${INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD}
```

## File Processing Configuration

```yaml
files:
  # Default storage settings
  storage_root: "./uploads"
  
  # Default chunking settings
  default_chunking_strategy: "recursive"   # fixed, semantic, token, recursive
  default_chunk_size: 2048
  default_chunk_overlap: 200
  
  # Processor configuration
  processing:
    docling_enabled: true              # Enable Docling document processor
    markitdown_enabled: true           # Enable MarkItDown processor
    processor_priority: "docling"      # docling, markitdown, native
    
    markitdown:
      enable_plugins: false            # Third-party plugins (security)
    
    csv:
      full_data_row_threshold: 200     # Include all rows below this threshold
      max_preview_rows: 5
      max_column_width: 50
      max_columns_full: 15
    
    json:
      full_data_item_threshold: 200
      max_array_preview_items: 3
      max_schema_depth: 4
      max_string_length: 100
      max_object_keys: 20
  
  # Tokenizer configuration
  tokenizer: null                      # character, gpt2, tiktoken
  use_tokens: false
  
  # Strategy-specific options
  chunking_options:
    model_name: null                   # Sentence-transformer model
    use_advanced: false                # Advanced semantic chunking
    chunk_size_tokens: null
    min_characters_per_chunk: 24
    threshold: 0.8                     # Similarity threshold
    similarity_window: 3
    min_sentences_per_chunk: 1
    min_characters_per_sentence: 24
  
  # Vector store defaults
  default_vector_store: "chroma"
  default_collection_prefix: "files_"
```

## Security Configuration

### CORS

```yaml
security:
  cors:
    allowed_origins: ["*"]             # Use specific origins in production
    allow_credentials: false           # Cannot be true with wildcard origins
    allowed_methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
    allowed_headers:
      - "Authorization"
      - "Content-Type"
      - "X-API-Key"
      - "X-Session-ID"
      - "X-User-ID"
      - "X-Request-ID"
    expose_headers:
      - "X-Request-ID"
      - "X-RateLimit-Limit"
      - "X-RateLimit-Remaining"
      - "X-RateLimit-Reset"
    max_age: 600                       # Preflight cache duration
```

### Security Headers

```yaml
security:
  headers:
    enabled: true
    content_security_policy: "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; ..."
    strict_transport_security: "max-age=31536000; includeSubDomains"
    x_content_type_options: "nosniff"
    x_frame_options: "SAMEORIGIN"
    x_xss_protection: "1; mode=block"
    referrer_policy: "strict-origin-when-cross-origin"
    permissions_policy: "geolocation=(), microphone=(), camera=()"
```

### Rate Limiting

```yaml
security:
  rate_limiting:
    enabled: true                      # Requires Redis
    trust_proxy_headers: false         # Only enable behind trusted proxy
    trusted_proxies: []                # List of trusted proxy IPs/CIDRs
    
    ip_limits:
      requests_per_minute: 60
      requests_per_hour: 1000
    
    api_key_limits:
      requests_per_minute: 120
      requests_per_hour: 5000
    
    exclude_paths:
      - "/health"
      - "/favicon.ico"
      - "/metrics"
      - "/static"
    
    retry_after_seconds: 60
```

### Throttling

```yaml
security:
  throttling:
    enabled: true
    
    default_quotas:
      daily_limit: 10000
      monthly_limit: 100000
    
    delay:
      min_ms: 100
      max_ms: 5000
      curve: "exponential"             # linear or exponential
      threshold_percent: 70            # Start throttling at 70% quota
    
    priority_multipliers:
      1: 0.5                           # Premium: half delay
      5: 1.0                           # Standard: normal delay
      10: 2.0                          # Low priority: double delay
    
    redis_key_prefix: "quota:"
    usage_sync_interval_seconds: 60
```

### Request Limits & Error Handling

```yaml
security:
  request_limits:
    max_body_size_mb: 10
  
  error_handling:
    expose_details: true               # Set false in production
```

## Vector Stores Configuration (stores.yaml)

The unified store layer manages vector databases:

```yaml
store_manager:
  enabled: true
  cleanup_interval: 300              # 5 minutes
  ephemeral_max_age: 3600            # 1 hour
  auto_cleanup: true

vector_stores:
  chroma:
    enabled: true
    connection_params:
      persist_directory: "./chroma_db"
      distance_function: "cosine"    # cosine, l2, ip
      allow_reset: false
    pool_size: 5
    timeout: 30
    cache_ttl: 1800
    ephemeral: false
    auto_cleanup: true
  
  qdrant:
    enabled: true
    connection_params:
      url: "${DATASOURCE_QDRANT_URL:-}"           # For Qdrant Cloud
      host: "${DATASOURCE_QDRANT_HOST:-localhost}" # For self-hosted
      port: "${DATASOURCE_QDRANT_PORT:-6333}"
      api_key: "${DATASOURCE_QDRANT_API_KEY:-}"
      prefer_grpc: false
      https: false
    cache_ttl: 1800
  
  pinecone:
    enabled: false
    connection_params:
      api_key: "${DATASOURCE_PINECONE_API_KEY}"
      namespace: ""
      index_name: "orbit-index"
    timeout: 30
    cache_ttl: 1800
  
  weaviate:
    enabled: false
    connection_params:
      url: "${DATASOURCE_WEAVIATE_URL}"
      api_key: "${DATASOURCE_WEAVIATE_API_KEY}"
    pool_size: 5
    timeout: 30
  
  milvus:
    enabled: false
    connection_params:
      uri: "./milvus.db"
    pool_size: 5
    timeout: 30
  
  pgvector:
    enabled: false
    connection_params:
      connection_string: "${DATASOURCE_PGVECTOR_CONNECTION_STRING}"
    pool_size: 5
    timeout: 30
    cache_ttl: 1800
  
  faiss:
    enabled: false
    connection_params:
      persist_directory: "./faiss_db"
    pool_size: 5
    timeout: 30
  
  marqo:
    enabled: false
    connection_params:
      url: "http://localhost:8882"
      model: "hf/all_datasets_v4_MiniLM-L6"
    pool_size: 5
    timeout: 30
```

## Adapters Configuration (adapters.yaml)

Adapters are organized by category and imported from separate files:

```yaml
adapters: []

import:
  - "adapters/passthrough.yaml"
  - "adapters/multimodal.yaml"
  - "adapters/qa.yaml"
  - "adapters/intent.yaml"
```

### Capability-Based Architecture

Each adapter can declare explicit capabilities:

```yaml
capabilities:
  retrieval_behavior: "always"         # none, always, conditional
  formatting_style: "standard"         # standard, clean, custom
  supports_file_ids: false             # Accept file_ids for filtering
  supports_session_tracking: false     # Track session_id
  supports_threading: true             # Conversation threading support
  requires_api_key_validation: true    # Validate API key access
  skip_when_no_files: true             # Skip retrieval when no file_ids
  optional_parameters: ["param1"]      # Additional context parameters
```

### Provider Overrides

Each adapter can override global providers:

```yaml
adapters:
  - name: "my-adapter"
    inference_provider: "anthropic"    # Override LLM provider
    model: "claude-sonnet-4-20250514"  # Override model
    embedding_provider: "openai"       # Override embedding provider
    reranker_provider: "cohere"        # Override reranker
```

### Adapter Example with Fault Tolerance

```yaml
adapters:
  - name: "qa-sql"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"
    database: "examples/sqlite/qa.db"  # Override datasource database
    
    config:
      confidence_threshold: 0.3
      max_results: 5
      return_results: 3
      table: "city"
      allowed_columns: ["id", "question", "answer", "category"]
      security_filter: "active = 1"
      cache_ttl: 1800
    
    fault_tolerance:
      operation_timeout: 15.0
      failure_threshold: 10
      recovery_timeout: 30.0
      success_threshold: 5
      max_recovery_timeout: 120.0
      enable_exponential_backoff: true
      enable_thread_isolation: false
      max_retries: 3
      retry_delay: 0.5
      cleanup_interval: 3600.0
      retention_period: 86400.0
      event_handler:
        type: "default"
```

## Inference Providers (inference.yaml)

ORBIT supports many LLM providers:

| Provider | Key Features |
|:---|:---|
| **ollama** | Local/remote Ollama server |
| **openai** | GPT-5.2, GPT-4.1, o3/o4-mini |
| **anthropic** | Claude models |
| **gemini** | Google Gemini |
| **vertex** | Google Cloud Vertex AI |
| **aws** | AWS Bedrock |
| **azure** | Azure OpenAI |
| **groq** | Fast inference |
| **deepseek** | DeepSeek models |
| **mistral** | Mistral AI |
| **cohere** | Command models |
| **together** | Together AI |
| **xai** | Grok models |
| **openrouter** | Multi-provider routing |
| **watson** | IBM watsonx |
| **huggingface** | Local HuggingFace models |
| **llama_cpp** | Local GGUF models |
| **vllm** | vLLM serving |

```yaml
inference:
  ollama:
    base_url: "http://localhost:11434"
    model: "gemma3:12b"
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    repeat_penalty: 1.1
    num_predict: 1024
    num_ctx: 8192
    stream: true
  
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "gpt-5.2"                   # Also: gpt-4.1, o3, o4-mini
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
  
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    api_base: "https://api.anthropic.com/v1"
    model: "claude-sonnet-4-20250514"
    temperature: 0.1
    max_tokens: 1024
    stream: true
```

## Embeddings Configuration (embeddings.yaml)

```yaml
embeddings:
  ollama:
    base_url: "http://localhost:11434"
    model: "nomic-embed-text"
    dimensions: 768
  
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "text-embedding-3-large"
    dimensions: 3072
    batch_size: 10
  
  jina:
    api_key: ${JINA_API_KEY}
    base_url: "https://api.jina.ai/v1"
    model: "jina-embeddings-v3"
    task: "text-matching"
    dimensions: 1024
    batch_size: 10
  
  cohere:
    api_key: ${COHERE_API_KEY}
    model: "embed-english-v3.0"
    input_type: "search_document"
    dimensions: 1024
    batch_size: 32
  
  mistral:
    api_key: ${MISTRAL_API_KEY}
    api_base: "https://api.mistral.ai/v1"
    model: "mistral-embed"
    dimensions: 1024
  
  llama_cpp:
    model_path: "gguf/nomic-embed-text-v1.5-Q4_0.gguf"
    n_ctx: 1024
    n_threads: 4
    n_gpu_layers: 0
    batch_size: 8
    dimensions: 768
```

## Vision Configuration (vision.yaml)

```yaml
vision:
  provider: "gemini"                   # Default: openai, gemini, anthropic
  enabled: true

visions:
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    model: "gpt-5.2"                   # Vision-capable model
    temperature: 0.0
    max_tokens: 1000
    timeout:
      connect: 15000
      total: 90000
    retry:
      enabled: true
      max_retries: 3
  
  gemini:
    enabled: true
    api_key: ${GOOGLE_API_KEY}
    model: "gemini-2.5-flash"
    transport: "rest"                  # Avoid gRPC warnings
  
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-5-sonnet-20241022"
  
  ollama:
    enabled: false
    base_url: "http://localhost:11434"
    model: "qwen3-vl:8b"
  
  cohere:
    enabled: true
    api_key: ${COHERE_API_KEY}
    model: "c4ai-aya-vision-32b"
```

## Text-to-Speech Configuration (tts.yaml)

```yaml
tts:
  provider: "openai"                   # Default TTS provider
  enabled: true

tts_providers:
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    tts_model: "gpt-4o-mini-tts"
    tts_voice: "coral"                 # alloy, ash, ballad, coral, echo, fable, onyx, nova, sage, shimmer, verse
    tts_format: "mp3"                  # mp3, opus, aac, flac
  
  google:
    enabled: true
    api_key: ${GOOGLE_API_KEY}
    tts_model: "neural2"
    tts_voice: "en-US-Neural2-A"
    tts_language_code: "en-US"
  
  gemini:
    enabled: true
    api_key: ${GOOGLE_API_KEY}
    tts_model: "gemini-2.5-pro-preview-tts"
    tts_voice: "Kore"                  # 30 voice options available
  
  elevenlabs:
    enabled: true
    api_key: ${ELEVENLABS_API_KEY}
    tts_model: "eleven_multilingual_v2"
    tts_voice: "5opxviIE64D8KxYYJKpx"
    tts_stability: 0.5
    tts_similarity_boost: 0.75
  
  coqui:
    enabled: false                     # Local, open-source TTS
    tts_model: "tts_models/en/ljspeech/tacotron2-DDC"
    vocoder_model: "vocoder_models/en/ljspeech/hifigan_v2"
    device: "auto"                     # auto, cpu, cuda
```

## Speech-to-Text Configuration (stt.yaml)

```yaml
stt:
  provider: "openai"                   # Default STT provider
  enabled: true

stt_providers:
  whisper:
    enabled: false                     # Local Whisper (free, no API costs)
    model_size: "base"                 # tiny, base, small, medium, large-v3
    device: "auto"                     # auto, cpu, cuda
    language: null                     # null for auto-detect
    task: "transcribe"                 # transcribe, translate
  
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    stt_model: "whisper-1"
  
  google:
    enabled: true
    api_key: ${GOOGLE_API_KEY}
    stt_model: "latest_long"
    stt_language_code: "en-US"
  
  gemini:
    enabled: true
    api_key: ${GOOGLE_API_KEY}
    stt_model: "gemini-2.5-pro"
    transport: "rest"
```

## Safety & Guardrails (guardrails.yaml)

```yaml
safety:
  enabled: false
  mode: "fuzzy"
  moderator: "openai"
  max_retries: 3
  retry_delay: 1.0
  request_timeout: 10
  allow_on_timeout: false
  disable_on_fallback: true            # Disable if no moderators available
```

## Rerankers Configuration (rerankers.yaml)

```yaml
reranker:
  provider: "ollama"
  enabled: false

rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "xitao/bge-reranker-v2-m3:latest"
    temperature: 0.0
    batch_size: 5
```

## Moderators Configuration (moderators.yaml)

```yaml
moderators:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "omni-moderation-latest"
  
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-haiku-20240307"
    temperature: 0.0
    max_tokens: 10
    batch_size: 5
  
  ollama:
    base_url: "http://localhost:11434"
    model: "llama-guard3:1b"
    temperature: 0.0
    batch_size: 1
```

## Data Sources Configuration (datasources.yaml)

```yaml
datasources:
  chroma:
    use_local: true
    db_path: "examples/chroma/chroma_db"
    host: "localhost"
    port: 8000
  
  sqlite:
    database: "examples/sqlite/sqlite_db"
  
  postgres:
    host: ${DATASOURCE_POSTGRES_HOST}
    port: ${DATASOURCE_POSTGRES_PORT}
    database: ${DATASOURCE_POSTGRES_DATABASE}
    username: ${DATASOURCE_POSTGRES_USERNAME}
    password: ${DATASOURCE_POSTGRES_PASSWORD}
    sslmode: ${DATASOURCE_POSTGRES_SSL_MODE}
  
  qdrant:
    host: ${DATASOURCE_QDRANT_HOST}
    port: ${DATASOURCE_QDRANT_PORT}
    timeout: 5
    prefer_grpc: false
    https: false
  
  mongodb:
    host: "localhost"
    port: 27017
    database: "orbit"
    username: ${DATASOURCE_MONGODB_USERNAME}
    password: ${DATASOURCE_MONGODB_PASSWORD}
  
  elasticsearch:
    node: 'https://localhost:9200'
    auth:
      username: ${DATASOURCE_ELASTICSEARCH_USERNAME}
      password: ${DATASOURCE_ELASTICSEARCH_PASSWORD}
      vector_field: "embedding"
      text_field: "content"
      verify_certs: true
  
  redis:
    host: ${DATASOURCE_REDIS_HOST}
    port: ${DATASOURCE_REDIS_PORT}
    password: ${DATASOURCE_REDIS_PASSWORD}
    db: 0
    use_ssl: false
    distance_metric: "COSINE"          # L2, IP, COSINE
```

## Environment Variables

### API Keys

| Variable | Description |
|:---|:---|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_API_KEY` | Google API key (Gemini) |
| `MISTRAL_API_KEY` | Mistral API key |
| `COHERE_API_KEY` | Cohere API key |
| `JINA_API_KEY` | Jina API key |
| `GROQ_API_KEY` | Groq API key |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `TOGETHER_API_KEY` | Together API key |
| `XAI_API_KEY` | XAI/Grok API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `WATSON_API_KEY` | IBM Watson API key |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `FIRECRAWL_API_KEY` | Firecrawl API key |

### Cloud Services

| Variable | Description |
|:---|:---|
| `GOOGLE_CLOUD_PROJECT` | Google Cloud project ID |
| `AWS_BEDROCK_ACCESS_KEY` | AWS Bedrock access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret access key |
| `AZURE_ACCESS_KEY` | Azure API key |

### Internal Services

| Variable | Description |
|:---|:---|
| `INTERNAL_SERVICES_MONGODB_HOST` | MongoDB host |
| `INTERNAL_SERVICES_MONGODB_PORT` | MongoDB port |
| `INTERNAL_SERVICES_MONGODB_USERNAME` | MongoDB username |
| `INTERNAL_SERVICES_MONGODB_PASSWORD` | MongoDB password |
| `INTERNAL_SERVICES_MONGODB_DB` | MongoDB database name |
| `INTERNAL_SERVICES_REDIS_HOST` | Redis host |
| `INTERNAL_SERVICES_REDIS_PORT` | Redis port |
| `INTERNAL_SERVICES_REDIS_USERNAME` | Redis username |
| `INTERNAL_SERVICES_REDIS_PASSWORD` | Redis password |
| `INTERNAL_SERVICES_ELASTICSEARCH_NODE` | Elasticsearch node URL |
| `INTERNAL_SERVICES_ELASTICSEARCH_USERNAME` | Elasticsearch username |
| `INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD` | Elasticsearch password |

### Data Sources

| Variable | Description |
|:---|:---|
| `DATASOURCE_POSTGRES_HOST` | PostgreSQL host |
| `DATASOURCE_POSTGRES_PORT` | PostgreSQL port |
| `DATASOURCE_POSTGRES_DATABASE` | PostgreSQL database |
| `DATASOURCE_POSTGRES_USERNAME` | PostgreSQL username |
| `DATASOURCE_POSTGRES_PASSWORD` | PostgreSQL password |
| `DATASOURCE_POSTGRES_SSL_MODE` | PostgreSQL SSL mode |
| `DATASOURCE_QDRANT_HOST` | Qdrant host |
| `DATASOURCE_QDRANT_PORT` | Qdrant port |
| `DATASOURCE_QDRANT_URL` | Qdrant Cloud URL |
| `DATASOURCE_QDRANT_API_KEY` | Qdrant API key |
| `DATASOURCE_PINECONE_API_KEY` | Pinecone API key |
| `DATASOURCE_PINECONE_HOST` | Pinecone host URL |
| `DATASOURCE_WEAVIATE_URL` | Weaviate URL |
| `DATASOURCE_WEAVIATE_API_KEY` | Weaviate API key |
| `DATASOURCE_PGVECTOR_CONNECTION_STRING` | PGVector connection string |
| `DATASOURCE_MONGODB_USERNAME` | MongoDB username (datasource) |
| `DATASOURCE_MONGODB_PASSWORD` | MongoDB password (datasource) |
| `DATASOURCE_ELASTICSEARCH_USERNAME` | Elasticsearch username |
| `DATASOURCE_ELASTICSEARCH_PASSWORD` | Elasticsearch password |
| `DATASOURCE_REDIS_HOST` | Redis host |
| `DATASOURCE_REDIS_PORT` | Redis port |
| `DATASOURCE_REDIS_PASSWORD` | Redis password |

### Authentication

| Variable | Description |
|:---|:---|
| `ORBIT_DEFAULT_ADMIN_PASSWORD` | Default admin password |

## Best Practices

### Security
- Use environment variables for all credentials
- Enable HTTPS in production
- Configure specific CORS origins (not `*`)
- Set `expose_details: false` in production error handling
- Enable rate limiting with Redis

### Performance
- Configure appropriate thread pool sizes
- Set reasonable timeouts for external services
- Enable caching where supported
- Use connection pooling for databases

### Fault Tolerance
- Configure circuit breakers for external services
- Set appropriate retry limits and delays
- Enable exponential backoff for network operations
- Use thread isolation for network-bound operations

### Logging
- Use `INFO` level in production
- Enable file logging with rotation
- Suppress noisy third-party loggers
- Use JSON format for log aggregation systems

## Troubleshooting

| Issue | Solution |
|:---|:---|
| Configuration not found | Check file paths and permissions |
| Environment variable not resolved | Verify variable is set and uses `${VAR}` syntax |
| HTTPS not working | Verify certificate paths and permissions |
| Rate limiting not working | Ensure Redis is enabled and connected |
| Adapter initialization timeout | Increase `adapter_preload_timeout` in performance section |
| Vector store connection failed | Check store configuration in `stores.yaml` |
