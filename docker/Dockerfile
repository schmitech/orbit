FROM python:3.12-slim

WORKDIR /orbit

ARG CUDA_VER=cu121
ARG UID=1001
ARG GID=0

# ═══════════════════════════════════════════════════════════════════════════
# Performance Optimizations for CPU/GPU inference
# ═══════════════════════════════════════════════════════════════════════════
# - OpenBLAS: Optimized linear algebra for CPU inference
# - numactl: NUMA-aware memory allocation for multi-socket systems
# - Environment variables optimize threading and memory for ML workloads
# ═══════════════════════════════════════════════════════════════════════════

# Install system dependencies including performance libraries.
# libopenblas-dev and numactl optimize CPU inference workloads.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    gcc \
    g++ \
    make \
    libssl-dev \
    libffi-dev \
    libpq-dev \
    jq \
    zstd \
    libopenblas-dev \
    numactl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ═══════════════════════════════════════════════════════════════════════════
# CPU Performance Environment Variables
# ═══════════════════════════════════════════════════════════════════════════
# These optimize threading and memory allocation for inference workloads.
# MALLOC_TRIM_THRESHOLD_ reduces Python memory fragmentation.
# TOKENIZERS_PARALLELISM=false optimizes for inference rather than training.
ENV OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4 \
    VECLIB_MAXIMUM_THREADS=4 \
    NUMEXPR_NUM_THREADS=4 \
    MALLOC_TRIM_THRESHOLD_=100000 \
    TOKENIZERS_PARALLELISM=false \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/orbit/data/cache/hf \
    SCARF_NO_ANALYTICS=true \
    DO_NOT_TRACK=true \
    ANONYMIZED_TELEMETRY=false \
    HF_HUB_DISABLE_TELEMETRY=1 \
    CUDA_VER=${CUDA_VER}

# Copy dependency configuration first (for better caching)
COPY install/dependencies.toml /orbit/install/
COPY install/generate_requirements.py /orbit/install/

# Copy setup script and make it executable
COPY install/setup.sh /orbit/install/
RUN chmod +x /orbit/install/setup.sh

# Install Python dependencies (all profiles - ready for future adapters like multimodal)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir uv tomli && \
    cd /orbit/install && \
    python3 generate_requirements.py all --output /tmp/requirements.txt && \
    grep -Ev '^(torch|torchvision)([<=>[:space:]]|$)' /tmp/requirements.txt > /tmp/requirements-no-torch.txt && \
    uv pip install --system --no-cache-dir -r /tmp/requirements-no-torch.txt && \
    uv pip install --system --no-cache-dir --index-url "https://download.pytorch.org/whl/${CUDA_VER}" \
        "torch>=2.2.2,<3.0.0" \
        "torchvision>=0.17.0,<1" && \
    rm /tmp/requirements-no-torch.txt && \
    rm /tmp/requirements.txt

# Copy the application code
COPY server/ /orbit/server/
COPY bin/ /orbit/bin/
COPY LICENSE* /orbit/

# Copy default-config as config directory (same as tarball approach)
# This matches exactly how build-tarball.sh copies config files
# Includes ollama.yaml which is referenced by inference.yaml
COPY install/default-config/ /orbit/config/

# ═══════════════════════════════════════════════════════════════════════════
# Docker Config Profiles
# ═══════════════════════════════════════════════════════════════════════════
COPY docker/config/config.yaml.minimal /orbit/config/config.yaml
COPY docker/config/adapters.yaml.minimal /orbit/config/adapters.yaml
COPY docker/config/adapters/passthrough.yaml.minimal /orbit/config/adapters/passthrough.yaml
COPY docker/config-custom/ /tmp/orbit-config-custom/
RUN if find /tmp/orbit-config-custom -type f ! -name ".gitkeep" | grep -q .; then \
        cp -R /tmp/orbit-config-custom/. /orbit/config/; \
    fi && \
    rm -rf /tmp/orbit-config-custom

# Keep the env template for reference, but do not create /orbit/.env in Docker.
# Runtime environment variables from docker run, --env-file, Compose, or
# orchestrator secrets must remain the source of truth for provider keys.
COPY env.example /orbit/env.example

# Make scripts executable
RUN chmod +x /orbit/bin/orbit.py /orbit/bin/orbit.sh

# Create necessary directories
RUN mkdir -p /orbit/logs /orbit/data /orbit/models /orbit/config-runtime

# Copy default database seed. The entrypoint copies this into /orbit/data on
# first boot so SQLite can write journals as the non-root orbit user.
COPY install/orbit.db.default /orbit/orbit.db.default

# Set environment variables
ENV PYTHONPATH=/orbit:/orbit/server
ENV PATH="/orbit/bin:${PATH}"
ENV ENVIRONMENT=production

# ═══════════════════════════════════════════════════════════════════════════
# GPU/CPU Auto-Detection Configuration
# ═══════════════════════════════════════════════════════════════════════════
# ORBIT_PRESET: Override automatic GPU detection (optional)
#   - "auto" (default): Detect GPU and select smollm2-1.7b-gpu or smollm2-1.7b-cpu
#   - "smollm2-1.7b-gpu": Force GPU preset
#   - "smollm2-1.7b-cpu": Force CPU preset
#     These presets map to the Ollama smollm2 tag pulled by docker-compose.
#   - Any other preset name from ollama.yaml
# ═══════════════════════════════════════════════════════════════════════════
ENV ORBIT_PRESET=auto

# Expose API port only (Ollama runs in separate container, orbitchat runs on host)
EXPOSE 3000

# Health check - API server only
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD curl -sf http://localhost:3000/health | jq -e '.status == "healthy"' > /dev/null || exit 1

# Copy entrypoint script
COPY docker/docker-entrypoint.sh /orbit/docker-entrypoint.sh
RUN chmod +x /orbit/docker-entrypoint.sh && \
    if ! getent group "${GID}" >/dev/null; then groupadd -r -g "${GID}" orbit; fi && \
    useradd -r -u "${UID}" -g "${GID}" orbit && \
    chown -R orbit:"${GID}" /orbit/logs /orbit/data /orbit/models /orbit/config-runtime && \
    chown orbit:"${GID}" /orbit/orbit.db.default && \
    chmod 640 /orbit/orbit.db.default

USER orbit

# Run the entrypoint script
ENTRYPOINT ["/orbit/docker-entrypoint.sh"]
