# Llama.cpp Server Usage Guide

## Overview
This guide provides comprehensive instructions for using the llama.cpp server to run and test GGUF models. The server provides both a web interface and REST API endpoints for interacting with your models.

## Prerequisites
- Built llama.cpp (server binary should be in `llama.cpp/bin/llama-server`)
- A GGUF model file

## Starting the Server

Basic server startup command:
```bash
./llama.cpp/bin/llama-server --model <path-to-your-gguf-model> --host 127.0.0.1 --port 8080 --ctx-size 2048
```

Common parameters:
- `--model`: Path to your GGUF model file
- `--host`: IP address to listen on (default: 127.0.0.1)
- `--port`: Port to listen on (default: 8080)
- `--ctx-size`: Context window size (default: 2048)
- `--threads`: Number of threads to use (default: -1, auto)
- `--gpu-layers`: Number of layers to offload to GPU (if available)

## Testing Methods

### 1. Web Interface
The server provides a built-in web interface:
- Open your browser and navigate to `http://127.0.0.1:8080`
- Use the chat interface to interact with the model directly

### 2. REST API Endpoints

#### Chat Completions
```bash
curl -X POST http://localhost:8080/chat/completions -d '{
    "messages": [
        {"role": "user", "content": "Hello, how are you?"}
    ],
    "stream": false
}'
```

#### Simple Completions
```bash
curl -X POST http://localhost:8080/completion -d '{
    "prompt": "Hello, how are you?",
    "n_predict": 128
}'
```

### 3. Generation Parameters

You can customize the generation using these parameters:

| Parameter | Description | Default | Range |
|-----------|-------------|---------|--------|
| temperature | Controls randomness | 0.8 | 0.0 to 1.0 |
| top_p | Nucleus sampling | 0.9 | 0.0 to 1.0 |
| top_k | Top-k sampling | 40 | 0 to infinity |
| n_predict | Max tokens to generate | 128 | 1 to infinity |
| repeat_penalty | Penalty for repeated tokens | 1.0 | 1.0 to infinity |
| presence_penalty | Penalty for token presence | 0.0 | -2.0 to 2.0 |
| frequency_penalty | Penalty for token frequency | 0.0 | -2.0 to 2.0 |

Example with custom parameters:
```bash
curl -X POST http://localhost:8080/chat/completions -d '{
    "messages": [
        {"role": "user", "content": "Tell me a story"}
    ],
    "temperature": 0.9,
    "top_p": 0.95,
    "n_predict": 256,
    "stream": false
}'
```

## API Endpoints

### 1. `/chat/completions`
- Purpose: Chat-style interactions
- Method: POST
- Format: OpenAI-compatible chat format
- Best for: Conversational AI applications

### 2. `/completion`
- Purpose: Simple text completion
- Method: POST
- Format: Simple prompt-response
- Best for: Text generation tasks

### 3. `/v1/chat/completions`
- Purpose: OpenAI-compatible chat completions
- Method: POST
- Format: OpenAI API format
- Best for: Compatibility with existing OpenAI applications

## Response Format

### Chat Completion Response
```json
{
    "choices": [{
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": "Response text here",
            "role": "assistant"
        }
    }],
    "created": 1234567890,
    "model": "model-name",
    "usage": {
        "completion_tokens": 10,
        "prompt_tokens": 5,
        "total_tokens": 15
    }
}
```

### Simple Completion Response
```json
{
    "content": "Generated text here",
    "stop": true,
    "timings": {
        "prompt_n": 5,
        "prompt_ms": 100.0,
        "predicted_n": 10,
        "predicted_ms": 200.0
    }
}
```

## Best Practices

1. **Context Management**
   - Monitor token usage to stay within context limits
   - Use appropriate `ctx-size` for your model
   - Consider using streaming for long generations

2. **Performance Optimization**
   - Adjust `--threads` based on your CPU
   - Use `--gpu-layers` if you have GPU support
   - Consider batch processing for multiple requests

3. **Generation Quality**
   - Start with default parameters
   - Adjust temperature for creativity vs. consistency
   - Use presence/frequency penalties to reduce repetition

4. **Error Handling**
   - Implement proper timeout handling
   - Check for rate limiting
   - Handle API errors gracefully

## Troubleshooting

Common issues and solutions:

1. **Server won't start**
   - Check if model file exists and is valid
   - Verify port availability
   - Check system resources

2. **Slow responses**
   - Increase `--threads`
   - Reduce context size
   - Enable GPU offloading if available

3. **Poor generation quality**
   - Adjust temperature and sampling parameters
   - Check model quality and quantization
   - Verify prompt formatting

## Advanced Features

1. **Streaming Responses**
   - Set `"stream": true` in requests
   - Handle server-sent events
   - Implement proper stream parsing

2. **Custom Templates**
   - Use `--chat-template` for custom formatting
   - Implement system prompts
   - Handle special tokens

3. **Model Management**
   - Load multiple models
   - Switch between models
   - Monitor model performance

## Security Considerations

1. **API Security**
   - Use API keys for authentication
   - Implement rate limiting
   - Secure your endpoints

2. **Model Security**
   - Validate input prompts
   - Monitor resource usage
   - Implement proper error handling

## Integration Examples

### Python Integration
```python
import requests

def chat_completion(prompt, temperature=0.8):
    response = requests.post(
        "http://localhost:8080/chat/completions",
        json={
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": False
        }
    )
    return response.json()
```

### JavaScript Integration
```javascript
async function chatCompletion(prompt, temperature = 0.8) {
    const response = await fetch('http://localhost:8080/chat/completions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            messages: [{ role: 'user', content: prompt }],
            temperature: temperature,
            stream: false
        })
    });
    return await response.json();
}
```

## Additional Resources

- [Llama.cpp GitHub Repository](https://github.com/ggerganov/llama.cpp)