# BitNet Setup Guide

This guide explains how to set up and use Microsoft BitNet as an inference provider in Orbit, supporting 1.58-bit quantized language models.

## Overview

BitNet is Microsoft's official inference framework for 1-bit LLMs, offering:
- **1.58-bit quantization**: Ultra-efficient model compression
- **High performance**: Optimized inference with custom kernels
- **Dual modes**: Direct model loading and API server support
- **GPU acceleration**: CUDA and Metal support

## Installation

### Prerequisites

- Python 3.9+
- C++ compiler (GCC, Clang, or MSVC)
- CUDA toolkit (for GPU support)
- CMake 3.15+

### Installing BitNet Dependencies

Orbit provides a dedicated BitNet profile that includes the necessary build dependencies:

```bash
# Install BitNet profile dependencies
pip install -e .[bitnet]

# Or if using uv
uv pip install -e .[bitnet]
```

This will install the build dependencies (cmake, ninja, pybind11) needed for building BitNet from source.

### Building BitNet from Source

Since BitNet doesn't have a PyPI package yet, you need to build it from source:

```bash
# Clone the BitNet repository
git clone --recursive https://github.com/microsoft/BitNet.git
cd BitNet

# Create a conda environment (recommended)
conda create -n bitnet-cpp python=3.9
conda activate bitnet-cpp

# Install dependencies
pip install -r requirements.txt

# Build the project
mkdir build && cd build
cmake ..
make -j$(nproc)  # Use all available cores

# Install Python bindings
cd ..
pip install -e .
```

### Alternative: Using Pre-built Binaries

If available, you can use pre-built binaries:

```bash
pip install bitnet-cpp  # This may not be available yet
```

## Model Setup

### Downloading Models

BitNet supports various 1.58-bit quantized models. Download them using:

```bash
# Download a pre-quantized model
huggingface-cli download microsoft/BitNet-b1.58-2B-4T --local-dir models/BitNet-b1.58-2B-4T

# Or download the base model and quantize it
huggingface-cli download microsoft/bitnet-b1.58-2B-4T-bf16 --local-dir models/bitnet-b1.58-2B-4T-bf16
```

### Quantizing Models

To quantize your own models:

```bash
# Convert from .safetensors to GGUF format
python utils/convert-helper-bitnet.py models/bitnet-b1.58-2B-4T-bf16

# Set up environment with specific quantization
python setup_env.py -md models/BitNet-b1.58-2B-4T -q i2_s
```

## Configuration

### Basic Configuration

Add BitNet to your `config/inference.yaml`:

```yaml
bitnet:
  mode: "direct"  # or "api"
  model_path: "models/bitnet-b1.58-3B/ggml-model-i2_s.gguf"
  quant_type: "i2_s"  # or "tl1"
  temperature: 0.7
  max_tokens: 1024
  n_ctx: 2048
  n_threads: 8
```

### Direct Mode Configuration

For local model loading:

```yaml
bitnet:
  mode: "direct"
  model_path: "models/bitnet-b1.58-3B/ggml-model-i2_s.gguf"
  quant_type: "i2_s"
  use_pretuned: true
  quant_embd: false
  n_ctx: 2048
  n_threads: 8
  n_gpu_layers: 0  # 0 = CPU only, -1 = all layers on GPU
  main_gpu: 0
  low_vram: false
  use_mmap: true
  use_mlock: false
```

### API Mode Configuration

For BitNet inference server:

```yaml
bitnet:
  mode: "api"
  base_url: "http://localhost:8080"
  api_key: null  # Optional
  model: "bitnet-b1.58-3B"
  temperature: 0.7
  max_tokens: 1024
```

### Advanced Configuration

Full configuration with all BitNet-specific parameters:

```yaml
bitnet:
  mode: "direct"
  model_path: "models/bitnet-b1.58-3B/ggml-model-i2_s.gguf"
  quant_type: "i2_s"  # Quantization type: i2_s or tl1
  use_pretuned: true  # Use pretuned kernel parameters
  quant_embd: false   # Quantize embeddings to f16
  
  # Generation parameters
  temperature: 0.7
  top_p: 0.9
  top_k: 40
  max_tokens: 1024
  
  # Context and threading
  n_ctx: 2048
  n_threads: 8
  n_batch: 2
  
  # GPU settings
  n_gpu_layers: 0  # Number of layers to offload to GPU
  main_gpu: 0      # Main GPU device
  low_vram: false  # Enable for systems with limited VRAM
  
  # BitNet-specific optimizations
  kernel_params:
    enable_custom: false
    # Add custom kernel parameters here
  
  # Memory management
  use_mmap: true
  use_mlock: false
  
  # Streaming
  stream: true
  
  # Stop sequences
  stop: []
  
  # Timeout and retry configuration
  timeout:
    connect: 10000
    total: 120000
  
  retry:
    enabled: true
    max_retries: 3
    initial_wait_ms: 1000
    max_wait_ms: 30000
    exponential_base: 2
```

## Usage

### Using BitNet in Orbit

Once configured, BitNet will be available as an inference provider:

```python
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType

# Create BitNet inference service
service = AIServiceFactory.create_service(
    ServiceType.INFERENCE,
    "bitnet",
    config
)

# Initialize the service
await service.initialize()

# Generate text
response = await service.generate("Hello, how are you?")
print(response)

# Generate streaming response
async for chunk in service.generate_stream("Tell me a story"):
    print(chunk, end='', flush=True)
```

### Running BitNet Server (API Mode)

To use API mode, start the BitNet inference server:

```bash
# Start the server
python run_inference.py -m models/bitnet-b1.58-3B/ggml-model-i2_s.gguf -p "You are a helpful assistant" -cnv

# Or run as a server
python run_inference_server.py --model_path models/bitnet-b1.58-3B/ggml-model-i2_s.gguf --port 8080
```

## Performance Optimization

### GPU Acceleration

For GPU acceleration, set appropriate parameters:

```yaml
bitnet:
  n_gpu_layers: -1  # Use all layers on GPU
  main_gpu: 0       # Primary GPU
  low_vram: true    # Enable for limited VRAM
```

### Memory Optimization

For memory-constrained systems:

```yaml
bitnet:
  use_mmap: true    # Memory mapping
  use_mlock: false  # Disable memory locking
  low_vram: true    # Low VRAM mode
  n_batch: 1        # Smaller batch size
```

### Threading

Optimize CPU performance:

```yaml
bitnet:
  n_threads: 8      # Number of CPU threads
  n_batch: 2        # Batch size for processing
```

## Troubleshooting

### Common Issues

1. **Import Error**: `ModuleNotFoundError: No module named 'bitnet'`
   - Solution: Build BitNet from source as described in the installation section

2. **Model Not Found**: `Model file not found`
   - Solution: Ensure the model path is correct and the file exists
   - Check that the model is properly quantized for BitNet

3. **CUDA Errors**: GPU-related errors
   - Solution: Ensure CUDA toolkit is installed and compatible
   - Try setting `n_gpu_layers: 0` to use CPU only

4. **Memory Issues**: Out of memory errors
   - Solution: Reduce `n_ctx`, enable `low_vram`, or use `use_mmap: true`

### Debug Mode

Enable verbose logging:

```yaml
bitnet:
  verbose: true
```

Or set environment variable:

```bash
export BITNET_VERBOSE=1
```

### Performance Monitoring

Monitor BitNet performance:

```python
import time

start_time = time.time()
response = await service.generate("Test prompt")
end_time = time.time()

print(f"Generation time: {end_time - start_time:.2f} seconds")
print(f"Tokens per second: {len(response.split()) / (end_time - start_time):.2f}")
```

## Supported Models

BitNet supports various 1.58-bit quantized models:

- **BitNet-b1.58-2B-4T**: 2B parameter model
- **BitNet-b1.58-3B**: 3B parameter model
- **Llama3-8B-1.58**: Llama 3 8B with 1.58-bit quantization
- **Falcon3-1B-Instruct-1.58bit**: Falcon 3 1B instruction-tuned
- **Falcon3-3B-Instruct-1.58bit**: Falcon 3 3B instruction-tuned
- **Falcon3-7B-Instruct-1.58bit**: Falcon 3 7B instruction-tuned
- **Falcon3-10B-Instruct-1.58bit**: Falcon 3 10B instruction-tuned

## Quantization Types

BitNet supports two quantization types:

- **i2_s**: Integer 2-bit signed quantization
- **tl1**: Ternary-like 1-bit quantization

Choose based on your model and performance requirements.

## API Reference

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | str | "direct" | Operation mode: "direct" or "api" |
| `model_path` | str | - | Path to quantized model file |
| `quant_type` | str | "i2_s" | Quantization type: "i2_s" or "tl1" |
| `use_pretuned` | bool | true | Use pretuned kernel parameters |
| `quant_embd` | bool | false | Quantize embeddings to f16 |
| `n_ctx` | int | 2048 | Context window size |
| `n_threads` | int | 8 | Number of CPU threads |
| `n_gpu_layers` | int | 0 | GPU layers (0=CPU, -1=all) |
| `temperature` | float | 0.7 | Generation temperature |
| `max_tokens` | int | 1024 | Maximum tokens to generate |

### Methods

- `initialize()`: Initialize the BitNet service
- `generate(prompt, **kwargs)`: Generate non-streaming response
- `generate_stream(prompt, **kwargs)`: Generate streaming response
- `close()`: Clean up resources
- `verify_connection()`: Check service health

## Examples

### Basic Text Generation

```python
# Simple text generation
response = await service.generate("What is artificial intelligence?")
print(response)
```

### Streaming Generation

```python
# Streaming text generation
async for chunk in service.generate_stream("Write a short story about a robot"):
    print(chunk, end='', flush=True)
```

### Custom Parameters

```python
# Custom generation parameters
response = await service.generate(
    "Explain quantum computing",
    temperature=0.3,
    max_tokens=500,
    top_p=0.9
)
```

### Conversation Format

```python
# Using conversation format
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is machine learning?"}
]

response = await service.generate("", messages=messages)
```

## Further Reading

- [BitNet GitHub Repository](https://github.com/microsoft/BitNet)
- [BitNet Paper](https://arxiv.org/abs/2402.17764)
- [1.58-bit Quantization Research](https://arxiv.org/abs/2402.17764)
- [Orbit Documentation](../README.md)
