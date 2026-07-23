#!/bin/bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════
# ORBIT Flavor Image Entrypoint
# ═══════════════════════════════════════════════════════════════════════════
# Runs as PID 1 under tini (see Dockerfile.flavor ENTRYPOINT). Starts ORBIT,
# orbitchat, and (ollama flavor only) a local Ollama daemon as supervised
# children; exits (and lets tini forward the signal to the group) as soon as
# any required process exits, so `docker stop`/a crash both terminate cleanly.
#
# Image capability marker: /orbit/.orbit-flavor lists the flavor baked in at
# build time and whether Ollama is bundled. A runtime ORBIT_PROFILE that
# needs Ollama on an image that doesn't bundle it is rejected before anything
# starts, rather than failing confusingly later.

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT (flavor image) - Starting"
echo "═══════════════════════════════════════════════════════════════════════════"

IMAGE_FLAVOR=""
IMAGE_HAS_OLLAMA="false"
if [ -f /orbit/.orbit-flavor ]; then
    # shellcheck source=/dev/null
    source /orbit/.orbit-flavor
fi

ORBIT_PROFILE="${ORBIT_PROFILE:-$IMAGE_FLAVOR}"

if [ -z "$ORBIT_PROFILE" ]; then
    echo "Error: ORBIT_PROFILE is not set and the image has no baked-in default." >&2
    exit 1
fi

CONFIG_SOURCE_DIR="/orbit/config"
RUNTIME_CONFIG_DIR="/orbit/config-runtime"
ORBITCHAT_DIR="/orbit/orbitchat"
ORBITCHAT_CONFIG="$RUNTIME_CONFIG_DIR/orbitchat.yaml"

echo "Preparing runtime configuration in: $RUNTIME_CONFIG_DIR"
mkdir -p "$RUNTIME_CONFIG_DIR"
find "$RUNTIME_CONFIG_DIR" -mindepth 1 -delete
cp -a "$CONFIG_SOURCE_DIR/." "$RUNTIME_CONFIG_DIR/"

if [ ! -f /orbit/data/orbit.db ]; then
    echo "Initializing database from bundled default seed"
    cp /orbit/orbit.db.default /orbit/data/orbit.db
    chmod 660 /orbit/data/orbit.db
fi

echo "Resolving profile: $ORBIT_PROFILE"
if ! python3 /orbit/docker/runtime_profiles.py \
        --profile "$ORBIT_PROFILE" \
        --config-dir "$RUNTIME_CONFIG_DIR" \
        --orbitchat-template "$ORBITCHAT_DIR/orbitchat.yaml.example" \
        --orbitchat-out "$ORBITCHAT_CONFIG"; then
    exit 1
fi

# Profile -> needs_ollama is re-derived here (not parsed from Python output) so
# a mismatched runtime override on a non-ollama image fails fast and loud.
case "$ORBIT_PROFILE" in
    ollama) PROFILE_NEEDS_OLLAMA="true" ;;
    openai|gemini) PROFILE_NEEDS_OLLAMA="false" ;;
    *) echo "Error: unknown ORBIT_PROFILE '$ORBIT_PROFILE'" >&2; exit 1 ;;
esac

if [ "$PROFILE_NEEDS_OLLAMA" = "true" ] && [ "$IMAGE_HAS_OLLAMA" != "true" ]; then
    echo "Error: profile '$ORBIT_PROFILE' requires a bundled Ollama runtime, but this image does not include one." >&2
    echo "Pull schmitech/orbit-ollama instead, or select a profile this image supports." >&2
    exit 1
fi

if [ "${ORBIT_ALLOW_DEFAULT_CREDENTIALS:-false}" != "true" ]; then
    echo ""
    echo "SECURITY WARNING:"
    echo "  This image includes the default database and API key for first-run convenience."
    echo "  Rotate the default API key/admin password before exposing ORBIT beyond localhost."
    echo "  Set ORBIT_ALLOW_DEFAULT_CREDENTIALS=true to acknowledge this warning."
    echo ""
fi

PIDS=()
NAMES=()

cleanup() {
    trap - TERM INT EXIT
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup TERM INT EXIT

# ═══════════════════════════════════════════════════════════════════════════
# Ollama (ollama flavor only)
# ═══════════════════════════════════════════════════════════════════════════
if [ "$PROFILE_NEEDS_OLLAMA" = "true" ]; then
    echo "Starting local Ollama..."
    OLLAMA_HOST=127.0.0.1:11434 ollama serve > /orbit/logs/ollama.log 2>&1 &
    PIDS+=("$!"); NAMES+=("ollama")

    OLLAMA_URL="http://127.0.0.1:11434"
    RETRY_COUNT=0
    until curl -s "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ "$RETRY_COUNT" -ge 60 ]; then
            echo "Error: Ollama failed to become ready" >&2
            exit 1
        fi
        sleep 1
    done
    echo "Ollama is ready"

    # Must match runtime_profiles.PROFILES["ollama"].ollama_models.
    REQUIRED_OLLAMA_MODELS="${REQUIRED_OLLAMA_MODELS:-gemma4:e2b nomic-embed-text}"
    for model in $REQUIRED_OLLAMA_MODELS; do
        if ! ollama list 2>/dev/null | grep -q "^${model}"; then
            echo "Pulling Ollama model: $model"
            ollama pull "$model"
        else
            echo "Ollama model already present: $model"
        fi
    done
fi

# ═══════════════════════════════════════════════════════════════════════════
# ORBIT server
# ═══════════════════════════════════════════════════════════════════════════
echo "Starting ORBIT server..."
python /orbit/server/main.py --config "$RUNTIME_CONFIG_DIR/config.yaml" > /orbit/logs/orbit.log 2>&1 &
PIDS+=("$!"); NAMES+=("orbit")

RETRY_COUNT=0
until curl -sf http://127.0.0.1:3000/health > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ "$RETRY_COUNT" -ge 90 ]; then
        echo "Error: ORBIT server failed to become healthy" >&2
        echo "--- orbit.log (tail) ---"
        tail -n 100 /orbit/logs/orbit.log || true
        exit 1
    fi
    sleep 1
done
echo "ORBIT server is healthy"

# ═══════════════════════════════════════════════════════════════════════════
# orbitchat UI
# ═══════════════════════════════════════════════════════════════════════════
echo "Starting orbitchat..."
export ORBIT_ADAPTER_KEYS='{"simple-chat-with-files":"multimodal"}'
node "$ORBITCHAT_DIR/bin/orbitchat.js" --host 0.0.0.0 --port 5173 --config "$ORBITCHAT_CONFIG" \
    > /orbit/logs/orbitchat.log 2>&1 &
PIDS+=("$!"); NAMES+=("orbitchat")

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  ORBIT is ready"
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  Profile:  $ORBIT_PROFILE"
echo "  API:      http://localhost:3000"
echo "  Chat UI:  http://localhost:5173"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Wait for the first process (of any) to exit, then tear the rest down. This
# treats every listed process as required: none of them are expected to exit
# on their own during normal operation.
set +e
wait -n "${PIDS[@]}"
EXIT_CODE=$?
set -e

for i in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
        echo "Process '${NAMES[$i]}' exited (code $EXIT_CODE)"
    fi
done

exit "$EXIT_CODE"
