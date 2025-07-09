# Configuration Guide

## Overview

ORBIT uses a flexible configuration system that combines YAML configuration files with environment variables. The configuration is managed by the `config_manager.py` module, which provides:

- Default configuration values
- Environment variable substitution
- Configuration validation
- Secure credential handling
- Logging of configuration changes

## Configuration Sources

The system looks for configuration in the following order:

1. User-specified config path
2. `../config/config.yaml`
3. `../../config/config.yaml`
4. `config.yaml` in current directory
5. Default configuration (if no file is found)

### Import Support

The configuration system supports importing external YAML files using the `import` directive:

```yaml
# Import external configuration files
import: "adapters.yaml"
# or multiple files
import: 
  - "adapters.yaml"
  - "custom-config.yaml"
```

This allows you to separate large configuration sections (like adapters) into dedicated files for better maintainability. See [Adapter Configuration Management](adapter-configuration.md) for detailed information.

## Configuration Structure

### General Settings

```yaml
general:
  port: 3000                    # Port number for HTTP server
  verbose: false                # Enable detailed logging for debugging
  https:
    enabled: false              # Enable HTTPS for secure connections
    port: 3443                  # Port number for HTTPS server
    cert_file: "./cert.pem"     # Path to SSL certificate file
    key_file: "./key.pem"       # Path to SSL private key file
  session_id:
    header_name: "X-Session-ID" # HTTP header name for session ID
    required: true              # Whether session ID is required
  inference_provider: "ollama"  # Default AI model provider
  inference_only: true         # Run in inference-only mode
  adapter: "qa-sql"            # Default adapter to use
```

### Messages Configuration

```yaml
messages:
  no_results_response: "I'm sorry, but I don't have any specific information about that topic in my knowledge base."
  collection_not_found: "I couldn't find the requested collection. Please make sure the collection exists before querying it."
```

### Embedding Configuration

```yaml
embedding:
  provider: "ollama"            # Default embedding provider
  enabled: false                # Enable embedding functionality
```

### API Key Management

```yaml
api_keys:
  header_name: "X-API-Key"      # HTTP header name for API key
  prefix: "orbit_"             # Prefix for generated API keys
```

### Logging Configuration

```yaml
logging:
  level: "INFO"                # Logging level (DEBUG, INFO, WARNING, ERROR)
  handlers:                    # Note: structure is different from documentation
    file:
      enabled: true              # Enable logging to file
      directory: "logs"          # Directory for log files
      filename: "orbit.log"     # Name of the log file
      max_size_mb: 10           # Maximum size of each log file in megabytes
      backup_count: 30          # Number of backup log files to keep
      rotation: "midnight"      # When to rotate logs (midnight, hourly, daily)
      format: "text"            # Log format (json for machine parsing, text for human reading)
    console:
      enabled: false            # Enable logging to console
      format: "text"            # Console log format
  capture_warnings: true      # Capture Python warnings in logs
  propagate: false            # Prevent log propagation to parent loggers
  loggers:                    # Specific logger configurations
    inference.clients.llama_cpp:
      level: "ERROR"
    llama_cpp:
      level: "ERROR"
    llama_cpp.llama:
      level: "ERROR"
    ggml:
      level: "ERROR"
    metal:
      level: "ERROR"
```

### Chat History Configuration

```yaml
chat_history:
  enabled: true                     # Enable chat history functionality
  collection_name: "chat_history"   # MongoDB collection name for chat history
  store_metadata: true              # Store additional metadata with messages
  retention_days: 90                # How long to keep chat history (days)
  max_tracked_sessions: 10000       # Maximum number of sessions to track
  session:
    auto_generate: false            # Auto-generate session IDs if not provided
    required: true                  # Whether session is required
    header_name: "X-Session-ID"     # HTTP header name for session ID
  user:
    header_name: "X-User-ID"        # HTTP header name for user ID
    required: false                 # Whether user ID is required
```

### File Upload Configuration

```yaml
file_upload:
  enabled: true                     # Enable file upload functionality
  max_size_mb: 10                   # Maximum file size in megabytes
  max_files_per_batch: 10           # Maximum files per upload batch
  allowed_extensions:               # List of allowed file extensions
    - ".txt"
    - ".pdf"
    - ".docx"
    - ".doc"
    - ".xlsx"
    - ".xls"
    - ".csv"
    - ".md"
    - ".json"
  upload_directory: "uploads"       # Directory to store uploaded files
  save_to_disk: true                # Save files to disk
  auto_store_in_vector_db: true     # Automatically add to vector database
  chunk_size: 1000                  # Text chunk size for processing
  chunk_overlap: 200                # Overlap between text chunks
```

### Internal Services Configuration

```yaml
internal_services:
  elasticsearch:
    enabled: false
    node: ${INTERNAL_SERVICES_ELASTICSEARCH_NODE}      # Note: different from docs
    index: 'orbit'
    username: ${INTERNAL_SERVICES_ELASTICSEARCH_USERNAME}  # Note: different from docs
    password: ${INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD}  # Note: different from docs

  mongodb:
    host: ${INTERNAL_SERVICES_MONGODB_HOST}
    port: ${INTERNAL_SERVICES_MONGODB_PORT}
    database: "orbit"
    apikey_collection: "api_keys"
    username: ${INTERNAL_SERVICES_MONGODB_USERNAME}
    password: ${INTERNAL_SERVICES_MONGODB_PASSWORD}

  redis:
    enabled: false
    host: ${INTERNAL_SERVICES_REDIS_HOST}
    port: ${INTERNAL_SERVICES_REDIS_PORT}
    db: 0
    username: ${INTERNAL_SERVICES_REDIS_USERNAME}
    password: ${INTERNAL_SERVICES_REDIS_PASSWORD}
    use_ssl: false
    ttl: 604800
```

### Embeddings Configuration

```yaml
embeddings:
  llama_cpp:
    model_path: "gguf/nomic-embed-text-v1.5-Q4_0.gguf"
    model: "nomic-embed-text-v1.5-Q4_0"
    n_ctx: 512                    # Note: different default value
    n_threads: 4
    n_gpu_layers: 0
    main_gpu: 0 
    tensor_split: null
    batch_size: 8
    dimensions: 768
    embed_type: "llama_embedding"
  ollama:
    base_url: "http://localhost:11434"
    model: "nomic-embed-text"
    dimensions: 768
  jina:
    api_key: ${JINA_API_KEY}
    base_url: "https://api.jina.ai/v1"
    model: "jina-embeddings-v3"
    task: "text-matching"
    dimensions: 1024
    batch_size: 10
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "text-embedding-3-large"
    dimensions: 1024
    batch_size: 10
  cohere:
    api_key: ${COHERE_API_KEY}
    model: "embed-english-v3.0"
    input_type: "search_document"
    dimensions: 1024
    batch_size: 32
    truncate: "NONE"
    embedding_types: ["float"]
  mistral:
    api_key: ${MISTRAL_API_KEY}
    api_base: "https://api.mistral.ai/v1"
    model: "mistral-embed"
    dimensions: 1024
```

### Adapters Configuration

```yaml
adapters:
  - name: "qa-sql"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"    # Note: different path
    config:
      confidence_threshold: 0.3
      max_results: 5
      return_results: 3

  - name: "qa-vector"
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAChromaRetriever"  # Note: different path
    config:
      confidence_threshold: 0.3
      distance_scaling_factor: 200.0
      embedding_provider: null
      max_results: 5
      return_results: 3

  - name: "file-vector"                                                # Note: new adapter
    type: "retriever"
    datasource: "chroma"
    adapter: "file"
    implementation: "retrievers.implementations.file.FileChromaRetriever"
    config:
      confidence_threshold: 0.1
      distance_scaling_factor: 150.0
      embedding_provider: null
      max_results: 10
      return_results: 5
      # File-specific settings
      include_file_metadata: true
      boost_file_uploads: true
      file_content_weight: 1.5
      metadata_weight: 0.8
```

### Data Sources Configuration

```yaml
datasources:
  chroma:
    use_local: true
    db_path: "examples/chroma/chroma_db"
    host: "localhost"
    port: 8000
    embedding_provider: null 
  sqlite:
    db_path: "examples/sqlite/sqlite_db"
  postgres:
    host: "localhost"
    port: 5432
    database: "retrieval"
    username: ${DATASOURCE_POSTGRES_USERNAME}
    password: ${DATASOURCE_POSTGRES_PASSWORD}
  milvus:
    host: "localhost"
    port: 19530
    dim: 768
    metric_type: "IP"  # Options: L2, IP, COSINE
    embedding_provider: null
  pinecone:
    api_key: ${DATASOURCE_PINECONE_API_KEY}
    host: ${DATASOURCE_PINECONE_HOST}                   # Note: different from docs
    namespace: "default"                                # Note: new field
    embedding_provider: null
  elasticsearch:
    node: 'https://localhost:9200'
    auth:
      username: ${DATASOURCE_ELASTICSEARCH_USERNAME}
      password: ${DATASOURCE_ELASTICSEARCH_PASSWORD}
      vector_field: "embedding"                         # Note: new field
      text_field: "content"                             # Note: new field
      verify_certs: true                                # Note: new field
      embedding_provider: null                          # Note: new field
  redis:                                                # Note: new datasource
    host: "localhost"
    port: 6379
    password: ${DATASOURCE_REDIS_PASSWORD}
    db: 0
    use_ssl: false
    vector_field: "embedding"
    text_field: "content"
    distance_metric: "COSINE"  # Options: L2, IP, COSINE
  mongodb:
    host: "localhost"
    port: 27017
    database: "orbit"
    apikey_collection: "api_keys"
    username: ${DATASOURCE_MONGODB_USERNAME}
    password: ${DATASOURCE_MONGODB_PASSWORD}
```

### Inference Providers

```yaml
inference:
  ollama:
    base_url: "http://localhost:11434"
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    repeat_penalty: 1.1
    num_predict: 1024
    num_ctx: 128                    # Note: different default value
    num_threads: 8
    model: "gemma3:1b"
    stream: true
  vllm:
    host: "localhost"
    port: 5000
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    max_tokens: 1024
    model: "Qwen2.5-14B"
    stream: true
  llama_cpp:
    model_path: "gguf/tinyllama-1.1b-chat-v1.0.Q4_0.gguf"   # Note: different default model
    chat_format: "chatml"  # Chat format to use (chatml, llama-2, gemma, etc.)
    verbose: false
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    max_tokens: 1024
    repeat_penalty: 1.1
    n_ctx: 256                      # Note: different default value
    n_threads: 4
    stream: true
    n_gpu_layers: 0  # Disable GPU/Metal support
    main_gpu: 0
    tensor_split: null
    stop_tokens: [                  # Note: different default tokens
      "<|im_start|>", 
      "<|im_end|>",
      "<|endoftext|>"
    ]
  gemini:
    api_key: ${GOOGLE_API_KEY}
    model: "gemini-2.0-flash"
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    max_tokens: 1024
    stream: true
  groq:
    api_key: ${GROQ_API_KEY}
    model: "llama3-8b-8192"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    api_base: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
  vertex:
    project_id: ${GOOGLE_CLOUD_PROJECT}
    location: "us-central1"
    model: "gemini-1.5-pro"
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    max_tokens: 1024
    credentials_path: ""
    stream: true
  aws:
    access_key: ${AWS_BEDROCK_ACCESS_KEY}
    secret_access_key: ${AWS_SECRET_ACCESS_KEY}
    region: "ca-central-1"
    model: "anthropic.claude-3-sonnet-20240229-v1:0"
    content_type: "application/json"
    accept: "application/json"
    max_tokens: 1024
  azure:
    base_url: http://azure-ai.endpoint.microsoft.com
    deployment: "azure-ai-deployment"
    api_key: ${AZURE_ACCESS_KEY}
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
    verbose: true
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "gpt-4.1"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
  mistral:
    api_key: ${MISTRAL_API_KEY}
    api_base: "https://api.mistral.ai/v1"
    model: "mistral-small-latest"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    api_base: "https://api.anthropic.com/v1"
    model: "claude-sonnet-4-20250514"    # Note: different default model
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
  together:
    api_key: ${TOGETHER_API_KEY}
    api_base: "https://api.together.xyz/v1"
    model: "Qwen/Qwen3-235B-A22B-fp8-tput"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
    show_thinking: false
  xai:
    api_key: ${XAI_API_KEY}
    api_base: "https://api.x.ai/v1"
    model: "grok-3-mini-beta"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
    show_thinking: false
  huggingface:
    model_name: "HuggingFaceTB/SmolLM2-1.7B-Instruct"
    device: "cpu"
    max_length: 1024
    temperature: 0.7
    top_p: 0.9
    stream: false
  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: "https://openrouter.ai/api/v1"
    model: "openai/gpt-4o"
    temperature: 0.1
    top_p: 0.8
    max_tokens: 1024
    stream: true
    verbose: false
```

### Safety/Moderation Configuration

```yaml
safety:
  enabled: false
  mode: "fuzzy"
  moderator: "ollama"
  max_retries: 3
  retry_delay: 1.0
  request_timeout: 10
  allow_on_timeout: false
  safety_prompt_path: "prompts/safety_prompt.txt"

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
    model: "granite3.3:2b"              # Note: different default model
    temperature: 0.0
    top_p: 1.0
    max_tokens: 50
    batch_size: 1
```

### Reranker Configuration

```yaml
reranker:
  provider: "ollama"                    # Note: simplified structure
  enabled: false

rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "xitao/bge-reranker-v2-m3:latest"    # Note: different default model
    temperature: 0.0
    batch_size: 5
```

## Environment Variables

The configuration system supports environment variable substitution using the `${VARIABLE_NAME}` syntax. Common variables include:

- `${OPENAI_API_KEY}`: OpenAI API key
- `${ANTHROPIC_API_KEY}`: Anthropic API key
- `${GOOGLE_API_KEY}`: Google API key
- `${MISTRAL_API_KEY}`: Mistral API key
- `${COHERE_API_KEY}`: Cohere API key
- `${JINA_API_KEY}`: Jina API key
- `${GROQ_API_KEY}`: Groq API key
- `${DEEPSEEK_API_KEY}`: Deepseek API key
- `${TOGETHER_API_KEY}`: Together API key
- `${XAI_API_KEY}`: XAI API key
- `${OPENROUTER_API_KEY}`: OpenRouter API key
- `${GOOGLE_CLOUD_PROJECT}`: Google Cloud project ID
- `${AWS_BEDROCK_ACCESS_KEY}`: AWS Bedrock access key
- `${AWS_SECRET_ACCESS_KEY}`: AWS secret access key
- `${AZURE_ACCESS_KEY}`: Azure API key
- `${INTERNAL_SERVICES_ELASTICSEARCH_NODE}`: Elasticsearch node URL
- `${INTERNAL_SERVICES_ELASTICSEARCH_USERNAME}`: Elasticsearch username
- `${INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD}`: Elasticsearch password
- `${INTERNAL_SERVICES_MONGODB_HOST}`: MongoDB host
- `${INTERNAL_SERVICES_MONGODB_PORT}`: MongoDB port
- `${INTERNAL_SERVICES_MONGODB_USERNAME}`: MongoDB username
- `${INTERNAL_SERVICES_MONGODB_PASSWORD}`: MongoDB password
- `${INTERNAL_SERVICES_REDIS_HOST}`: Redis host
- `${INTERNAL_SERVICES_REDIS_PORT}`: Redis port
- `${INTERNAL_SERVICES_REDIS_USERNAME}`: Redis username
- `${INTERNAL_SERVICES_REDIS_PASSWORD}`: Redis password
- `${DATASOURCE_POSTGRES_USERNAME}`: PostgreSQL username
- `${DATASOURCE_POSTGRES_PASSWORD}`: PostgreSQL password
- `${DATASOURCE_PINECONE_API_KEY}`: Pinecone API key
- `${DATASOURCE_PINECONE_HOST}`: Pinecone host URL
- `${DATASOURCE_ELASTICSEARCH_USERNAME}`: Elasticsearch username
- `${DATASOURCE_ELASTICSEARCH_PASSWORD}`: Elasticsearch password
- `${DATASOURCE_REDIS_PASSWORD}`: Redis password for datasource
- `${DATASOURCE_MONGODB_USERNAME}`: MongoDB username for datasource
- `${DATASOURCE_MONGODB_PASSWORD}`: MongoDB password for datasource

## Configuration Management

The `config_manager.py` module provides several key functions:

### Loading Configuration

```python
from config.config_manager import load_config

# Load configuration with default path
config = load_config()

# Load configuration from specific path
config = load_config("path/to/config.yaml")
```

### Configuration Validation

The system automatically:
- Validates required sections
- Applies default values
- Processes environment variables
- Masks sensitive information in logs

### Security Features

- Credentials are masked in logs
- Environment variables for sensitive data
- HTTPS configuration support
- API key management

## Best Practices

1. **Environment Variables**
   - Use environment variables for sensitive data
   - Never commit credentials to configuration files
   - Use different variables for different environments

2. **Configuration Organization**
   - Group related settings together
   - Use clear, descriptive names
   - Document non-obvious settings

3. **Security**
   - Enable HTTPS in production
   - Use strong API key prefixes
   - Configure appropriate timeouts
   - Enable safety checks

4. **Performance**
   - Configure appropriate batch sizes
   - Set reasonable timeouts
   - Enable caching where appropriate
   - Configure appropriate thread counts

## Troubleshooting

Common issues and solutions:

1. **Configuration Not Found**
   - Check file paths
   - Verify file permissions
   - Check for syntax errors

2. **Environment Variables**
   - Verify variables are set
   - Check variable names
   - Ensure proper syntax

3. **Security Issues**
   - Verify HTTPS configuration
   - Check API key settings
   - Validate credentials

4. **Performance Problems**
   - Check batch sizes
   - Verify thread counts
   - Review timeout settings