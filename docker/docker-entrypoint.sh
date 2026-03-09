#!/bin/bash
set -e

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT Server - Starting"
echo "═══════════════════════════════════════════════════════════════════════════"

# ═══════════════════════════════════════════════════════════════════════════
# GPU Detection and Preset Selection
# ═══════════════════════════════════════════════════════════════════════════
detect_gpu() {
    # Check for NVIDIA GPU using multiple methods

    # Method 1: nvidia-smi (requires NVIDIA driver)
    if command -v nvidia-smi &> /dev/null; then
        if nvidia-smi &> /dev/null; then
            echo "nvidia"
            return 0
        fi
    fi

    # Method 2: Check for NVIDIA device files (works with --gpus flag)
    if [ -e /dev/nvidia0 ] || [ -e /dev/nvidiactl ]; then
        echo "nvidia"
        return 0
    fi

    # Method 3: Check lspci for NVIDIA GPU (hardware detection)
    if command -v lspci &> /dev/null; then
        if lspci | grep -qi "nvidia"; then
            # GPU present but driver may not be available in container
            # Only count as GPU if nvidia-smi works or device files exist
            echo "cpu"
            return 0
        fi
    fi

    # Method 4: Check for AMD ROCm GPU
    if [ -e /dev/kfd ] && [ -e /dev/dri ]; then
        echo "amd"
        return 0
    fi

    echo "cpu"
    return 0
}

select_preset() {
    local preset="${ORBIT_PRESET:-auto}"

    if [ "$preset" = "auto" ]; then
        local gpu_type=$(detect_gpu)

        case "$gpu_type" in
            nvidia|amd)
                echo "smollm2-1.7b-gpu"
                ;;
            *)
                echo "smollm2-1.7b-cpu"
                ;;
        esac
    else
        echo "$preset"
    fi
}

# Detect hardware and select appropriate preset
DETECTED_GPU=$(detect_gpu)
SELECTED_PRESET=$(select_preset)

echo ""
echo "Hardware Detection:"
if [ "$DETECTED_GPU" = "nvidia" ]; then
    echo "  GPU Type: NVIDIA (CUDA acceleration enabled)"
    # Show GPU info if available
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
        echo "  GPU Model: $GPU_NAME"
        echo "  GPU Memory: $GPU_MEM"
    fi
elif [ "$DETECTED_GPU" = "amd" ]; then
    echo "  GPU Type: AMD (ROCm acceleration enabled)"
else
    echo "  GPU Type: None detected (CPU inference mode)"
fi
echo "  Selected Preset: $SELECTED_PRESET"
echo ""

# Update inference.yaml with selected preset
if [ -f /orbit/config/inference.yaml ]; then
    echo "Configuring inference with preset: $SELECTED_PRESET"
    sed -i "s/use_preset: \".*\"/use_preset: \"$SELECTED_PRESET\"/" /orbit/config/inference.yaml
fi

# Update adapter configs with selected preset
for adapter_file in /orbit/config/adapters/*.yaml; do
    if [ -f "$adapter_file" ]; then
        # Replace model references for smollm2 presets (cpu <-> gpu)
        if echo "$SELECTED_PRESET" | grep -q "gpu"; then
            sed -i 's/model: "smollm2-1.7b-cpu"/model: "smollm2-1.7b-gpu"/' "$adapter_file"
        else
            sed -i 's/model: "smollm2-1.7b-gpu"/model: "smollm2-1.7b-cpu"/' "$adapter_file"
        fi
    fi
done
echo "Updated adapter configs with preset: $SELECTED_PRESET"

# ═══════════════════════════════════════════════════════════════════════════
# Rewrite Ollama URLs for docker-compose networking
# ═══════════════════════════════════════════════════════════════════════════
OLLAMA_URL="http://${OLLAMA_HOST:-localhost:11434}"
echo "Rewriting Ollama URLs to: $OLLAMA_URL"
find /orbit/config -name '*.yaml' -exec sed -i "s|http://localhost:11434|${OLLAMA_URL}|g" {} +

# ═══════════════════════════════════════════════════════════════════════════
# Wait for Ollama to be ready
# ═══════════════════════════════════════════════════════════════════════════
echo "Waiting for Ollama to be ready at ${OLLAMA_URL}..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Error: Ollama failed to respond after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "Waiting for Ollama... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "Ollama is ready"

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT Server is starting"
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  API:      http://localhost:3000"
echo "  Ollama:   $OLLAMA_URL"
echo "  Preset:   $SELECTED_PRESET"
if [ "$DETECTED_GPU" = "cpu" ]; then
    echo "  Hardware: CPU"
else
    echo "  Hardware: GPU ($DETECTED_GPU)"
fi
echo ""
echo "  Connect orbitchat from host:"
echo "    ORBIT_ADAPTER_KEYS='{\"simple-chat\":\"default-key\"}' orbitchat"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Run ORBIT server as PID 1 for proper signal handling
exec python /orbit/server/main.py --config /orbit/config/config.yaml
