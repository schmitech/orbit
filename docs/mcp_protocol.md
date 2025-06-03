# MCP Protocol Support

ORBIT includes support for the Model Context Protocol (MCP) using JSON-RPC 2.0 format. This enables compatibility with MCP-compatible clients and tools.

## Overview

The MCP (Model Context Protocol) implementation in ORBIT follows JSON-RPC 2.0 specifications and uses a `tools/call` method with a `chat` tool for message handling. This protocol provides a standardized way to interact with the AI server.

## Configuration

The MCP protocol is **always enabled** on the `/v1/chat` endpoint. No additional configuration is required.

## Endpoint

The MCP endpoint is available at:

```
POST /v1/chat
```

## Request Format

MCP requests use JSON-RPC 2.0 format with the following structure:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "chat",
    "arguments": {
      "messages": [
        {
          "role": "user",
          "content": "Your message here"
        }
      ],
      "stream": true
    }
  },
  "id": "unique-request-id"
}
```

### Fields

- `jsonrpc`: Always "2.0" (JSON-RPC version)
- `method`: Always "tools/call" for chat requests
- `params`: Parameters object containing:
  - `name`: Always "chat" for chat tool
  - `arguments`: Chat arguments containing:
    - `messages`: Array of message objects with `role` and `content`
    - `stream`: Boolean indicating whether to stream the response
- `id`: Unique identifier for the request (string)

### Message Format

Messages in the conversation history use this simple format:
```json
{
  "role": "user|assistant",
  "content": "Message text"
}
```

## Response Format

### Non-Streaming Response

For non-streaming requests (`stream: false`), the response follows JSON-RPC 2.0 format:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "output": {
      "messages": [
        {
          "role": "assistant",
          "content": "The AI's response text"
        }
      ]
    },
    "sources": [
      "Optional array of sources if using RAG"
    ]
  },
  "id": "unique-request-id"
}
```

### Streaming Response

For streaming requests (`stream: true`), the response is sent as Server-Sent Events (SSE) with JSON-RPC format chunks:

```
data: {"jsonrpc":"2.0","result":{"chunk":"First"},"id":"unique-request-id"}

data: {"jsonrpc":"2.0","result":{"chunk":" part"},"id":"unique-request-id"}

data: {"jsonrpc":"2.0","result":{"chunk":" of response"},"id":"unique-request-id"}

data: [DONE]
```

### Error Response

When an error occurs, the response follows JSON-RPC 2.0 error format:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "Method not found: invalid_method"
  },
  "id": "unique-request-id"
}
```

Common error codes:
- `-32601`: Method not found (unsupported method or tool)
- `-32602`: Invalid params (missing or invalid parameters)
- `-32603`: Internal error (server-side error)

## Example Usage

### cURL

```bash
curl -X POST "http://localhost:3000/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -H "X-Session-ID: session_123" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "chat",
      "arguments": {
        "messages": [
          {
            "role": "user",
            "content": "What is the capital of France?"
          }
        ],
        "stream": false
      }
    },
    "id": "req_123"
  }'
```

### Python

```python
import requests
import json
import uuid

# API endpoint
url = "http://localhost:3000/v1/chat"

# Request data
request_data = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "chat",
        "arguments": {
            "messages": [
                {
                    "role": "user",
                    "content": "What is the capital of France?"
                }
            ],
            "stream": False
        }
    },
    "id": str(uuid.uuid4())
}

# Headers
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your_api_key",
    "X-Session-ID": "session_123"
}

# Send request
response = requests.post(url, json=request_data, headers=headers)

# Print response
print(json.dumps(response.json(), indent=2))
```

### Python Streaming

```python
import requests
import json
import uuid
import sseclient

# API endpoint
url = "http://localhost:3000/v1/chat"

# Request data
request_data = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "chat",
        "arguments": {
            "messages": [
                {
                    "role": "user",
                    "content": "What is the capital of France?"
                }
            ],
            "stream": True
        }
    },
    "id": str(uuid.uuid4())
}

# Headers
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your_api_key",
    "X-Session-ID": "session_123"
}

# Send request with streaming
response = requests.post(url, json=request_data, headers=headers, stream=True)
client = sseclient.SSEClient(response)

# Process the streamed response
for event in client.events():
    if event.data == "[DONE]":
        break
    try:
        chunk = json.loads(event.data)
        if "result" in chunk and "chunk" in chunk["result"]:
            print(chunk["result"]["chunk"], end="", flush=True)
    except json.JSONDecodeError:
        pass

print()  # Add final newline
```

## Required Headers

- `Content-Type: application/json` - Required for JSON requests
- `X-API-Key: your_api_key` - Required for authentication
- `X-Session-ID: session_id` - Required for conversation tracking

## Client Libraries

Since this implementation uses JSON-RPC 2.0, you can adapt existing JSON-RPC clients or create simple HTTP clients as shown in the examples above.

## Testing

Test the MCP protocol implementation using the provided test script:

```bash
cd server
python ./tests/test_mcp_client.py --api-key=your_api_key --session-id=session_123 --url="http://localhost:3000/v1/chat"
```

Available test options:
- `--stream`: Test streaming responses
- `--tools`: Test tool calling (if implemented)
- `--session-id`: Specify session ID (auto-generated if not provided)