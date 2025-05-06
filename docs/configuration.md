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
  inference_provider: "ollama"  # Default AI model provider (ollama, llama_cpp, etc.)
  datasource_provider: "chroma" # Default vector database (chroma, sqlite, etc.)
  mcp_protocol: disabled        # Enable Message Content Protocol support
```

### API Key Management

```yaml
api_keys:
  header_name: "X-API-Key"      # HTTP header name for API key
  prefix: "orbit_"             # Prefix for generated API keys
  require_for_health: true      # Require API key for health check endpoint
```

### Logging Configuration

```yaml
logging:
  level: "INFO"                # Logging level (DEBUG, INFO, WARNING, ERROR)
  file:
    enabled: true              # Enable logging to file
    directory: "logs"          # Directory for log files
    filename: "server.log"     # Name of the log file
    max_size_mb: 10           # Maximum size of each log file in megabytes
    backup_count: 30          # Number of backup log files to keep
    rotation: "midnight"      # When to rotate logs (midnight, hourly, daily)
    format: "json"            # Log format (json for machine parsing, text for human reading)
  console:
    enabled: true             # Enable logging to console
    format: "text"            # Console log format
  capture_warnings: true      # Capture Python warnings in logs
  propagate: false            # Prevent log propagation to parent loggers
```

### Embedding Configuration

```yaml
embedding:
  provider: "ollama"          # Default embedding model provider
  enabled: true               # Enable embedding generation
  fail_on_error: false        # Whether to fail if embedding service is unavailable

embeddings:
  ollama:                     # Ollama embedding settings
    base_url: "http://localhost:11434"  # Ollama server URL
    model: "nomic-embed-text"  # Model name for embeddings
    dimensions: 768           # Size of embedding vectors
  openai:                     # OpenAI embedding settings
    api_key: ${OPENAI_API_KEY}  # Your OpenAI API key
    model: "text-embedding-3-large"  # OpenAI embedding model
    dimensions: 1024          # Size of embedding vectors
    batch_size: 10           # Number of texts to embed at once
```

### Safety Configuration

```yaml
safety:
  enabled: true               # Enable content safety checks
  mode: "fuzzy"              # Safety mode (strict: exact matching, fuzzy: flexible matching)
  moderator: "ollama"        # Model to use for content moderation
  max_retries: 3             # Maximum number of retry attempts for safety checks
  retry_delay: 1.0           # Delay between retries in seconds
  request_timeout: 10        # Timeout for safety check requests in seconds
  allow_on_timeout: false    # Whether to allow content if safety check times out
```

### Inference Providers

```yaml
inference:
  ollama:                     # Ollama inference settings
    base_url: "http://localhost:11434"  # Ollama server URL
    temperature: 0.1          # Controls randomness (0.0-1.0, lower = more focused)
    top_p: 0.8               # Nucleus sampling parameter (0.0-1.0)
    top_k: 20                # Number of highest probability tokens to consider
    model: "gemma3:1b"       # Model name to use
    stream: true             # Enable streaming responses
  llama_cpp:                  # llama.cpp settings
    model_path: "gguf/gemma-3-4b-it-q4_0.gguf"  # Path to model file
    chat_format: "chatml"    # Chat format (chatml, llama-2, gemma)
    n_ctx: 1024              # Context window size
    n_threads: 4             # Number of CPU threads to use
    n_gpu_layers: -1         # Number of layers to offload to GPU (-1 = all)
    main_gpu: 0              # Main GPU to use (for multi-GPU systems)
```

### Vector Store Configuration

```yaml
datasources:
  chroma:                     # ChromaDB settings
    use_local: true          # Use local filesystem storage
    db_path: "./chroma_db"   # Path to database files
    host: "localhost"        # Host for remote ChromaDB server
    port: 8000              # Port for remote ChromaDB server
    confidence_threshold: 0.85  # Minimum confidence score for results
    relevance_threshold: 0.7   # Minimum relevance score for results
  sqlite:                     # SQLite settings
    db_path: "sqlite_db"     # Path to SQLite database file
    confidence_threshold: 0.5  # Minimum confidence score
    relevance_threshold: 0.5   # Minimum relevance score
    max_results: 10          # Maximum number of results to return
    return_results: 3        # Number of results to include in response
```

## Environment Variables

The configuration system supports environment variable substitution using the `${VARIABLE_NAME}` syntax. Common variables include:

- `${OPENAI_API_KEY}`: OpenAI API key
- `${INTERNAL_SERVICES_MONGODB_USERNAME}`: MongoDB username
- `${INTERNAL_SERVICES_MONGODB_PASSWORD}`: MongoDB password
- `${INTERNAL_SERVICES_ELASTICSEARCH_API_KEY}`: Elasticsearch API key

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
