# MCP Protocol Support

The Open Inference Server now includes support for the Message Content Protocol (MCP), allowing for compatibility with a wide range of clients and tools that use this protocol format.

## Overview

MCP (Message Content Protocol) is a standardized format for communication between LLM clients and servers. It follows the format used by many popular LLM providers, making it easy to integrate with existing tools and SDKs that already support this protocol.

## Configuration

To enable MCP protocol support, add the following setting to your `config.yaml` file:

```yaml
general:
  # Other general settings...
  mcp_protocol: true  # Set to true to enable MCP protocol
```

## Endpoint

When enabled, the MCP endpoint is available at:

```
POST /v1/chat
```

## Request Format

MCP requests follow this structure:

```json
{
  "messages": [
    {
      "id": "msg_1234567890",
      "object": "thread.message",
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Your message here"
        }
      ],
      "created_at": 1683753347
    }
  ],
  "stream": true
}
```

### Fields

- `messages`: Array of message objects in the conversation
  - `id`: Unique identifier for the message
  - `object`: Object type (always "thread.message")
  - `role`: Either "user" or "assistant"
  - `content`: Array of content objects
    - `type`: Content type (currently only "text" is supported)
    - `text`: The actual message text
  - `created_at`: Unix timestamp
- `stream`: Boolean indicating whether to stream the response

## Response Format

### Non-Streaming Response

For non-streaming requests (`stream: false`), the response structure is:

```json
{
  "id": "resp_1234567890",
  "object": "thread.message",
  "created_at": 1683753348,
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "The complete response text"
    }
  ]
}
```

### Streaming Response

For streaming requests (`stream: true`), the response is sent as a series of Server-Sent Events (SSE) chunks:

```
data: {"id":"resp_1234567890","object":"thread.message.delta","created_at":1683753348,"delta":{"role":"assistant","content":[{"type":"text","text":"The"}]}}

data: {"id":"resp_1234567890","object":"thread.message.delta","created_at":1683753348,"delta":{"content":[{"type":"text","text":" complete"}]}}

data: {"id":"resp_1234567890","object":"thread.message.delta","created_at":1683753348,"delta":{"content":[{"type":"text","text":" response"}]}}

data: {"id":"resp_1234567890","object":"thread.message.delta","created_at":1683753348,"delta":{"content":[{"type":"text","text":" text"}]}}

data: [DONE]
```

Each chunk includes:
- `id`: The same ID throughout the stream
- `object`: Always "thread.message.delta" for streaming chunks
- `created_at`: Unix timestamp
- `delta`: Contains the changes to apply to the response
  - `role`: Only in the first chunk
  - `content`: Array of content objects with the text deltas

## Example Usage

### cURL

```bash
curl -X POST "http://localhost:3000/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "messages": [
      {
        "id": "msg_1234567890",
        "object": "thread.message",
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "What is the capital of France?"
          }
        ],
        "created_at": 1683753347
      }
    ],
    "stream": false
  }'
```

### Python

```python
import requests
import json
import time
import uuid

# API endpoint
url = "http://localhost:3000/v1/chat"

# Request data
request_data = {
    "messages": [
        {
            "id": str(uuid.uuid4()),
            "object": "thread.message",
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What is the capital of France?"
                }
            ],
            "created_at": int(time.time())
        }
    ],
    "stream": False
}

# Headers
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your_api_key"
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
import time
import uuid
import sseclient

# API endpoint
url = "http://localhost:3000/v1/chat"

# Request data
request_data = {
    "messages": [
        {
            "id": str(uuid.uuid4()),
            "object": "thread.message",
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What is the capital of France?"
                }
            ],
            "created_at": int(time.time())
        }
    ],
    "stream": True
}

# Headers
headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your_api_key"
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
        # Process the chunk
        if "delta" in chunk and "content" in chunk["delta"]:
            for content in chunk["delta"]["content"]:
                if content["type"] == "text":
                    print(content["text"], end="", flush=True)
    except json.JSONDecodeError:
        pass

print()  # Add final newline
```

## Client Libraries

Since the MCP protocol follows a standard format, you can use client libraries that support similar APIs:

- Python libraries like `openai`, `anthropic`, or `litellm` can be adapted to work with this endpoint
- JavaScript libraries like `@langchain/openai` can also be adapted

## Testing

The MCP protocol implementation includes comprehensive unit tests that verify:

1. Non-streaming requests and responses
2. Streaming requests and responses
3. Error handling and validation
4. Configuration-based enabling/disabling

Run the tests with:

```bash
cd server
python ./tests/test_mcp_client.py --api-key=orbit_api_key --url="http://localhost:3000/v1/chat"
```