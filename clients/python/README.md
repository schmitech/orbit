# Orbit Client

A Python client for interacting with Orbit chat servers. This client provides a command-line interface for chatting with Orbit servers, supporting MCP protocol.

### GitHub Project

https://github.com/schmitech/orbit/tree/main/clients/python

## Build and Test Before Publishing

Before publishing to PyPI, you should test your package locally. Here's how:

1. Build the package locally:
```bash
# Install build tools if not already installed
pip install build

# Build the package
python -m build
```

2. Install the package in development mode:
```bash
# Install in editable mode
pip install -e .

# Or install the built wheel directly
pip install dist/schmitech_orbit_client-*.whl
```

3. Test the CLI:
```bash
# Test basic functionality
orbit-chat --url http://localhost:3000

# Test with debug mode
orbit-chat --url http://localhost:3000 --debug

# Test with API key
orbit-chat --url http://localhost:3000 --api-key your-test-key
```

4. Uninstall test version:
```bash
pip uninstall schmitech-orbit-client
```

## Publishing Package:

To build the package from source:

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Upload to PyPI (requires PyPI account)
python -m twine upload dist/*
```

### Removing the Package

To remove the package from PyPI:

```bash
# Install twine if not already installed
pip install twine

# Delete specific version
twine delete schmitech-orbit-client==0.1.0

# Or delete all versions
twine delete schmitech-orbit-client
```

Note: Once a package version is deleted, it cannot be restored. The package name becomes available again after 30 days.

## Usage

After installation, you can use the client in two ways:

### 1. Command-line Interface

The simplest way to use the client is through the command-line interface:

```bash
# Basic usage with default settings
orbit-chat --url http://your-server:3000

# Advanced usage with all options
orbit-chat --url http://your-server:3000 \
           --api-key your-api-key \
           --debug \
           --show-timing
```

#### Command-line Options

- `--url`: Chat server URL (default: http://localhost:3000)
- `--api-key`: API key for authentication
- `--debug`: Enable debug mode to see request/response details
- `--show-timing`: Show latency timing information

#### Interactive Features

- Use up/down arrow keys to navigate through chat history
- Type `exit` or `quit` to end the conversation
- Press Ctrl+C to interrupt the current response
- Chat history is saved in `~/.orbit_client_history/chat_history`

### 2. Python Module

You can also use the client in your Python code:

```python
from schmitech_orbit_client import stream_chat

# Basic usage
response, timing_info = stream_chat(
    url="http://your-server:3000",
    message="Hello, how are you?"
)

# Advanced usage with all options
response, timing_info = stream_chat(
    url="http://your-server:3000",
    message="Hello, how are you?",
    api_key="your-api-key",  # optional
    debug=True
)

# The response contains:
# - response: The full text response from the server
# - timing_info: Dictionary with timing metrics
#   - total_time: Total request time
#   - time_to_first_token: Time until first response token
```

## Features

- **Interactive CLI**: Command-line interface with history navigation
- **Protocol Support**: MCP protocol format
- **Real-time Streaming**: Responses appear gradually, character by character
- **Colored Output**: Better readability with syntax highlighting
- **Debug Mode**: Detailed request/response information for troubleshooting
- **Performance Metrics**: Latency timing information
- **Authentication**: API key support for secure communication
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Unicode Support**: Full support for non-English characters

## Examples

### Basic Chat Session
```bash
$ orbit-chat --url http://localhost:3000
Welcome to the Orbit Chat Client!
Server URL: http://localhost:3000
Type 'exit' or 'quit' to end the conversation.
You can use arrow keys to navigate, up/down for history.

You: Hello, how are you?
Assistant: I'm doing well, thank you for asking! How can I help you today?

You: exit
Goodbye!
```

### Debug Mode
```bash
$ orbit-chat --url http://localhost:3000 --debug
Debug - Request:
{
  "message": "Hello",
  "stream": true
}
Debug - Received:
{
  "text": "Hi there!"
}
```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 