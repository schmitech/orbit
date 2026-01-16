#!/bin/bash
set -e

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT Basic - Starting with Ollama"
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

# Start Ollama in the background
echo "Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Error: Ollama failed to start after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "Waiting for Ollama... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "✓ Ollama is ready"

# Verify SmolLM2 model is available
echo "Checking for SmolLM2 model..."
if ollama list | grep -qi "smollm2"; then
    echo "✓ Model SmolLM2 is available"
else
    echo "Model not found, pulling smollm2:latest..."
    ollama pull smollm2:latest
    echo "✓ Model SmolLM2 pulled successfully"
fi

# Verify nomic-embed-text model is available for embeddings
echo "Checking for nomic-embed-text model..."
if ollama list | grep -q "nomic-embed-text"; then
    echo "✓ Model nomic-embed-text is available"
else
    echo "Model not found, pulling nomic-embed-text:latest..."
    ollama pull nomic-embed-text:latest
    echo "✓ Model nomic-embed-text pulled successfully"
fi

# Start the ORBIT server in the background
echo "Starting ORBIT server..."
python /orbit/server/main.py --config /orbit/config/config.yaml &
ORBIT_PID=$!

# Wait for ORBIT server to be ready
echo "Waiting for ORBIT server to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s http://localhost:3000/health > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Error: ORBIT server failed to start after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "Waiting for ORBIT server... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "✓ ORBIT server is ready"

# Start orbitchat web app (direct mode with default API key)
echo "Starting orbitchat web app on port 5173..."

orbitchat --api-url http://localhost:3000 --api-key default-key --host 0.0.0.0 &
ORBITCHAT_PID=$!

echo "✓ orbitchat web app started"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT Basic is ready!"
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  Web App:  http://localhost:5173"
echo "  API:      http://localhost:3000"
echo "  Model:    SmolLM2 1.7B"
echo "  Preset:   $SELECTED_PRESET"
if [ "$DETECTED_GPU" = "cpu" ]; then
    echo "  Hardware: CPU"
else
    echo "  Hardware: GPU ($DETECTED_GPU)"
fi
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Handle shutdown gracefully
trap "echo 'Shutting down...'; kill $ORBITCHAT_PID $ORBIT_PID $OLLAMA_PID 2>/dev/null; exit 0" SIGTERM SIGINT

# Wait for any process to exit
wait -n

# If any process exits, shut down all
echo "A process exited, shutting down..."
kill $ORBITCHAT_PID $ORBIT_PID $OLLAMA_PID 2>/dev/null
exit 1
