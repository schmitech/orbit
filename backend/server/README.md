# FastAPI Chat Server

A modular FastAPI server that provides a chat endpoint with Ollama LLM integration and Chroma vector database for retrieval augmented generation.

## Features

- Chat endpoint with context-aware responses
- Health check endpoint
- ChromaDB integration for document retrieval
- Ollama integration for embeddings and LLM responses
- Safety check for user queries
- Streaming responses with proper formatting
- Text summarization for long responses
- Comprehensive logging system
- HTTPS support with proper certificate management
- Production-ready with health checks and graceful shutdown

## Project Structure

The project has been modularized for better maintainability:

```
chatbot/
├── __init__.py
├── config/           # Configuration management
│   ├── __init__.py
│   └── config_manager.py
├── clients/          # External service clients
│   ├── __init__.py
│   ├── chroma_client.py
│   └── ollama_client.py
├── services/         # Business logic services
│   ├── __init__.py
│   ├── chat_service.py
│   ├── health_service.py
│   ├── guardrail_service.py
│   └── summarization_service.py
├── utils/            # Utility functions
│   ├── __init__.py
│   └── text_utils.py
├── models/           # Data models and schemas
│   ├── __init__.py
│   └── schema.py
└── server.py         # Main FastAPI application
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/chatbot-server.git
cd chatbot-server
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `config.yaml` file in one of the following locations:
   - `../config/config.yaml`
   - `../../backend/config/config.yaml`
   - `./config.yaml`

Example config:
```yaml
general:
  port: 3000
  verbose: false
  https:
    enabled: false
    port: 3443
    cert_file: ./cert.pem
    key_file: ./key.pem

logging:
  level: "INFO"  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
  file:
    enabled: true
    directory: "logs"
    filename: "server.log"
    max_size_mb: 10
    backup_count: 30
    rotation: "midnight"  # Options: midnight, h (hourly), d (daily)
    format: "json"  # Options: json, text
  console:
    enabled: true
    format: "text"  # Options: json, text
  capture_warnings: true
  propagate: false

elasticsearch:
  enabled: true
  node: 'https://localhost:9200'
  index: 'chatbot'
  auth:
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

safety:
  mode: "fuzzy"  # Options: strict, fuzzy, disabled
  model: "gemma3:12b"
  max_retries: 3
  retry_delay: 1.0
  request_timeout: 15
  allow_on_timeout: false  # Set to true to allow queries if safety check times out
  temperature: 0.0  # Use 0 for deterministic response
  top_p: 1.0
  top_k: 1
  num_predict: 20  # Limit response length for safety checks
  stream: false
  repeat_penalty: 1.1

chroma:
  host: localhost
  port: 8000
  collection: qa-chatbot
  confidence_threshold: 0.85
  relevance_threshold: 0.5

ollama:
  base_url: http://localhost:11434
  temperature: 0.7
  top_p: 0.9
  top_k: 40
  repeat_penalty: 1.1
  num_predict: 1024
  model: llama2
  embed_model: nomic-embed-text
  # Summarization settings
  summarization_model: gemma3:4b
  max_summary_length: 100
  enable_summarization: true
```

## Running the Server

Start the server using Uvicorn:

```bash
uvicorn server:app --reload
```

Or run the server script directly:
```bash
python server.py
```

The server will be available at http://localhost:3000 by default.

## API Endpoints

### Chat Endpoint

```
POST /chat
```

Request body:
```json
{
  "message": "Your question or message here",
  "voiceEnabled": false,
  "stream": true
}
```

Response:
```json
{
  "response": "The answer to your question...",
  "audio": null
}
```

For streaming responses, set `stream: true` and use server-sent events (SSE) handling in your client.

### Health Check

```
GET /health
```

Response:
```json
{
  "status": "ok",
  "components": {
    "server": {
      "status": "ok"
    },
    "chroma": {
      "status": "ok"
    },
    "llm": {
      "status": "ok"
    }
  }
}
```

## HTTPS Configuration

The server supports HTTPS connections using TLS (Transport Layer Security). Here's how to configure it:

### Using Let's Encrypt with Certbot

1. Install Certbot:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install certbot
```

2. If your server runs on port 3000, you'll need to route requests from port 80 to port 3000 for the certificate verification:
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 3000
```

3. Obtain TLS certificate using DNS challenge (recommended for production):
```bash
sudo certbot certonly --manual --preferred-challenges http -d your-domain.com
```

4. Update your `config.yaml`:
```yaml
general:
  https:
    enabled: true
    port: 3443
    cert_file: "/etc/letsencrypt/live/your-domain.com/fullchain.pem"
    key_file: "/etc/letsencrypt/live/your-domain.com/privkey.pem"
```

5. Set proper permissions for the certificate files:
```bash
sudo chown -R $USER:$USER /etc/letsencrypt/live/your-domain.com
sudo chown -R $USER:$USER /etc/letsencrypt/archive/your-domain.com
sudo chmod -R 755 /etc/letsencrypt/live
sudo chmod -R 755 /etc/letsencrypt/archive
sudo chmod 644 /etc/letsencrypt/archive/your-domain.com/*.pem
```

6. Configure your firewall/security group to allow:
   - Port 443 (HTTPS)
   - Port 80 (for certificate verification)

7. Test your HTTPS setup:
```bash
curl -I https://your-domain.com:3443/health
```

Note: Let's Encrypt certificates expire after 90 days. Set up automatic renewal:
```bash
# Add to crontab
0 0 * * * certbot renew --quiet
```

### Development with Self-Signed Certificates

For development and testing, you can use self-signed certificates:

1. Generate self-signed certificate:
```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

2. Update your `config.yaml`:
```yaml
general:
  https:
    enabled: true
    port: 3443
    cert_file: "./cert.pem"
    key_file: "./key.pem"
```

3. For development clients, you may need to disable certificate verification:
```python
# Python example
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
```

### Important Notes

1. **Production Use**:
   - Always use a proper domain name
   - Use Let's Encrypt certificates
   - Never disable certificate verification
   - Keep certificates up to date

2. **Security Considerations**:
   - Keep private keys secure
   - Use strong key sizes (4096 bits recommended)
   - Regularly rotate certificates
   - Monitor certificate expiration

3. **Troubleshooting**:
   - Check certificate permissions
   - Verify firewall rules
   - Check server logs for SSL errors
   - Test with `curl -v` for detailed SSL information

# Reranker Service

The Reranker Service enhances retrieval accuracy in the Open Inference Platform by providing a cross-encoder style reranking step. This improves the precision of context provided to the LLM for higher quality responses.

## Overview

In traditional RAG systems, retrieval occurs in a single step using vector similarity search. While efficient, this can sometimes miss relevant documents or include irrelevant ones. Reranking adds a second pass that more thoroughly evaluates relevance, leading to better retrieval results.

## How It Works

1. **Initial Retrieval**: Documents are first retrieved using ChromaDB vector similarity search
2. **Reranking**: Each retrieved document is evaluated against the query using a cross-encoder approach
3. **Score Refinement**: Documents are rescored and reordered based on their relevance to the query
4. **Result Filtering**: Only the top N most relevant documents are kept

## Configuration

Enable and configure reranking in your `config.yaml` file:

```yaml
reranker:
  enabled: true                   # Set to true to enable reranking
  model: "gemma3:4b"              # Model to use for reranking (smaller models work well)
  batch_size: 5                   # Number of documents to process in parallel
  temperature: 0.0                # Use 0 for deterministic scoring
  top_n: 3                        # Number of documents to keep after reranking
```

## Benefits

- **Higher Precision**: Reranking can significantly improve the relevance of retrieved documents
- **Better Context**: LLMs receive more relevant context for generating responses
- **Reduced Hallucination**: With better context, the LLM is less likely to hallucinate information
- **Improved Answer Accuracy**: More accurate and on-point responses to user queries

## Performance Considerations

Reranking adds computation time to the retrieval process. Consider these factors:

- Use a smaller/faster model for reranking than your main LLM
- Balance retrieval time against improved answer quality
- For very latency-sensitive applications, consider keeping `enabled: false`

## Example Prompt Format

The reranker uses this prompt format to score document relevance:

```
Rate the relevance of the following document to the query on a scale from 0 to 10, 
where 0 means completely irrelevant and 10 means perfectly relevant.
Return only a number (0-10) without any explanations.

QUERY: {user_query}

DOCUMENT: {document_content}

RELEVANCE SCORE (0-10):
``` 

## Logging

The application implements a comprehensive logging system:

1. **Filesystem Logging**
   - Logs are stored in the `logs` directory
   - Uses daily rotation
   - Each log file is limited to 10MB
   - Logs are retained for 30 days
   - Includes all chat interactions, errors, and system status
   - Supports both JSON and text formats

2. **Elasticsearch Logging (Optional)**
   - Enabled/disabled via `elasticsearch.enabled` in config
   - Requires valid credentials in environment variables
   - Falls back to filesystem-only logging if Elasticsearch is unavailable

## Running as a Service

### Using Systemd (Recommended)

Create a systemd service file:

```bash
sudo vim /etc/systemd/system/chatbot.service
```

Add this content:

```bash
[Unit]
Description=Chatbot FastAPI Server
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/your/project
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=3
StandardOutput=append:/var/log/chatbot.log
StandardError=append:/var/log/chatbot.error.log

[Install]
WantedBy=multi-user.target
```

Manage the service:
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable the service
sudo systemctl enable chatbot

# Start the service
sudo systemctl start chatbot

# Check status
sudo systemctl status chatbot
```

## Dependencies

- FastAPI: Web framework
- Uvicorn: ASGI server
- Chromadb: Vector database
- Langchain-Ollama: Embeddings and LLM wrapper
- Pydantic: Data validation
- PyYAML: Configuration parsing
- aiohttp: Async HTTP client
- python-json-logger: JSON logging support

## License

[Apache 2.0](LICENSE)

## Safety Service

The Safety Service provides configurable guardrails for user queries using LLM-based verification. It helps prevent inappropriate or harmful content from being processed by the system.

### Safety Modes

The service supports three different safety modes:

1. **Strict Mode** (default)
   - Most restrictive mode
   - Only accepts exact matches of "SAFE: true" (with or without quotes)
   - Used when safety_mode is not specified or set to 'strict'

2. **Fuzzy Mode**
   - More lenient but still maintains safety checks
   - Accepts variations of safe responses
   - Common patterns include:
     - "safe: true"
     - "safe:true"
     - "safe - true"
     - "safe = true"
     - "\"safe\": true"
     - "safe\"=true"
     - "\"safe: true\""

3. **Disabled Mode**
   - Completely bypasses safety checks
   - Always returns `True` for safety checks
   - Use with caution in production environments

### Configuration

Configure safety settings in your `config.yaml`:

```yaml
safety:
  mode: "fuzzy"  # Options: strict, fuzzy, disabled
  model: "gemma3:12b"
  max_retries: 3
  retry_delay: 1.0
  request_timeout: 15
  allow_on_timeout: false  # Set to true to allow queries if safety check times out
  temperature: 0.0  # Use 0 for deterministic response
  top_p: 1.0
  top_k: 1
  num_predict: 20  # Limit response length for safety checks
  stream: false
  repeat_penalty: 1.1
```

### Benefits

- **Configurable Safety**: Choose the appropriate safety level for your use case
- **Flexible Implementation**: Supports different safety check strategies
- **Reliable Fallbacks**: Includes retry mechanisms and timeout handling
- **Detailed Logging**: Verbose mode provides insight into safety check decisions

### Performance Considerations

- Safety checks add latency to each query
- Use appropriate timeout settings based on your requirements
- Consider using a smaller model for safety checks to reduce latency
- Balance safety with performance based on your use case