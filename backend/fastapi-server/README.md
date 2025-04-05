# FastAPI Chat Server

A modular FastAPI server that provides a chat endpoint with Ollama LLM integration and Chroma vector database for retrieval augmented generation.

## Features

- Chat endpoint with context-aware responses
- Health check endpoint
- ChromaDB integration for document retrieval
- Ollama integration for embeddings and LLM responses
- Safety check for user queries
- Streaming responses with proper formatting

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
│   └── health_service.py
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

chroma:
  host: localhost
  port: 8000
  collection: qa-chatbot
  confidence_threshold: 0.85

ollama:
  base_url: http://localhost:11434
  temperature: 0.7
  top_p: 0.9
  top_k: 40
  repeat_penalty: 1.1
  num_predict: 1024
  model: llama2
  embed_model: nomic-embed-text
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

## Dependencies

- FastAPI: Web framework
- Uvicorn: ASGI server
- Chromadb: Vector database
- Langchain-Ollama: Embeddings and LLM wrapper
- Pydantic: Data validation
- PyYAML: Configuration parsing

## License

[Apache 2.0](LICENSE)