# Setting Up vLLM with Qwen2.5-14B-Instruct on AWS

This guide walks through the process of setting up and running the Qwen2.5-14B-Instruct model using vLLM on AWS EC2 instances, with solutions for common storage and configuration issues.

## Prerequisites

- AWS EC2 instance with NVIDIA GPU (recommended: g4dn.xlarge or higher)
- NVIDIA drivers installed
- Docker and NVIDIA Container Toolkit installed
- At least 100GB of storage space (preferably more)

## Hugging Face Login (Required for Private or Large Model Downloads)

Before running vLLM with Hugging Face models, log in to the Hugging Face CLI to provide your access token. This is required for downloading most large models (including Qwen2.5-14B-Instruct) and for accessing private models.

1. Install the Hugging Face CLI (if not already):
   ```bash
   pip install --upgrade huggingface_hub
   ```
2. Log in to Hugging Face:
   ```bash
   huggingface-cli login
   ```
   - Paste your access token when prompted. You can get your token from https://huggingface.co/settings/tokens

3. (Optional) Set the token as an environment variable for Docker:
   ```bash
   export HUGGING_FACE_HUB_TOKEN=your_token_here
   ```
   - This allows Docker containers to access the token for model downloads.

## Initial Setup

### 1. Create EC2 Instance

Use an AWS Deep Learning AMI (DLAMI) with GPU support to simplify driver installation:

```bash
# Example instance types
# g4dn.xlarge - 1 GPU, 4 vCPUs, 16 GB RAM
# g4dn.2xlarge - 1 GPU, 8 vCPUs, 32 GB RAM
# g5.xlarge - 1 GPU, 4 vCPUs, 16 GB RAM
```

Attach a large EBS volume (300GB recommended) to your instance.

### 1. Configure Docker for NVIDIA Support

Ensure Docker and NVIDIA Container Toolkit are properly installed:

```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker installation
docker --version

# Check NVIDIA Docker integration
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```
### 2. Setup docker
```bash
./setup_docker.sh
```

### 3. Verify Docker Storage Location (optional)

```bash
# Check Docker's root directory
docker info | grep "Docker Root Dir"

# Should show: Docker Root Dir: /opt/dlami/nvme/docker
```

## Running the vLLM Container

```bash
./run_vllm.sh Qwen/Qwen2.5-7B-Instruct
```

## Troubleshooting

### "No space left on device" Error

If you encounter space issues despite configuring Docker to use the larger volume:

1. Verify Docker is using the correct storage location:
   ```bash
   docker info | grep "Docker Root Dir"
   ```

2. Clean Docker resources completely:
   ```bash
   docker system prune -a -f --volumes
   ```

3. Check available space on both volumes:
   ```bash
   df -h
   ```

4. Try pulling the image separately:
   ```bash
   docker pull vllm/vllm-openai:latest
   ```

### GGUF Model Loading Issues

If you encounter issues loading the GGUF model:

1. Make sure you're using absolute paths for volume mounts:
   ```bash
   CURRENT_DIR=$(pwd)
   MODEL_DIR="${CURRENT_DIR}/models"
   CONFIG_DIR="${CURRENT_DIR}/config"
   ```

2. Try the direct Hugging Face approach if GGUF isn't working:
   ```bash
   docker run -it \
       --runtime nvidia \
       --gpus all \
       --network="host" \
       --ipc=host \
       -v "${CONFIG_DIR}:/config" \
       vllm/vllm-openai:latest \
       --model "Qwen/Qwen2.5-14B-Instruct" \
       --quantization awq \
       --host "0.0.0.0" \
       --port 5000 \
       --gpu-memory-utilization 0.9 \
       --served-model-name "VLLMQwen2.5-14B" \
       --max-num-batched-tokens 8192 \
       --max-num-seqs 256 \
       --max-model-len 8192 \
       --generation-config /config
   ```

3. Check vLLM documentation for specific GGUF loading requirements:
   [vLLM GGUF Support](https://docs.vllm.ai/en/latest/models/supported_models.html)

### GPU Issues

If Docker can't access the GPUs:

1. Verify NVIDIA drivers are working:
   ```bash
   nvidia-smi
   ```

2. Check NVIDIA Container Toolkit configuration:
   ```bash
   sudo nano /etc/docker/daemon.json
   ```
   
   Ensure it contains the NVIDIA runtime configuration.

3. Restart Docker:
   ```bash
   sudo systemctl restart docker
   ```

## Using the API

Once the server is running, you can make API calls to generate text:

### Test the Completions Endpoint

```bash
curl http://localhost:5000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "VLLMQwen2.5-14B",
    "prompt": "Write a short poem about artificial intelligence:",
    "max_tokens": 256,
    "temperature": 0.7
  }'
```

### Test the Chat Completions Endpoint

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "VLLMQwen2.5-14B",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What are the three laws of robotics?"}
    ],
    "max_tokens": 256,
    "temperature": 0.7
  }'
```

### Check Available Models

```bash
curl http://localhost:5000/v1/models
```

### Test Server Health

```bash
curl http://localhost:5000/health
```

### Test With Streaming Response

For streaming responses (similar to how ChatGPT provides tokens incrementally):

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "VLLMQwen2.5-14B",
    "messages": [
      {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    "max_tokens": 256,
    "temperature": 0.7,
    "stream": true
  }'
```

You can also access the OpenAPI documentation by opening http://localhost:5000/docs in your browser, which will show you all the available endpoints and parameters.

## Utility Scripts and GUI

For easier interaction with the vLLM API, several utility scripts have been created:

### 1. Test Query Script

Create a script to test the chat completion API with pretty formatting:

```bash
#!/bin/bash

# Test vLLM chat completion API
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen2.5-14B-Instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "temperature": 0.7,
    "max_tokens": 100
  }' | jq
```

Save as `test-query.sh` and make it executable with `chmod +x test-query.sh`.

### 2. List Models Script

Create a script to list available models with readable output:

```bash
#!/bin/bash

# List available models in vLLM server
curl http://localhost:5000/v1/models | jq
```

Save as `list-models.sh` and make it executable with `chmod +x list-models.sh`.

### 3. Gradio GUI Interface

A simple web interface using Gradio can be created to interact with vLLM:

```bash
./gui-demo.sh
```

Save as `gui-demo.sh` and make it executable with `chmod +x gui-demo.sh`.

### Running the GUI

To run the web interface:

```bash
./gui-demo.sh
```

You can customize the settings with command-line parameters:

```bash
./gui-demo.sh --model "Qwen2.5-14B-Instruct" --api-url "http://localhost:5000/v1" --temperature 0.7 --port 7860
```

### Third-Party UIs

Several third-party UI options are also available for vLLM:

1. **nextjs-vllm-ui** - A beautiful ChatGPT-like interface
   - GitHub: https://github.com/yoziru/nextjs-vllm-ui
   - Run with Docker: `docker run --rm -d -p 3000:3000 -e VLLM_URL=http://host.docker.internal:5000 ghcr.io/yoziru/nextjs-vllm-ui:latest`

2. **Open WebUI** - A full-featured web interface that works with vLLM
   - Can be configured to use vLLM as the backend instead of Ollama
   - Example Docker command:
     ```bash
     docker run -d -p 3000:8080 \
       --name open-webui \
       --restart always \
       --env=OPENAI_API_BASE_URL=http://<your-ip>:5000/v1 \
       --env=OPENAI_API_KEY=your-api-key \
       --env=ENABLE_OLLAMA_API=false \
       ghcr.io/open-webui/open-webui:main
     ```

3. **vllm-ui** - A simple Gradio-based interface designed for Vision Language Models
   - GitHub: https://github.com/sammcj/vlm-ui

## Performance Tuning

Adjust these parameters in the `run_vllm.sh` script based on your hardware:

- `--gpu-memory-utilization`: Value between 0 and 1 (default: 0.9)
- `--max-num-batched-tokens`: Increase for higher throughput, decrease if out of memory
- `--max-num-seqs`: Maximum number of sequences in the batch
- `--max-model-len`: Maximum sequence length
- `--tensor-parallel-size`: Set to number of GPUs if using multiple GPUs

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [Qwen2.5 Model Information](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct)
- [NVIDIA Container Toolkit Documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/overview.html)
