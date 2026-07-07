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
  - "llama_cpp.yaml"       # llama.cpp local model settings
  - "adapters.yaml"        # Retriever adapter definitions
  - "inference.yaml"       # LLM inference providers
  - "datasources.yaml"     # Database connections
  - "embeddings.yaml"      # Embedding providers
  - "rerankers.yaml"       # Reranking providers
  - "stores.yaml"          # Vector store layer
  - "moderators.yaml"      # Content moderation
  - "guardrails.yaml"      # Safety guardrails
  - "vision.yaml"          # Vision/image processing
  - "ocr.yaml"             # AI/LLM-based document OCR
  - "image.yaml"           # Image generation
  - "video.yaml"           # Video generation
  - "document.yaml"        # Document processing
  - "tts.yaml"             # Text-to-speech
  - "stt.yaml"             # Speech-to-text
  - "mcp_client.yaml"      # MCP client integration
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
    key_password: ${ORBIT_TLS_KEY_PASSWORD}  # Optional passphrase for encrypted private key
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

  # GZip compression for responses (opt-in)
  # Compresses responses larger than minimum_size bytes.
  # Streaming endpoints are automatically excluded to preserve word-by-word streaming.
  compression:
    enabled: false                    # Enable for bandwidth optimization
    minimum_size: 2048                # Minimum response size in bytes to compress
    excluded_paths:                   # Paths excluded from compression
      - "/v1/chat"                    # SSE streaming endpoint
      - "/ws"                         # WebSocket endpoints
      - "/mcp"                        # MCP protocol endpoints

  # ETag caching for GET requests (opt-in)
  # Returns 304 Not Modified for unchanged responses.
  # Recommended for read-heavy REST API deployments.
  etag_caching:
    enabled: false                    # Enable if clients implement ETag caching
    excluded_paths:
      - "/v1/chat"
      - "/ws"
      - "/mcp"

  thread_pools:
    # Total pool capacity is per worker. Defaults: 140 threads per worker,
    # or up to 560 threads when workers is 4.
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
    failure_threshold: 5              # Consecutive failures before circuit opens
    recovery_timeout: 30              # Base recovery wait in seconds (exponential backoff applied)
    success_threshold: 3              # Consecutive successes in HALF_OPEN before closing
    max_recovery_timeout: 300.0       # Backoff ceiling in seconds
    enable_exponential_backoff: true  # Enable exponential backoff
    max_half_open_calls: 1            # Max concurrent probes allowed while HALF_OPEN
  execution:
    strategy: "all"                   # Only "all" is currently implemented; first_success/best_effort are planned
    timeout: 35                       # Total operation timeout per adapter call (30% init, 70% query)
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
  # Credential storage: "keyring" (system keychain, default) or "file" (~/.orbit/.env)
  credential_storage: keyring
```

#### External Identity Providers (OIDC / OAuth2)

Optional integration with Microsoft Entra ID (Azure AD) and Auth0. The built-in username/password auth above always works. When enabled, ORBIT validates access-token JWTs presented as `Authorization: Bearer <jwt>` by clients that have already completed the OAuth login. Requires the `auth-providers` dependency profile (`PyJWT[crypto]`).

```yaml
auth:
  providers:
    enabled: false                    # Master switch for external-provider bearer-token validation
    default_role: "user"              # Role assigned to users provisioned on first login
    # Microsoft Entra ID (Azure AD)
    entra:
      enabled: false
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID:-}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID:-}          # Expected token audience
      client_secret: ${ORBIT_AUTH_ENTRA_CLIENT_SECRET:-}  # Optional; only for admin-panel SSO confidential clients
    # Auth0
    auth0:
      enabled: false
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN:-}                # e.g. your-tenant.us.auth0.com
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE:-}            # API identifier = expected token audience
      client_id: ${ORBIT_AUTH_AUTH0_CLIENT_ID:-}          # Required for admin-panel SSO
      client_secret: ${ORBIT_AUTH_AUTH0_CLIENT_SECRET:-}  # Optional; only for admin-panel SSO confidential clients

    # Admin-panel browser SSO (server-side OAuth Authorization Code + PKCE).
    # Lets admins sign in to /admin with Entra/Auth0 instead of a password.
    # Register this redirect URI with each provider:
    #   {base_url or auto-detected}/admin/auth/{entra|auth0}/callback
    admin_sso:
      enabled: false
      base_url: ${ORBIT_ADMIN_BASE_URL:-}  # Optional; overrides auto-detected redirect base (needed behind a proxy)
      admin_users: []                      # Emails and/or "provider:subject" granted admin at login
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
    ttl_seconds: 3600          # How long to cache prompts (1 hour)
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
  dataset_ttl_hours: 24              # Global default TTL for stored datasets
  # "cache" uses the configured cache provider (internal_services.cache.provider).
  # sqlite/mongodb/postgres store thread datasets directly in the application
  # database instead of the cache. Fallback order when using the cache: cache -> database.
  storage_backend: "sqlite"          # cache, sqlite, mongodb, postgres
  cache_key_prefix: "thread_dataset:"
```

### Autocomplete

Query suggestions based on intent template `nl_examples`:

```yaml
autocomplete:
  enabled: true                      # Master switch - when false, /v1/autocomplete returns empty results

  # Query matching settings
  min_query_length: 3                # Minimum characters before fetching suggestions
  max_suggestions: 10                # Server-side ceiling; endpoint and UI request smaller values within this cap

  # Caching configuration
  cache:
    # Use the configured cache provider (internal_services.cache.provider) for
    # distributed caching, recommended for multi-instance deployments.
    # Falls back to in-memory cache if the cache service is unavailable.
    use_cache: false
    ttl_seconds: 1800                # 30 minutes - templates rarely change
    cache_key_prefix: "autocomplete:"

  # Fuzzy matching configuration
  fuzzy_matching:
    enabled: true                    # Enable fuzzy/approximate string matching
    # Algorithm options:
    # - substring: Exact substring matching (fastest, no typo tolerance)
    # - levenshtein: Edit distance (handles typos, moderate speed)
    # - jaro_winkler: Optimized for short strings and prefixes (good for typos)
    algorithm: "jaro_winkler"
    # Minimum similarity score (0.0-1.0) to include a suggestion
    # Recommended: 0.7 for levenshtein, 0.8 for jaro_winkler
    threshold: 0.75
    # Maximum candidates to fuzzy-rank after cheap relevance prefiltering
    max_candidates: 250
```

### Composite Retrieval

Template selection for the Composite Intent Retriever. Improves accuracy when routing queries across multiple intent adapters by combining embedding similarity, optional reranking, and string similarity:

```yaml
composite_retrieval:
  # Two-stage retrieval with reranking
  # Uses the configured reranker (from rerankers.yaml) to re-score top candidates
  reranking:
    enabled: false                   # Enable reranker stage for better semantic understanding
    provider: "anthropic"            # Reranker provider from rerankers.yaml (anthropic, cohere, openai, etc.)
    top_candidates: 10               # Number of embedding candidates to pass to reranker
    weight: 0.4                      # Weight for reranker score in final combined score

  # String similarity scoring - adds lexical matching to complement semantic embeddings
  string_similarity:
    enabled: true
    algorithm: "jaro_winkler"        # jaro_winkler, levenshtein, ratio
    weight: 0.2                      # Weight for string similarity in final combined score
    compare_fields:                  # Template fields to compare against query
      - "description"
      - "nl_examples"
    min_threshold: 0.3               # Minimum string similarity to consider (0.0-1.0)
    aggregation: "max"               # Aggregate multiple field scores: max, avg, weighted_avg

  # Combined scoring formula:
  # final_score = (embedding_weight * emb) + (rerank_weight * rerank) + (string_weight * str_sim)
  # Weights should sum to 1.0 for normalized scoring
  scoring:
    embedding_weight: 0.4            # Weight for embedding similarity (base retrieval)
    normalize_scores: true           # Normalize all scores to 0-1 before combining
    tie_breaker: "embedding"         # embedding, reranker, string_similarity

  # Performance settings
  performance:
    parallel_rerank: true            # Rerank candidates in parallel batches
    cache_rerank_results: true       # Cache reranking results for repeated queries
    cache_ttl_seconds: 300           # TTL for reranking cache (5 minutes)
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
    websocket_update_interval: 5     # Seconds between WebSocket updates
  alerts:
    cpu_threshold: 90
    memory_threshold: 85
    error_rate_threshold: 5
    response_time_threshold: 5000
```

## Internal Services

### Backend Database

Choose between `sqlite` (no installation required), `mongodb`, or `postgres` (require a running server):

```yaml
internal_services:
  backend:
    type: "sqlite"                   # sqlite, mongodb, or postgres
    sqlite:
      database_path: "orbit.db"      # SQLite file path (relative to project root)
    postgres:
      host: ${INTERNAL_SERVICES_POSTGRES_HOST}
      port: ${INTERNAL_SERVICES_POSTGRES_PORT}
      database: ${INTERNAL_SERVICES_POSTGRES_DB}
      username: ${INTERNAL_SERVICES_POSTGRES_USERNAME}
      password: ${INTERNAL_SERVICES_POSTGRES_PASSWORD}
      sslmode: ${INTERNAL_SERVICES_POSTGRES_SSLMODE}
```

### Audit Trail

Stores conversation audit logs for compliance and analytics:

```yaml
internal_services:
  audit:
    enabled: true
    # "database" means use the same backend as internal_services.backend.type
    storage_backend: "database"      # elasticsearch, sqlite, mongodb, postgres, database
    collection_name: "audit_logs"
    # Gzip compression for the response field (saves storage, reduces I/O).
    # Set to false for debugging/testing to see plain text responses.
    compress_responses: true
    clear_on_startup: false          # WARNING: true deletes ALL audit logs on startup
    # Admin & auth event auditing (opt-in). Records mutations on /admin/*
    # and /auth/* endpoints (user CRUD, API-key management, config changes,
    # login/logout, etc.) into a separate collection/table.
    admin_events:
      enabled: true
      collection_name: "audit_admin_logs"
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

### Cache Provider

Cache provider selection applies to all caching consumers (rate limiting, quotas, prompt cache, autocomplete, query burst cache, thread datasets, and more). Switch backends by changing `provider` and enabling the matching block below; no other config needs to change.

- `sqlite` - zero-config default; no external service, persists across restarts
- `redis` - best for multi-instance deployments needing shared/distributed caching
- `memcached` - lighter-weight alternative to Redis for single-purpose caching

```yaml
internal_services:
  cache:
    # Master switch. When false, NO cache provider is created at all.
    # Dependent features (quota/throttling hard limits, autocomplete distributed
    # cache, query burst cache, cache-backed conversation threading) fall back
    # to in-memory/no-op behavior and log a warning.
    enabled: false
    provider: "sqlite"               # sqlite | redis | memcached
    clear_cache_on_startup: true
    # Query burst cache - absorbs repeated identical queries (e.g. user clicking retry)
    query_cache:
      enabled: false
      ttl: 30                        # Seconds to cache identical query results
      max_memory_entries: 100        # In-memory fallback when the cache provider is unavailable
```

### SQLite Cache

Default cache provider. No external service required; a good fit for single-instance self-hosted deployments. Uses its own database file, separate from the application database, so cache write volume doesn't contend with application data. Slower than Redis/Memcached under high write throughput since every write is a disk-backed transaction.

```yaml
internal_services:
  sqlite_cache:
    enabled: true
    database_path: "orbit_cache.db"
    ttl: 3600                        # 1 hour
```

### Redis

```yaml
internal_services:
  redis:
    enabled: false
    host: ${INTERNAL_SERVICES_REDIS_HOST}
    port: ${INTERNAL_SERVICES_REDIS_PORT}
    db: 0
    username: ${INTERNAL_SERVICES_REDIS_USERNAME}
    password: ${INTERNAL_SERVICES_REDIS_PASSWORD}
    use_ssl: false
    ttl: 3600                        # 1 hour
    # Connection pool settings
    max_connections: 20
    socket_connect_timeout: 5
    socket_timeout: 5
    retry_on_timeout: true
    # Resilience settings
    health_check_interval: 30
    max_consecutive_failures: 5
    circuit_recovery_timeout: 30
```

### Memcached

Lighter-weight alternative to Redis. Requires the `memcached` dependency profile (`./install/setup.sh --profile memcached`). Note: no selective cache invalidation (no key pattern matching) and no TTL introspection, which are inherent Memcached protocol limitations.

```yaml
internal_services:
  memcached:
    enabled: false
    host: ${INTERNAL_SERVICES_MEMCACHED_HOST}
    port: 11211
    pool_size: 20
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

Global defaults for all file adapters. Individual adapters in `adapters.yaml` can override these settings.

> **Note:** File metadata (`uploaded_files`, `file_chunks`) is stored in the main backend database configured in `internal_services.backend`, not in a separate `files.db`.

### File Storage

Uploaded files are stored on the local filesystem by default. Set `storage_backend` to `s3`, `minio`, `azure`, or `gcs` to store uploads in the cloud instead. Cloud backends require the `cloud-services` dependency profile.

```yaml
files:
  # Storage backend selection: filesystem | s3 | minio | azure | gcs
  storage_backend: "filesystem"
  storage_root: "./uploads"            # Root directory for uploaded files (filesystem backend)

  # AWS S3 / S3-compatible (MinIO) settings - used when storage_backend is s3 or minio.
  # The bucket must already exist. Always reference env vars; never inline secrets.
  s3:
    bucket: "${ORBIT_S3_BUCKET:-}"
    prefix: "${ORBIT_S3_PREFIX:-}"                # Optional key prefix within the bucket
    region: "${AWS_REGION:-us-east-1}"
    endpoint_url: "${ORBIT_S3_ENDPOINT_URL:-}"    # Set for MinIO / S3-compatible stores
    # Omit the credentials below to use the boto3 default chain (env / instance role / SSO):
    # access_key_id: "${AWS_ACCESS_KEY_ID:-}"
    # secret_access_key: "${AWS_SECRET_ACCESS_KEY:-}"

  # Azure Blob settings - used when storage_backend is azure. The container must already exist.
  azure:
    container: "${ORBIT_AZURE_CONTAINER:-}"
    prefix: "${ORBIT_AZURE_PREFIX:-}"             # Optional blob-name prefix
    connection_string: "${AZURE_STORAGE_CONNECTION_STRING:-}"
    # Or identity-based auth (managed identity / Entra) instead of a connection string:
    # account_url: "${AZURE_STORAGE_ACCOUNT_URL:-}"
    # account_key: "${AZURE_STORAGE_ACCOUNT_KEY:-}"  # Omit to use DefaultAzureCredential

  # Google Cloud Storage settings - used when storage_backend is gcs. The bucket must already exist.
  gcs:
    bucket: "${ORBIT_GCS_BUCKET:-}"
    prefix: "${ORBIT_GCS_PREFIX:-}"               # Optional object-name prefix
    project: "${GOOGLE_CLOUD_PROJECT:-}"          # Optional; inferred from credentials if omitted
    # Omit credentials_path to use Application Default Credentials (ADC):
    #   GOOGLE_APPLICATION_CREDENTIALS env, gcloud user creds, or Workload Identity on GCP.
    # credentials_path: "${GOOGLE_APPLICATION_CREDENTIALS:-}"  # Service-account JSON key file
```

### File Encryption at Rest

AES-256-GCM encryption for sensitive/classified content. Opt-in per adapter via `capabilities.requires_encryption: true` (see `adapters.yaml`). Encrypts file bytes and the storage backend's metadata sidecar only, not extracted text stored in the database or chunk text indexed in the vector store.

```yaml
files:
  encryption:
    enabled: false
    # Generate a key with:
    #   python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    # The key is read from the ORBIT_FILE_ENCRYPTION_KEY environment variable (see env.example).
    # Reference the env var only - never inline the key in config.
```

### Chunking and Processing

```yaml
files:
  # Default chunking settings (can be overridden per adapter)
  # Recommended: "recursive" - works best for all file types and respects
  # document structure (paragraphs -> sentences -> words)
  default_chunking_strategy: "recursive"   # fixed, semantic, token, recursive
  default_chunk_size: 2048                 # Characters for fixed/semantic, tokens for token/recursive
  default_chunk_overlap: 200               # Overlap between chunks
  
  # Processor configuration
  processing:
    # Set docling_enabled to false to prevent outbound connections to HuggingFace
    # at startup (docling is then lazily initialized only when actually needed)
    docling_enabled: false             # Docling document processor (advanced document understanding)
    markitdown_enabled: true           # MarkItDown processor (Microsoft's document-to-markdown converter)
    ai_document_enabled: false         # AI/LLM OCR processor for PDFs and images (see ocr.yaml)
    # Processor priority when multiple universal processors are enabled:
    # which processor is tried first for overlapping MIME types
    processor_priority: "markitdown"   # docling, markitdown, ai_document, native
    
    markitdown:
      enable_plugins: false            # Third-party plugins (disabled by default for security)

    # AI/LLM OCR options (used when ai_document_enabled is true).
    # Provider credentials/models live in ocr.yaml; these tune the processor.
    ai_document:
      provider: "mistral"              # mistral | openai | gemini | anthropic | cohere | ollama | vllm | llama_cpp
      model: null                      # Optional model override; null = provider's model from ocr.yaml
      max_pages: 50                    # Cap PDF pages sent to vision-backed providers (Mistral OCR ignores)
      dpi: 150                         # Rasterization DPI for vision-backed PDF OCR
      prompt: null                     # Optional custom OCR prompt for vision-backed providers

    # Magika upload inspection - verifies uploaded content against the
    # declared MIME type before processing
    magika:
      enabled: false
      enforcement: "block"
      prediction_mode: "HIGH_CONFIDENCE"
      allow_generic_text_fallback: false
      allow_generic_binary_fallback: false
      log_detection_details: true
    
    csv:
      full_data_row_threshold: 200     # Include all rows below this threshold (0 = always summary mode)
      max_preview_rows: 5              # Sample rows shown in summary mode
      max_column_width: 50             # Max characters per column value before truncation
      max_columns_full: 15             # Max columns shown in detail
    
    json:
      full_data_item_threshold: 200    # Include all array items below this threshold (0 = always summary mode)
      max_array_preview_items: 3
      max_schema_depth: 4
      max_string_length: 100
      max_object_keys: 20
  
  # Tokenizer configuration (requires chonkie library for advanced tokenizers)
  tokenizer: null                      # character (default), gpt2, tiktoken
  use_tokens: false                    # Use token-based chunking for the fixed strategy
  
  # Strategy-specific options
  chunking_options:
    # Semantic chunking options
    model_name: null                   # Optional sentence-transformer model (e.g., "all-MiniLM-L6-v2")
    use_advanced: false                # Advanced semantic chunking (requires sentence-transformers)
    chunk_size_tokens: null            # Optional token-based chunk size limit for semantic chunks

    # Recursive chunking options
    min_characters_per_chunk: 24

    # Advanced semantic chunking options (when use_advanced: true)
    threshold: 0.8                     # Similarity threshold (0-1) for semantic boundary detection
    similarity_window: 3               # Sentences to consider for similarity calculation
    min_sentences_per_chunk: 1
    min_characters_per_sentence: 24
    skip_window: 0                     # Groups to skip when merging (0 = disabled)
    filter_window: 5                   # Window length for Savitzky-Golay filter (requires scipy)
    filter_polyorder: 3                # Polynomial order for Savitzky-Golay filter
    filter_tolerance: 0.2              # Tolerance for Savitzky-Golay filter
  
  # Vector store defaults (can be overridden per adapter)
  default_vector_store: "chroma"
  default_collection_prefix: "files_"
```

## Secrets Management

Controls where `${VAR_NAME}` placeholders used throughout `config/*.yaml` are resolved from. The default (`env`) resolves from `.env` / the process environment, exactly as before this feature existed. Setting `provider` to `aws`, `azure`, or `gcp` additionally resolves each placeholder as a secret of the same name in that cloud provider — the provider is consulted first, and only names it doesn't have fall back to `.env`/environment, then to any `${VAR:-default}`. This means no existing `config/*.yaml` file needs to change to adopt a cloud provider; only the resolution source changes.

```yaml
secrets_management:
  provider: "env"                      # env, aws, azure, gcp

  aws:
    region: "us-east-1"
    endpoint_url: ""                   # optional, e.g. LocalStack for testing

  azure:
    vault_url: ""                      # e.g. https://your-vault.vault.azure.net/

  gcp:
    project: ""
```

Cloud providers require the `secrets-management` dependency profile:

```bash
./install/setup.sh --profile secrets-management
```

Notes:
- **Naming**: each `${VAR_NAME}` is looked up as a secret of the exact same name (AWS Secrets Manager, GCP Secret Manager), except Azure Key Vault, which disallows underscores in secret names — `DATASOURCE_POSTGRES_PASSWORD` is looked up there as `DATASOURCE-POSTGRES-PASSWORD`.
- **Failure handling**: if the backend can't be reached at startup, or an individual secret lookup fails, ORBIT logs a warning and falls back to `.env`/environment rather than crashing.
- **Caching**: resolved secrets are cached in-memory for the life of the process to avoid repeated cloud API calls on every admin-triggered config reload.

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

The configured cache provider (`internal_services.cache.provider`) enforces limits atomically. If the cache service is disabled or an operation fails, a per-worker in-memory fixed-window fallback is used. With `workers > 1`, the aggregate fallback ceiling can be up to `limit * workers`.

```yaml
security:
  rate_limiting:
    enabled: false                     # Master switch
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

Executes before rate limiting. Delays requests progressively instead of rejecting them:

```yaml
security:
  throttling:
    enabled: false                     # Master switch
    
    # Default quotas for API keys (can be overridden per-key)
    default_quotas:
      daily_limit: 10000
      monthly_limit: 100000
    
    delay:
      min_ms: 100                      # Minimum delay when throttling starts
      max_ms: 5000                     # Maximum delay before quota rejection
      curve: "exponential"             # linear or exponential
      threshold_percent: 70            # Start throttling at 70% quota
    
    # Priority-based delay multipliers (priority 1-10)
    priority_multipliers:
      1: 0.5                           # Premium: half delay
      5: 1.0                           # Standard: normal delay
      10: 2.0                          # Low priority: double delay
    
    # Paths to exclude from throttling
    exclude_paths: []
    
    cache_key_prefix: "quota:"
    usage_sync_interval_seconds: 60    # Sync cache usage to database
    
    # Response headers
    headers:
      delay: "X-Throttle-Delay"
      daily_remaining: "X-Quota-Daily-Remaining"
      monthly_remaining: "X-Quota-Monthly-Remaining"
      daily_reset: "X-Quota-Daily-Reset"
      monthly_reset: "X-Quota-Monthly-Reset"
```

### Request Limits & Error Handling

```yaml
security:
  request_limits:
    max_body_size_mb: 10
  
  error_handling:
    expose_details: false              # Set true only for development/debugging
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

## OCR Configuration (ocr.yaml)

Powers the `ai_document` universal file processor — a third option alongside Docling and MarkItDown that offloads OCR for **PDFs and images** to an LLM inference service. Enable it with `files.processing.ai_document_enabled: true` and select the active provider with `files.processing.ai_document.provider` (see [File Processing](#chunking-and-processing)).

Two kinds of backend:

- **Mistral OCR** (`mistral`) — the dedicated `client.ocr` endpoint. Ingests a PDF or image directly and returns per-page markdown; no page rasterization.
- **Vision-backed** (`openai`, `gemini`, `anthropic`, `cohere`, `ollama`, `vllm`, `llama_cpp`) — PDF pages are rasterized to images (via `pypdfium2`) and sent through the provider's vision model, reusing the per-provider settings from `vision.yaml`. Single-frame images are OCR'd directly; multi-frame images (multi-page TIFF, animated GIF) are split frame-by-frame and OCR'd page-by-page like a PDF.

Both backends handle **PDFs and images only** — other document formats (DOCX, PPTX, XLSX, HTML, CSV, …) already carry extractable text and continue to flow to Docling / MarkItDown / native processors. The `max_pages` limit caps PDF pages and image frames for vision-backed providers (Mistral native OCR ignores it).

> **Note:** The provider you set as `ai_document.provider` must also be `enabled: true` here — registration is gated by this flag. Vision-backed entries only need `enabled`; their model/API key come from `vision.yaml`. When `files.processing.ai_document.model` is set, it overrides the vision provider's model for OCR only.

```yaml
ocr:
  provider: "mistral"                  # Informational default; actual selection is files.processing.ai_document.provider

  # Mistral native OCR (dedicated endpoint, PDF/image-direct)
  mistral:
    enabled: true
    api_key: ${MISTRAL_API_KEY}
    model: "mistral-ocr-latest"
    timeout:
      connect: 15000
      total: 120000                    # OCR of multi-page PDFs can be slow
    retry:
      enabled: true
      max_retries: 3

  # Vision-backed providers — reuse settings from vision.yaml (visions:).
  # Enable the one you set as files.processing.ai_document.provider.
  openai:
    enabled: false
  gemini:
    enabled: false
  anthropic:
    enabled: false
  cohere:
    enabled: false
  ollama:
    enabled: false
  vllm:
    enabled: false
  llama_cpp:
    enabled: false
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

  xai:
    enabled: true
    api_key: ${XAI_API_KEY}
    api_base: "https://api.x.ai/v1"
    stt_model: "grok-stt"              # Label for logs/cache keys
    language: null                     # Optional: "en", "fr", "de", etc.
    format: false                      # true requires language
    diarize: false
    keyterms: []
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
| `INTERNAL_SERVICES_POSTGRES_HOST` | PostgreSQL host (backend database) |
| `INTERNAL_SERVICES_POSTGRES_PORT` | PostgreSQL port (backend database) |
| `INTERNAL_SERVICES_POSTGRES_DB` | PostgreSQL database name (backend database) |
| `INTERNAL_SERVICES_POSTGRES_USERNAME` | PostgreSQL username (backend database) |
| `INTERNAL_SERVICES_POSTGRES_PASSWORD` | PostgreSQL password (backend database) |
| `INTERNAL_SERVICES_POSTGRES_SSLMODE` | PostgreSQL SSL mode (backend database) |
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
| `INTERNAL_SERVICES_MEMCACHED_HOST` | Memcached host |

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

### File Storage

| Variable | Description |
|:---|:---|
| `ORBIT_S3_BUCKET` | S3 bucket for file uploads |
| `ORBIT_S3_PREFIX` | Optional S3 key prefix |
| `ORBIT_S3_ENDPOINT_URL` | S3 endpoint URL (for MinIO / S3-compatible stores) |
| `AWS_REGION` | AWS region (S3 and Secrets Manager) |
| `ORBIT_AZURE_CONTAINER` | Azure Blob container for file uploads |
| `ORBIT_AZURE_PREFIX` | Optional Azure blob-name prefix |
| `AZURE_STORAGE_CONNECTION_STRING` | Azure Storage connection string |
| `ORBIT_GCS_BUCKET` | Google Cloud Storage bucket for file uploads |
| `ORBIT_GCS_PREFIX` | Optional GCS object-name prefix |
| `ORBIT_FILE_ENCRYPTION_KEY` | Base64-encoded AES-256 key for file encryption at rest |

### Secrets Management

| Variable | Description |
|:---|:---|
| `ORBIT_SECRETS_PROVIDER` | Secrets provider: env, aws, azure, gcp |
| `ORBIT_SECRETS_AWS_ENDPOINT_URL` | Optional AWS Secrets Manager endpoint (e.g. LocalStack) |
| `AZURE_KEY_VAULT_URL` | Azure Key Vault URL |

### Authentication

| Variable | Description |
|:---|:---|
| `ORBIT_DEFAULT_ADMIN_PASSWORD` | Default admin password |
| `ORBIT_TLS_KEY_PASSWORD` | Passphrase for encrypted TLS private key |
| `ORBIT_AUTH_ENTRA_TENANT_ID` | Microsoft Entra ID tenant ID |
| `ORBIT_AUTH_ENTRA_CLIENT_ID` | Microsoft Entra ID client ID |
| `ORBIT_AUTH_ENTRA_CLIENT_SECRET` | Microsoft Entra ID client secret (admin-panel SSO) |
| `ORBIT_AUTH_AUTH0_DOMAIN` | Auth0 tenant domain |
| `ORBIT_AUTH_AUTH0_AUDIENCE` | Auth0 API identifier (token audience) |
| `ORBIT_AUTH_AUTH0_CLIENT_ID` | Auth0 client ID (admin-panel SSO) |
| `ORBIT_AUTH_AUTH0_CLIENT_SECRET` | Auth0 client secret (admin-panel SSO) |
| `ORBIT_ADMIN_BASE_URL` | Base URL override for admin-panel SSO redirects |

## Best Practices

### Security
- Use environment variables for all credentials
- Enable HTTPS in production
- Configure specific CORS origins (not `*`)
- Set `expose_details: false` in production error handling
- Enable rate limiting (backed by the configured cache provider)

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
| Rate limiting not working | Ensure the cache service (`internal_services.cache`) is enabled and connected |
| Adapter initialization timeout | Increase `adapter_preload_timeout` in performance section |
| Vector store connection failed | Check store configuration in `stores.yaml` |
