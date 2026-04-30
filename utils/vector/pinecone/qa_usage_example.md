# QA Adapter Usage Example for Pinecone

This guide demonstrates how to use the QA-specialized Pinecone retriever with the Orbit server.

## Prerequisites

1. **Pinecone API Key**: Set your Pinecone API key in `.env`:
   ```bash
   DATASOURCE_PINECONE_API_KEY=your-api-key-here
   ```

2. **Install Pinecone Client**:
   ```bash
   pip install pinecone>=7.3.0
   ```

3. **Create and Populate an Index**: Use the provided scripts to create a Pinecone index:
   ```bash
   # Create index with Q&A pairs
   python examples/pinecone/create_pinecone_index.py city-faq examples/city-qa-pairs.json
   ```

## Configuration

### 1. Configure the Adapter in `config/adapters.yaml`

Enable the `qa-vector-pinecone` adapter:

```yaml
- name: "qa-vector-pinecone"
  enabled: true  # Set to true to enable
  type: "retriever"
  datasource: "pinecone"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAPineconeRetriever"
  inference_provider: "cohere"
  embedding_provider: "openai"
  config:
    collection: "city-faq"  # Your Pinecone index name
    confidence_threshold: 0.3
    score_scaling_factor: 1.0
    embedding_provider: null  # Uses default from config
    max_results: 5
    return_results: 3
    timezone: "America/Toronto"
```

### 2. Verify Pinecone Configuration in `config/datasources.yaml`

Ensure Pinecone is properly configured:

```yaml
datasources:
  pinecone:
    api_key: ${DATASOURCE_PINECONE_API_KEY}
    namespace: "default"
    embedding_provider: null
```

### 3. Configure Embedding Provider

Make sure your embedding provider is configured in `config/embeddings.yaml`. Example:

```yaml
embeddings:
  openai:
    model: "text-embedding-3-small"
    dimensions: 1536
    api_key: ${OPENAI_API_KEY}
```

## Usage

### Start the Orbit Server

```bash
cd server
python app.py
```

### Query the QA Adapter via API

**Example using curl:**

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "query": "How do I pay my property taxes?",
    "adapter": "qa-vector-pinecone"
  }'
```

**Example using Python:**

```python
import requests

response = requests.post(
    "http://localhost:8080/query",
    headers={
        "Content-Type": "application/json",
        "X-API-Key": "your-api-key"
    },
    json={
        "query": "What are the library hours?",
        "adapter": "qa-vector-pinecone"
    }
)

print(response.json())
```

## Response Format

The API returns matching Q&A pairs with confidence scores:

```json
{
  "response": "Based on the retrieved information: The library is open...",
  "context": [
    {
      "content": "Question: What are the library hours?\nAnswer: The library is open Monday-Friday 9am-8pm...",
      "confidence": 0.89,
      "question": "What are the library hours?",
      "answer": "The library is open Monday-Friday 9am-8pm, Saturday 10am-6pm...",
      "metadata": {
        "source": "pinecone",
        "collection": "city-faq",
        "similarity": 0.89,
        "score": 0.89
      }
    }
  ]
}
```

## Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `collection` | Pinecone index name | Required |
| `confidence_threshold` | Minimum confidence score (0-1) for results | 0.3 |
| `score_scaling_factor` | Multiplier for Pinecone similarity scores | 1.0 |
| `max_results` | Maximum results to retrieve from Pinecone | 5 |
| `return_results` | Maximum results to return to the user | 3 |
| `embedding_provider` | Override default embedding provider | null |
| `namespace` | Pinecone namespace (from datasources.yaml) | "default" |

## Advanced Usage

### Using Multiple Collections (Indexes)

You can configure multiple QA adapters for different Pinecone indexes:

```yaml
- name: "qa-customer-support"
  enabled: true
  type: "retriever"
  datasource: "pinecone"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAPineconeRetriever"
  config:
    collection: "customer-support-faq"
    confidence_threshold: 0.4

- name: "qa-product-docs"
  enabled: true
  type: "retriever"
  datasource: "pinecone"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QAPineconeRetriever"
  config:
    collection: "product-documentation"
    confidence_threshold: 0.3
```

### Dynamic Collection Selection

You can specify the collection at query time:

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "query": "How do I return a product?",
    "adapter": "qa-vector-pinecone",
    "collection": "product-docs"
  }'
```

## Pinecone-Specific Features

### Serverless Architecture

Pinecone supports serverless indexes with automatic scaling:

```python
# When creating an index (see create_pinecone_index.py)
from pinecone import ServerlessSpec

pc.create_index(
    name="my-index",
    dimension=1536,
    metric="cosine",
    spec=ServerlessSpec(
        cloud="aws",
        region="us-east-1"
    )
)
```

### Namespaces

Pinecone supports namespaces for logical data separation within an index:

```yaml
datasources:
  pinecone:
    api_key: ${DATASOURCE_PINECONE_API_KEY}
    namespace: "production"  # Use different namespaces for different environments
```

### Metadata Filtering

Pinecone supports metadata filtering for more precise queries (future enhancement):

```python
# Future enhancement example
results = index.query(
    vector=embedding,
    top_k=5,
    filter={
        "category": {"$eq": "billing"},
        "priority": {"$gte": 3}
    }
)
```

## Monitoring and Debugging

### Enable Verbose Logging

In `config/config.yaml`:

```yaml
verbose: true
```

This will show detailed logs including:
- Embedding generation
- Pinecone query execution
- Score-to-confidence conversion
- Result filtering

### Check Index Stats

Use the provided utility script:

```bash
python examples/pinecone/list_pinecone_indexes.py
```

## Troubleshooting

### Issue: Empty Results

**Possible causes:**
- Confidence threshold too high
- Index is empty or not populated
- Embedding model mismatch between ingestion and query

**Solutions:**
```yaml
config:
  confidence_threshold: 0.1  # Lower threshold temporarily
  max_results: 10  # Increase to see more candidates
```

### Issue: Low-Quality Matches

**Possible causes:**
- Score scaling factor needs adjustment
- Wrong embedding provider

**Solutions:**
```yaml
config:
  score_scaling_factor: 0.8  # Reduce to be more selective
  embedding_provider: "openai"  # Try different provider
```

### Issue: Connection Errors

**Check:**
1. API key is set correctly in `.env`
2. Pinecone service is accessible
3. Index name exists

```bash
# Verify API key
echo $DATASOURCE_PINECONE_API_KEY

# List available indexes
python examples/pinecone/list_pinecone_indexes.py
```

## Performance Optimization

### Batch Operations

When creating indexes, use batch uploads (default 100 vectors per batch):

```python
await ingest_to_pinecone(
    json_file_path="data.json",
    config=config,
    embedding_provider="openai",
    index_name="my-index",
    batch_size=100  # Adjust based on your data size
)
```

### Caching

Pinecone handles caching internally, but you can implement application-level caching for frequently asked questions.

### Index Selection

- Use smaller dimensions for faster queries (with trade-off in accuracy)
- Consider using serverless for variable workloads
- Use pod-based indexes for consistent high throughput

## Example Workflow

```bash
# 1. Set up environment
export DATASOURCE_PINECONE_API_KEY="your-api-key"
export OPENAI_API_KEY="your-openai-key"

# 2. Create and populate index
python examples/pinecone/create_pinecone_index.py city-faq examples/city-qa-pairs.json

# 3. Configure adapter (edit config/adapters.yaml)
# Set enabled: true for qa-vector-pinecone

# 4. Start server
cd server
python app.py

# 5. Test queries
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "What are the library hours?", "adapter": "qa-vector-pinecone"}'
```

## Related Resources

- [Pinecone Documentation](https://docs.pinecone.io/)
- [Orbit Server Documentation](../../README.md)
- [QA Adapter Architecture](../../server/retrievers/implementations/qa/README.md)
- [Embedding Configuration Guide](../../config/README.md)
