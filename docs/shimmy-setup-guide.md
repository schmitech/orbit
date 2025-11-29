# Shimmy Setup Guide

This guide explains how to set up and use Shimmy as an inference provider in Orbit. Shimmy is a 4.8MB single-binary Rust inference server that provides 100% OpenAI-compatible endpoints for GGUF models.

## Overview

Shimmy is a lightweight, Python-free inference server that offers:
- **100% OpenAI-compatible API**: Drop-in replacement for OpenAI endpoints
- **Auto-discovery**: Automatically finds models in Hugging Face cache, Ollama models directory, and local directories
- **Hot model swap**: Switch between models without restarting
- **Single binary**: Only 4.8MB, no Python dependencies
- **Fast startup**: <100ms startup time
- **Multiple backends**: Supports CUDA, Vulkan, OpenCL, MLX (Apple Silicon), and CPU

## Installation

### Prerequisites

- Rust toolchain (for building from source) OR
- Pre-built binary from GitHub releases

### Installing Shimmy

#### Option 1: Install via Cargo (Recommended)

```bash
# Basic installation
cargo install shimmy

# With GPU support (CUDA)
cargo install shimmy --features llama-cuda

# With all features
cargo install shimmy --features gpu,moe
```

After installation, add Cargo's bin directory to your PATH:

```bash
# Add to ~/.zshrc or ~/.bashrc
export PATH="$HOME/.cargo/bin:$PATH"

# Reload your shell
source ~/.zshrc  # or source ~/.bashrc
```

#### Option 2: Download Pre-built Binary

Download the latest release from [Shimmy GitHub Releases](https://github.com/Michael-A-Kuykendall/shimmy/releases) and add it to your PATH.

#### Option 3: Build from Source

```bash
git clone https://github.com/Michael-A-Kuykendall/shimmy.git
cd shimmy
cargo build --release
```

### Verify Installation

```bash
# Check if shimmy is available
shimmy --version

# Check GPU support
shimmy gpu-info
```

## Starting the Server

### Basic Server Startup

```bash
# Auto-allocates port to avoid conflicts
shimmy serve

# Or use manual port binding
shimmy serve --bind 127.0.0.1:11435
```

The server will:
- Auto-discover models from:
  - `~/.cache/huggingface/hub/` (Hugging Face cache)
  - `~/.ollama/models/` (Ollama models)
  - `./models/` (Local directory)
  - `SHIMMY_BASE_GGUF` environment variable
- Start on the specified port (default: 11435)
- Display available models and endpoints

### Server Output Example

```
🎯 Shimmy v1.7.4
🔧 Backend: CPU (no GPU acceleration)
📦 Models: 10 available
🚀 Starting server on 127.0.0.1:11435
✅ Ready to serve requests
   • POST /api/generate (streaming + non-streaming)
   • GET  /health (health check + metrics)
   • GET  /v1/models (OpenAI-compatible)
```

## Model Management

### Listing Available Models

```bash
# List all discovered models
shimmy list

# Refresh model discovery
shimmy discover
```

### Model Auto-Discovery

Shimmy automatically discovers models from:

1. **Hugging Face Cache**: `~/.cache/huggingface/hub/`
2. **Ollama Models**: `~/.ollama/models/`
3. **Local Directory**: `./models/`
4. **Environment Variable**: `SHIMMY_BASE_GGUF=path/to/model.gguf`

### Downloading Models

```bash
# Download models that work out of the box
huggingface-cli download microsoft/Phi-3-mini-4k-instruct-gguf --local-dir ./models/
huggingface-cli download bartowski/Llama-3.2-1B-Instruct-GGUF --local-dir ./models/
```

## Configuration in Orbit

### Basic Configuration

Add Shimmy to your `config/inference.yaml`:

```yaml
inference:
  shimmy:
    enabled: true
    base_url: "http://localhost:11435"  # Shimmy server URL
    model: "phi3-lora"  # Model name (use shimmy list to see available models)
    api_key: null  # Optional - Shimmy doesn't require authentication
    
    # Generation parameters
    temperature: 0.4
    top_p: 0.9
    top_k: 50
    max_tokens: 4096
    repeat_penalty: 1.2
    
    # Context configuration
    context_window: 65536  # Shimmy supports large context windows
    stream: true
    
    # Stop sequences (optional)
    stop_tokens: []
    
    # Timeout configuration
    timeout:
      connect: 10000   # 10 seconds
      total: 120000    # 2 minutes
    
    # Retry configuration
    retry:
      enabled: true
      max_retries: 5
      initial_wait_ms: 2000
      max_wait_ms: 30000
      exponential_base: 2
```

### Using Shimmy as Default Provider

Set Shimmy as the default inference provider in `config/config.yaml`:

```yaml
general:
  inference_provider: "shimmy"
```

### Per-Adapter Configuration

You can also override the inference provider for specific adapters:

```yaml
adapters:
  - name: "my-adapter"
    inference_provider: "shimmy"
    model: "gemma-3-1b-it-q4-0"
```

## Testing the Integration

### 1. Verify Server is Running

```bash
# Check health endpoint
curl http://localhost:11435/health

# List available models
curl http://localhost:11435/v1/models
```

### 2. Test Chat Completions (Non-Streaming)

```bash
curl -s http://127.0.0.1:11435/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
        "model":"phi3-lora",
        "messages":[{"role":"user","content":"Say hi in 5 words."}],
        "max_tokens":8000,
        "stream":false
      }' | jq -r '.choices[0].message.content'
```

### 3. Test Chat Completions (Streaming)

```bash
curl -s http://127.0.0.1:11435/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
        "model":"phi3-lora",
        "messages":[{"role":"user","content":"Say hi in 5 words."}],
        "max_tokens":8000,
        "stream":true
      }' | grep '^data: ' | sed 's/^data: //' | jq -r '.choices[0].delta.content // empty' | tr -d '\n' && echo
```

### 4. Test from Orbit

Start your Orbit server and make a request to any adapter configured to use Shimmy.

## API Endpoints

Shimmy provides 100% OpenAI-compatible endpoints:

### 1. `/v1/chat/completions`
- **Purpose**: Chat-style interactions
- **Method**: POST
- **Format**: OpenAI-compatible chat format
- **Best for**: Conversational AI applications

### 2. `/v1/models`
- **Purpose**: List available models
- **Method**: GET
- **Format**: OpenAI-compatible models list
- **Best for**: Model discovery

### 3. `/health`
- **Purpose**: Health check and metrics
- **Method**: GET
- **Format**: JSON with server status
- **Best for**: Monitoring and health checks

### 4. `/api/generate`
- **Purpose**: Shimmy native API (non-OpenAI format)
- **Method**: POST
- **Format**: Shimmy-specific format
- **Best for**: Advanced usage

## Generation Parameters

You can customize generation using these parameters:

| Parameter | Description | Default | Range |
|-----------|-------------|---------|--------|
| temperature | Controls randomness | 0.7 | 0.0 to 2.0 |
| top_p | Nucleus sampling | 0.9 | 0.0 to 1.0 |
| top_k | Top-k sampling | 50 | 0 to infinity |
| max_tokens | Max tokens to generate | 4096 | 1 to infinity |
| repeat_penalty | Penalty for repeated tokens | 1.2 | 1.0 to infinity |
| stop | Stop sequences | [] | Array of strings |

Example with custom parameters:

```bash
curl -X POST http://localhost:11435/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "phi3-lora",
    "messages": [
      {"role": "user", "content": "Tell me a story"}
    ],
    "temperature": 0.9,
    "top_p": 0.95,
    "max_tokens": 256,
    "stream": false
  }'
```

## Response Format

### Chat Completion Response (Non-Streaming)

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "phi3-lora",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Response text here"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 10,
    "total_tokens": 15
  }
}
```

### Streaming Response Format

Streaming responses use Server-Sent Events (SSE) format:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":1234567890,"model":"phi3-lora","choices":[{"index":0,"delta":{"content":"Hello","role":null},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":1234567890,"model":"phi3-lora","choices":[{"index":0,"delta":{"content":" there","role":null},"finish_reason":null}]}

data: [DONE]
```

## Best Practices

1. **Model Selection**
   - Use smaller models (like `phi3-lora` or `gemma-3-1b-it-q4-0`) for quick testing
   - Larger models provide better quality but require more resources
   - Check available models with `shimmy list`

2. **Context Management**
   - Shimmy supports large context windows (up to 128K+ tokens)
   - Monitor token usage to stay within context limits
   - Use streaming for long generations

3. **Performance Optimization**
   - Enable GPU acceleration if available (use `--features llama-cuda` or `--features mlx` for Apple Silicon)
   - Use appropriate model quantization (Q4_0, Q4_K_M, etc.)
   - Consider batch processing for multiple requests

4. **Generation Quality**
   - Start with default parameters
   - Adjust temperature for creativity vs. consistency
   - Use repeat_penalty to reduce repetition
   - Experiment with top_p and top_k for different sampling strategies

5. **Error Handling**
   - Implement proper timeout handling
   - Check for connection errors (server might be starting)
   - Handle API errors gracefully
   - Use retry configuration in Orbit

## Troubleshooting

### Common Issues

1. **Server won't start**
   - Check if port 11435 is available: `lsof -i :11435`
   - Verify shimmy is in PATH: `which shimmy`
   - Check for permission issues

2. **No models found**
   - Run `shimmy discover` to refresh model discovery
   - Check model directories exist:
     - `~/.cache/huggingface/hub/`
     - `~/.ollama/models/`
     - `./models/`
   - Verify models are in GGUF format

3. **Connection refused**
   - Ensure Shimmy server is running: `shimmy serve`
   - Check the base_url in config matches the server port
   - Verify firewall settings

4. **Model not found**
   - List available models: `shimmy list`
   - Use exact model name from the list
   - Check model file exists and is readable

5. **Slow responses**
   - Enable GPU acceleration if available
   - Use smaller models for faster inference
   - Reduce max_tokens for quicker responses
   - Check system resources (CPU, memory)

6. **Poor generation quality**
   - Adjust temperature and sampling parameters
   - Check model quality and quantization level
   - Verify prompt formatting
   - Try a different model

### Debugging

Enable verbose logging in Orbit to see detailed Shimmy API calls:

```yaml
logging:
  level: "DEBUG"
```

Check Shimmy server logs for detailed error messages.

## Integration Examples

### Python Integration

```python
import requests

def chat_completion(prompt, model="phi3-lora", temperature=0.7):
    response = requests.post(
        "http://localhost:11435/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": False
        }
    )
    return response.json()["choices"][0]["message"]["content"]
```

### JavaScript/TypeScript Integration

```javascript
async function chatCompletion(prompt, model = "phi3-lora", temperature = 0.7) {
    const response = await fetch('http://localhost:11435/v1/chat/completions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            model: model,
            messages: [{ role: 'user', content: prompt }],
            temperature: temperature,
            stream: false
        })
    });
    const data = await response.json();
    return data.choices[0].message.content;
}
```

### Using OpenAI SDK (Recommended)

Since Shimmy is 100% OpenAI-compatible, you can use the OpenAI SDK directly:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11435/v1",
    api_key="not-needed"  # Shimmy doesn't require authentication
)

response = client.chat.completions.create(
    model="phi3-lora",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

## Advanced Features

### GPU Acceleration

Shimmy supports multiple GPU backends:

```bash
# CUDA (NVIDIA GPUs)
cargo install shimmy --features llama-cuda

# Vulkan (Cross-platform GPUs)
cargo install shimmy --features llama-vulkan

# OpenCL (AMD/Intel/Others)
cargo install shimmy --features llama-opencl

# MLX (Apple Silicon)
cargo install shimmy --features mlx

# All features
cargo install shimmy --features gpu,moe
```

Check GPU support:

```bash
shimmy gpu-info
```

### Hot Model Swapping

Shimmy supports switching models without restarting:

```bash
# List available models
shimmy list

# The model name in your request determines which model is used
# No server restart needed!
```

### MOE (Mixture of Experts) Support

For large models, enable MOE CPU offloading:

```bash
shimmy serve --cpu-moe --n-cpu-moe 8
```

## Comparison with Other Providers

| Feature | Shimmy | Ollama | llama.cpp |
|---------|--------|--------|-----------|
| Binary Size | 4.8MB | 680MB | 89MB |
| Startup Time | <100ms | 5-10s | 1-2s |
| Memory Usage | 50MB | 200MB+ | 100MB |
| OpenAI API | 100% | Partial | Via server |
| Auto-discovery | Yes | Yes | No |
| Hot model swap | Yes | Yes | No |
| Python-free | Yes | No | No |

## Security Considerations

1. **Local Server**
   - Shimmy runs locally by default
   - No authentication required (local use)
   - Bind to `127.0.0.1` for local-only access

2. **Network Security**
   - If exposing to network, consider adding authentication
   - Use firewall rules to restrict access
   - Monitor resource usage

3. **Model Security**
   - Validate input prompts
   - Monitor resource usage
   - Implement proper error handling

## Additional Resources

- [Shimmy GitHub Repository](https://github.com/Michael-A-Kuykendall/shimmy)
- [Shimmy Documentation](https://github.com/Michael-A-Kuykendall/shimmy#readme)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference) (compatible with Shimmy)

## See Also

- [Llama.cpp Server Guide](llama-cpp-server-guide.md) - Alternative local inference server
- [Ollama Installation Manual](ollama-installation-manual.md) - Another local inference option
- [Configuration Guide](configuration.md) - General Orbit configuration

