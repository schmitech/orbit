# Elasticsearch Sample Data Generator

Generate realistic synthetic application log data and index it into Elasticsearch for testing the Intent Elasticsearch adapter.

## Quick Start

### 1. Set Up Elasticsearch Credentials

```bash
export DATASOURCE_ELASTICSEARCH_USERNAME=elastic
export DATASOURCE_ELASTICSEARCH_PASSWORD=your-password
```

### 2. Update Elasticsearch Node URL

Edit `config/datasources.yaml`:
```yaml
elasticsearch:
  node: 'https://your-elastic-cloud-instance.es.io:9200'  # Your Elastic Cloud URL
  verify_certs: true
  timeout: 30
  auth:
    username: ${DATASOURCE_ELASTICSEARCH_USERNAME}
    password: ${DATASOURCE_ELASTICSEARCH_PASSWORD}
```

### 3. Install Dependencies

```bash
# Install Faker for synthetic data generation
pip install faker

# Install Elasticsearch Python client (already installed with ORBIT)
pip install elasticsearch
```

### 4. Generate Sample Data

#### Basic Usage (No AI)
```bash
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 1000 \
    --index logs-app-demo
```

#### With AI-Generated Messages (More Realistic)
```bash
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 1000 \
    --index logs-app-demo \
    --use-ai \
    --provider openai
```

#### Large Dataset with Custom Settings
```bash
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 10000 \
    --index logs-app-production \
    --days-back 30 \
    --error-rate 15 \
    --batch-size 500
```

## Generated Data Model

The script generates application logs with the following fields:

### Core Fields
- **timestamp**: ISO 8601 timestamp
- **level**: Log level (ERROR, WARN, INFO, DEBUG)
- **message**: Log message text
- **logger**: Logger name (e.g., "auth-service.RequestLogger")
- **service_name**: Service that generated the log
- **environment**: Environment (production, staging, development)
- **host**: Hostname
- **request_id**: Unique request ID (UUID)

### Optional Fields
- **user_id**: User identifier (if applicable)
- **response_time**: Response time in milliseconds (for API calls)
- **status_code**: HTTP status code (for API calls)
- **endpoint**: API endpoint (for API calls)
- **exception**: Exception details (for ERROR logs)
  - **type**: Exception type
  - **message**: Exception message
  - **stacktrace**: Stack trace

## Configuration Options

### Required Environment Variables
- `DATASOURCE_ELASTICSEARCH_USERNAME`: Elasticsearch username
- `DATASOURCE_ELASTICSEARCH_PASSWORD`: Elasticsearch password

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--config` | `../../config/config.yaml` | Path to ORBIT config file |
| `--count` | `1000` | Number of log records to generate |
| `--batch-size` | `100` | Records per bulk indexing batch |
| `--index` | `logs-app-demo` | Elasticsearch index name |
| `--use-ai` | `False` | Use AI for realistic messages |
| `--provider` | `openai` | AI provider (openai, anthropic, etc.) |
| `--days-back` | `7` | Time span for logs in days |
| `--error-rate` | `10.0` | Percentage of error logs (0-100) |

## Example Scenarios

### Development Testing (Fast)
```bash
# Generate 500 logs quickly without AI
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 500 \
    --index logs-app-dev
```

### Demo Dataset (Realistic)
```bash
# Generate 5000 realistic logs with AI
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 5000 \
    --index logs-app-demo \
    --use-ai \
    --provider anthropic \
    --days-back 14 \
    --error-rate 12
```

### Production-Like Dataset
```bash
# Generate 50000 logs spanning 90 days
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 50000 \
    --index logs-app-production \
    --days-back 90 \
    --error-rate 5 \
    --batch-size 1000
```

### High Error Rate Testing
```bash
# Generate logs with 30% error rate for testing
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 2000 \
    --index logs-app-errors \
    --error-rate 30 \
    --days-back 7
```

## Sample Queries

After generating data, test with these natural language queries:

### Error Analysis
```
"Show me recent error logs"
"Find errors from the last hour"
"What errors did user-abc123 encounter?"
"Show me errors in production"
```

### Service Analysis
```
"How many errors by service?"
"Which services have the most errors?"
"Show me error count per service"
```

### Performance Analysis
```
"Find slow API requests"
"Show me requests taking more than 2 seconds"
"Which endpoints are slow?"
```

### Time Series Analysis
```
"Show me error trends over the last 24 hours"
"Display error timeline"
"How have errors changed over time?"
```

## Generated Services

The script generates logs from these realistic microservices:
- auth-service
- user-service
- order-service
- payment-service
- inventory-service
- notification-service
- api-gateway
- data-pipeline
- search-service
- recommendation-service
- analytics-service

## Log Level Distribution

By default:
- **ERROR**: 10% (configurable via `--error-rate`)
- **WARN**: 10%
- **INFO**: 60%
- **DEBUG**: 20%

## Data Quality

### Without AI (`--use-ai` not set)
- Fast generation (~100-500 records/second)
- Template-based messages with realistic placeholders
- Good for large datasets and testing

### With AI (`--use-ai` flag)
- Slower generation (~5-20 records/second depending on provider)
- Highly realistic, varied messages
- Better for demos and presentations
- Uses 50% AI / 50% templates for efficiency

## Troubleshooting

### Connection Errors
```
Error: Failed to initialize Elasticsearch datasource
```
**Solution**: Check your credentials and node URL in `config/datasources.yaml`

### Authentication Errors
```
Error: Elasticsearch auth failed
```
**Solution**: Verify your environment variables:
```bash
echo $DATASOURCE_ELASTICSEARCH_USERNAME
echo $DATASOURCE_ELASTICSEARCH_PASSWORD
```

### SSL Certificate Errors
```
Error: SSL certificate verification failed
```
**Solution**: For Elastic Cloud, ensure `verify_certs: true` in config. For self-signed certs, set to `false`.

### Index Already Exists
The script will use the existing index. To start fresh:
```bash
# Delete the index first (careful!)
curl -X DELETE "https://your-instance.es.io:9200/logs-app-demo" \
    -u elastic:your-password
```

### Rate Limiting (AI Mode)
If you see rate limiting errors with AI providers:
```
⚠️ Rate limited (attempt 2/3), retrying in 2.5s...
```
**Solution**: The script automatically retries. For faster generation, use smaller batches or disable AI.

## Performance Tips

1. **Bulk Indexing**: Increase `--batch-size` for faster indexing (500-1000 for large datasets)
2. **Skip AI**: Omit `--use-ai` flag for 10-50x faster generation
3. **Parallel Generation**: Run multiple instances with different index names
4. **Index Settings**: Use `number_of_replicas: 0` for faster initial indexing

## Next Steps

After generating data:

1. **Enable the adapter** in `config/adapters.yaml`:
   ```yaml
   - name: "intent-elasticsearch-app-logs"
     enabled: true  # Change to true
   ```

2. **Update index pattern** to match your generated data:
   ```yaml
   config:
     index_pattern: "logs-app-*"  # Matches logs-app-demo, logs-app-production, etc.
   ```

3. **Test queries** through the ORBIT API:
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
       -H "Content-Type: application/json" \
       -H "X-API-Key: your-api-key" \
       -d '{
         "model": "intent-elasticsearch-app-logs",
         "messages": [{"role": "user", "content": "Show me recent error logs"}]
       }'
   ```

## Examples

### Quick Demo Setup
```bash
# 1. Set credentials
export DATASOURCE_ELASTICSEARCH_USERNAME=elastic
export DATASOURCE_ELASTICSEARCH_PASSWORD=your-password

# 2. Generate 1000 logs
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 1000 \
    --index logs-app-demo

# 3. Enable adapter in config/adapters.yaml
# 4. Start ORBIT server
# 5. Query: "Show me recent error logs"
```

### Production-Like Setup
```bash
# Generate comprehensive dataset
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 100000 \
    --index logs-app-production \
    --use-ai \
    --provider anthropic \
    --days-back 90 \
    --error-rate 5 \
    --batch-size 1000
```

## License

Same as ORBIT project license.
