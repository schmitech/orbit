# API Key Management Utilities

This package provides utilities for managing API keys and interacting with the chat server API. It includes:

1. `api_key_manager.py` - A command-line tool for creating and managing API keys
2. `api_client.py` - A client library for sending chat messages using API keys

## Installation

```bash
# Install required dependencies
pip install requests python-dotenv
```

## API Key Manager

The API Key Manager utility allows you to create, test, and deactivate API keys from the command line.

### Usage

```bash
# Create a new API key
python api_key_manager.py create --collection client_collection --name "Client Name" --notes "Optional notes"

# List all API keys
python api_key_manager.py list

# Test an API key
python api_key_manager.py test --key YOUR_API_KEY

# Deactivate an API key
python api_key_manager.py deactivate --key YOUR_API_KEY
```

### Configuration

You can configure the API Key Manager using:

1. Command-line arguments
2. Environment variables
3. `.env` file in the current directory

Example `.env` file:
```
API_SERVER_URL=http://localhost:3001
API_ADMIN_TOKEN=your-admin-token-if-needed
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
python api_client.py --server http://localhost:3001 --key YOUR_API_KEY --health
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
4. The API Key Manager saves keys to a `.api_keys` file for convenience - ensure this file is properly secured