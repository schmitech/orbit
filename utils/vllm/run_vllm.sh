#!/bin/bash

# Usage: ./run_vllm.sh [MODEL_NAME]
# Example: ./run_vllm.sh Qwen/Qwen2.5-14B-Instruct

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: $0 [MODEL_NAME]"
  echo "  MODEL_NAME: HuggingFace model ID (default: Qwen/Qwen2.5-14B-Instruct)"
  exit 0
fi

MODEL_NAME=${1:-"Qwen/Qwen2.5-14B-Instruct"}

# Check available disk space
ROOT_SPACE=$(df -h / | awk 'NR==2 {print $4}')
DOCKER_SPACE=$(df -h /opt/dlami/nvme | awk 'NR==2 {print $4}')
echo "Available space on root: $ROOT_SPACE"
echo "Available space on Docker volume: $DOCKER_SPACE"

# Check if Docker daemon is running
docker info > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "Docker daemon is not running. Starting Docker..."
  sudo systemctl start docker
fi

# Clean up Docker resources before running
echo "Cleaning up Docker resources..."
sudo docker system prune -f

# Create HuggingFace cache directory for model downloads
HF_CACHE_DIR="${HOME}/.cache/huggingface"
mkdir -p "${HF_CACHE_DIR}"

# Run vLLM Docker container
echo "Starting vLLM container..."
sudo docker run -it \
    --runtime nvidia \
    --gpus all \
    --network="host" \
    --ipc=host \
    -v "${HF_CACHE_DIR}:/root/.cache/huggingface" \
    -e HUGGING_FACE_HUB_TOKEN="${HUGGING_FACE_HUB_TOKEN}" \
    vllm/vllm-openai:latest \
    --model "$MODEL_NAME" \
    --dtype auto \
    --tensor-parallel-size 1 \
    --host "0.0.0.0" \
    --port 5000 \
    --gpu-memory-utilization 0.9 \
    --served-model-name "VLLMQwen2.5-14B" \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 256 \
    --max-model-len 8192 \
    --trust-remote-code