#!/bin/bash
set -euo pipefail

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

    # Method 4: Check for AMD ROCm GPU. Require ROCm-specific signals so
    # generic /dev/dri devices from integrated graphics do not select GPU mode.
    if { command -v rocminfo &> /dev/null && rocminfo &> /dev/null; } || \
       { [ -e /dev/kfd ] && [ -d /sys/class/kfd ] && ls /dev/dri/renderD* > /dev/null 2>&1; }; then
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

if [ "$DETECTED_GPU" = "nvidia" ]; then
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/usr/local/lib/python3.12/site-packages/torch/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib"
fi

CONFIG_SOURCE_DIR="/orbit/config"
RUNTIME_CONFIG_DIR="/orbit/config-runtime"

echo "Preparing runtime configuration in: $RUNTIME_CONFIG_DIR"
mkdir -p "$RUNTIME_CONFIG_DIR"
find "$RUNTIME_CONFIG_DIR" -mindepth 1 -delete
cp -a "$CONFIG_SOURCE_DIR/." "$RUNTIME_CONFIG_DIR/"

if [ ! -f /orbit/data/orbit.db ]; then
    echo "Initializing database from bundled default seed"
    cp /orbit/orbit.db.default /orbit/data/orbit.db
    chmod 660 /orbit/data/orbit.db
fi

# Update inference.yaml with selected preset. Source templates under /orbit/config
# are never changed; this keeps restarts idempotent when env vars or hardware change.
if [ -f "$RUNTIME_CONFIG_DIR/inference.yaml" ]; then
    echo "Configuring inference with preset: $SELECTED_PRESET"
    sed -i "s/use_preset: \".*\"/use_preset: \"$SELECTED_PRESET\"/" "$RUNTIME_CONFIG_DIR/inference.yaml"
fi

# Update adapter configs with selected preset
for adapter_file in "$RUNTIME_CONFIG_DIR"/adapters/*.yaml; do
    if [ -f "$adapter_file" ]; then
        # Replace model references for smollm2 presets (cpu <-> gpu). Both
        # presets use the smollm2 Ollama tag pulled by ollama-init.
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
OLLAMA_HOST_VALUE="${OLLAMA_HOST:-localhost:11434}"
case "$OLLAMA_HOST_VALUE" in
    http://*|https://*) OLLAMA_URL="$OLLAMA_HOST_VALUE" ;;
    *) OLLAMA_URL="http://$OLLAMA_HOST_VALUE" ;;
esac
echo "Rewriting Ollama URLs to: $OLLAMA_URL"
find "$RUNTIME_CONFIG_DIR" -name '*.yaml' -exec sed -i "s|http://localhost:11434|${OLLAMA_URL}|g" {} +

should_wait_for_ollama() {
    local mode="${ORBIT_WAIT_FOR_OLLAMA:-auto}"

    case "$mode" in
        true|1|yes) return 0 ;;
        false|0|no) return 1 ;;
        auto)
            if grep -qiE 'inference_provider:[[:space:]]*"?ollama"?|-[[:space:]]*"?ollama.yaml"?' "$RUNTIME_CONFIG_DIR/config.yaml" 2>/dev/null; then
                return 0
            fi
            if grep -RqiE 'inference_provider:[[:space:]]*"?ollama"?|model:[[:space:]]*"?smollm2-|provider:[[:space:]]*"?ollama"?' "$RUNTIME_CONFIG_DIR/adapters" 2>/dev/null; then
                return 0
            fi
            return 1
            ;;
        *)
            echo "Warning: invalid ORBIT_WAIT_FOR_OLLAMA=${mode}; using auto"
            if grep -qiE 'inference_provider:[[:space:]]*"?ollama"?|-[[:space:]]*"?ollama.yaml"?' "$RUNTIME_CONFIG_DIR/config.yaml" 2>/dev/null; then
                return 0
            fi
            if grep -RqiE 'inference_provider:[[:space:]]*"?ollama"?|model:[[:space:]]*"?smollm2-|provider:[[:space:]]*"?ollama"?' "$RUNTIME_CONFIG_DIR/adapters" 2>/dev/null; then
                return 0
            fi
            return 1
            ;;
    esac
}

if [ "${ORBIT_ALLOW_DEFAULT_CREDENTIALS:-false}" != "true" ]; then
    echo ""
    echo "SECURITY WARNING:"
    echo "  This image includes the default database and API key for first-run convenience."
    echo "  Rotate the default API key/admin password before exposing ORBIT beyond localhost."
    echo "  Set ORBIT_ALLOW_DEFAULT_CREDENTIALS=true to acknowledge this warning."
    echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# Wait for Ollama to be ready
# ═══════════════════════════════════════════════════════════════════════════
OLLAMA_STATUS="not required"
if should_wait_for_ollama; then
    echo "Waiting for Ollama to be ready at ${OLLAMA_URL}..."
    MAX_RETRIES="${ORBIT_OLLAMA_MAX_RETRIES:-30}"
    RETRY_COUNT=0
    while ! curl -s "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
            echo "Error: Ollama failed to respond after $MAX_RETRIES attempts"
            echo "Hint: if Ollama is running on the Docker host, pass:"
            echo "  -e OLLAMA_HOST=host.docker.internal:11434 --add-host=host.docker.internal:host-gateway"
            echo "For non-Ollama provider images, pass ORBIT_WAIT_FOR_OLLAMA=false or remove Ollama references from the config overlay."
            exit 1
        fi
        echo "Waiting for Ollama... (attempt $RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    done
    OLLAMA_STATUS="$OLLAMA_URL"
    echo "Ollama is ready"
else
    echo "Skipping Ollama readiness check (ORBIT_WAIT_FOR_OLLAMA=${ORBIT_WAIT_FOR_OLLAMA:-auto})"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT Server is starting"
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  API:      http://localhost:3000"
echo "  Ollama:   $OLLAMA_STATUS"
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
exec python /orbit/server/main.py --config "$RUNTIME_CONFIG_DIR/config.yaml"
