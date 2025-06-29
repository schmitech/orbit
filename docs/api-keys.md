# API Key Management Utilities

This package provides utilities for managing API keys and interacting with the chat server API. It includes:

1. `orbit.py` - A command-line tool for creating and managing API keys and system prompts
2. `api_client.py` - A client library for sending chat messages using API keys

## Installation

```bash
# Install required dependencies
pip install requests python-dotenv
```

## API Key Manager

The API Key Manager utility allows you to create, test, and manage API keys and system prompts from the command line.

### API Key Management

```bash
# Create a new API key with a system prompt
python orbit.py --url http://localhost:3000 key create\
  --collection city \
  --name "City Assistant" \
  --prompt-file .examples/prompts/examples/city/city-assistant-normal-prompt.txt \
  --prompt-name "Municipal Assistant Prompt"

# List all API keys
python orbit.py --url http://localhost:3000 list

# Test an API key
python orbit.py --url http://localhost:3000 test --key YOUR_API_KEY

# Deactivate an API key
python orbit.py --url http://localhost:3000 deactivate --key YOUR_API_KEY

# Delete an API key
python orbit.py --url http://localhost:3000 delete --key YOUR_API_KEY

# Get API key status
python orbit.py --url http://localhost:3000 status --key YOUR_API_KEY
```

### System Prompt Management

```bash
# Create a new system prompt
python orbit.py --url http://localhost:3000 prompt create \
  --name "Support Assistant" \
  --file prompts/support.txt \
  --version "1.0"

# List all prompts
python orbit.py --url http://localhost:3000 prompt list

# Get a specific prompt
python orbit.py --url http://localhost:3000 prompt get --id PROMPT_ID

# Update a prompt
python orbit.py --url http://localhost:3000 prompt update \
  --id PROMPT_ID \
  --file prompts/updated.txt \
  --version "1.1"

# Delete a prompt
python orbit.py --url http://localhost:3000 prompt delete --id PROMPT_ID

# Associate a prompt with an API key
python orbit.py --url http://localhost:3000 prompt associate \
  --key YOUR_API_KEY \
  --prompt-id PROMPT_ID
```

## API Client

The API Client provides a convenient interface for sending chat messages to the server using API keys. The project is located under
clients/python, however for your convenience there is a pre-built package available:
```bash
pip install schmitech-orbit-client
orbit-chat --url http://localhost:3000 # Type 'hello' to chat with Ollama. No chat history yet, coming soon...
```

### Usage

```python
from chat_client import stream_chat

# Stream a chat message
response, timing_info = stream_chat(
    url="http://localhost:3000",
    message="Hello, how are you?",
    api_key="your-api-key-here",
    session_id=None,  # Optional, will generate UUID if not provided
    debug=False  # Optional, for debugging
)

# Print response
print(response)

# Print timing information if needed
if timing_info:
    print(f"Total time: {timing_info['total_time']:.3f}s")
    print(f"Time to first token: {timing_info['time_to_first_token']:.3f}s")

```

## Security Notes

1. API keys are sensitive credentials and should be handled securely
2. Consider using environment variables or secure credential storage instead of hardcoding API keys
3. In production, always use HTTPS to encrypt API keys in transit