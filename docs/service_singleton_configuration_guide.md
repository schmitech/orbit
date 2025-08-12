# Service Singleton Configuration Guide

The system uses singleton patterns for shared services (embedding services, MongoDB services, Redis services, and API key services) to ensure that all adapters share the same service instances, improving performance and reducing resource usage.

## How to Switch Embedding Providers

### Current Configuration
The global embedding provider is set in `config/embeddings.yaml`:

```yaml
# Global embedding configuration
embedding:
  provider: "ollama"  # Current default
  enabled: true       # Whether embeddings are enabled globally
```

**Note**: All embedding configuration is now consolidated in `embeddings.yaml` (previously there was a duplicate section in `config.yaml`).

### Switching to OpenAI Embeddings

1. **Update the provider in `config/embeddings.yaml`:**
```yaml
# Global embedding configuration
embedding:
  provider: "openai"  # Changed from "ollama" to "openai"
```

2. **Ensure your OpenAI API key is set:**
```bash
export OPENAI_API_KEY="your-api-key-here"
```

3. **Restart the server**

### Switching to Other Providers

You can switch to any supported provider:

```yaml
# For Cohere
embedding:
  provider: "cohere"

# For Mistral
embedding:
  provider: "mistral"

# For Jina
embedding:
  provider: "jina"

# For LlamaCpp (local)
embedding:
  provider: "llama_cpp"
```

## How the Singleton Works

### Before (Multiple Instances)
```
Adapter 1 → EmbeddingService A + MongoDB A + Redis A + ApiKeyService A
Adapter 2 → EmbeddingService B + MongoDB B + Redis B + ApiKeyService B  
Adapter 3 → EmbeddingService C + MongoDB C + Redis C + ApiKeyService C
```

### After (Shared Instances)
```
Adapter 1 ┐
Adapter 2 ├─→ Shared Service Instances (Embedding + MongoDB + Redis + ApiKey)
Adapter 3 ┘
```

### Service Singleton Patterns

1. **Embedding Services**: Cached by provider + host + model combination
2. **MongoDB Services**: Cached by host + port + database combination  
3. **Redis Services**: Cached by host + port + database + SSL configuration
4. **API Key Services**: Cached by MongoDB configuration + collection name

## Benefits

1. **Reduced Memory Usage**: Single service instances instead of multiple duplicates
2. **Faster Startup**: Services initialize only once, not per adapter
3. **Consistent Configuration**: All adapters use the same service configuration
4. **Better Resource Management**: Fewer connections to external services (databases, caches, embedding providers)
5. **Improved Performance**: Reduced overhead from duplicate service initialization

## Monitoring

You can monitor cached services via health endpoints:

### Embedding Services
```bash
curl http://localhost:3001/health/embedding-services
```

Response example:
```json
{
  "total_cached_instances": 1,
  "cached_providers": ["ollama:localhost:bge-m3"],
  "memory_info": "1 embedding service instances cached"
}
```

### MongoDB Services
```bash
curl http://localhost:3001/health/mongodb-services
```

### Redis Services
```bash
curl http://localhost:3001/health/redis-services
```

### API Key Services
```bash
curl http://localhost:3001/health/api-key-services
```

## Configuration Validation

The system will:
- Use the provider specified in `embedding.provider`
- Fall back to "ollama" if no provider is specified
- Create separate instances for different configurations (different hosts/models)
- Share instances when the configuration is identical

## Important Notes

- **Global Settings**: Service configurations affect ALL adapters using that service type
- **Restart Required**: Configuration changes require a server restart to take effect
- **API Keys**: Ensure required API keys are set for cloud providers
- **Cache Persistence**: Singleton caches persist for the lifetime of the server
- **Thread Safety**: All singleton implementations are thread-safe with proper locking
- **Configuration Isolation**: Different configurations (different hosts, ports, etc.) create separate instances