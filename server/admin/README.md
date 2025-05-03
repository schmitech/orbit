# API Key Management Utilities

This package provides utilities for managing API keys and interacting with the chat server API. It includes:

1. `api_key_manager.py` - A command-line tool for creating and managing API keys and system prompts
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
python api_key_manager.py --url http://localhost:3000 create \
  --collection city \
  --name "City Assistant" \
  --prompt-file ../prompts/examples/city/city-assistant-normal-prompt.txt \
  --prompt-name "Municipal Assistant Prompt"

# List all API keys
python api_key_manager.py --url http://localhost:3000 list

# Test an API key
python api_key_manager.py --url http://localhost:3000 test --key YOUR_API_KEY

# Deactivate an API key
python api_key_manager.py --url http://localhost:3000 deactivate --key YOUR_API_KEY

# Delete an API key
python api_key_manager.py --url http://localhost:3000 delete --key YOUR_API_KEY

# Get API key status
python api_key_manager.py --url http://localhost:3000 status --key YOUR_API_KEY
```

### System Prompt Management

```bash
# Create a new system prompt
python api_key_manager.py --url http://localhost:3000 prompt create \
  --name "Support Assistant" \
  --file prompts/support.txt \
  --version "1.0"

# List all prompts
python api_key_manager.py --url http://localhost:3000 prompt list

# Get a specific prompt
python api_key_manager.py --url http://localhost:3000 prompt get --id PROMPT_ID

# Update a prompt
python api_key_manager.py --url http://localhost:3000 prompt update \
  --id PROMPT_ID \
  --file prompts/updated.txt \
  --version "1.1"

# Delete a prompt
python api_key_manager.py --url http://localhost:3000 prompt delete --id PROMPT_ID

# Associate a prompt with an API key
python api_key_manager.py --url http://localhost:3000 prompt associate \
  --key YOUR_API_KEY \
  --prompt-id PROMPT_ID
```

## API Client

The API Client provides a convenient interface for sending chat messages to the server using API keys.

### Usage

```python
from api_client import ChatApiClient

# Create client instance
client = ChatApiClient(server_url="http://localhost:3001", api_key="your-api-key-here")

# Send chat message
response = client.chat("Hello, how are you?")
print(response["response"])

# Stream chat message
for chunk in client.chat("Tell me a story", stream=True):
    print(chunk, end="", flush=True)

# Check server health
health = client.health()
print(health)
```

### Command-line Interface

The API Client also includes a simple command-line interface for testing:

```bash
# Send a chat message
python api_client.py --server http://localhost:3001 --key YOUR_API_KEY --message "Hello"

# Stream a chat message
python api_client.py --server http://localhost:3001 --key YOUR_API_KEY --message "Tell me a story" --stream

# Check server health
python api_client.py --server http://localhost:3001 --key YOUR_KEY --health
```

### Configuration

Like the API Key Manager, you can configure the API Client using command-line arguments, environment variables, or a `.env` file:

```
API_SERVER_URL=http://localhost:3001
API_KEY=your-api-key-here
```

## Security Notes

1. API keys are sensitive credentials and should be handled securely
2. Consider using environment variables or secure credential storage instead of hardcoding API keys
3. In production, always use HTTPS to encrypt API keys in transit