#!/bin/bash
#
# ORBIT Docker Image Publishing Script
# -------------------------------------
# This script builds and optionally publishes the ORBIT server Docker image.
#
# Production builds use stable release tarballs by default. Do not build
# production images directly from the main branch unless you explicitly opt into
# development/testing mode with --source checkout.
#
# Source modes:
#   release        Default. Download a GitHub release tarball and build from it.
#                  If --tag is 2.7.11-openai, the source release resolves to
#                  v2.7.11 unless --release-tag is provided.
#   local-tarball  Build utils/scripts/build-tarball.sh from this checkout and
#                  use that tarball as the Docker context. Use for release tests.
#   checkout       Build from this checkout. Use for development/testing only.
#
# Targeted config builds:
#   Use --config-dir to overlay a config tree onto /orbit/config in the image.
#   This is how to build provider-specific images such as:
#     schmitech/orbit:2.7.11-openai
#     schmitech/orbit:2.7.11-gemini
#     schmitech/orbit:2.7.11-ollama
#
#   Example:
#     ./publish.sh --build --tag 2.7.11-openai --config-dir ../deploy/openai
#
#   The config directory should contain only configuration files, for example:
#     deploy/openai/config.yaml
#     deploy/openai/adapters.yaml
#     deploy/openai/inference.yaml
#     deploy/openai/adapters/passthrough.yaml
#
# Secrets and API keys:
#   Do not bake API keys, datasource passwords, or other secrets into the image
#   or config overlay. ORBIT configs reference values like ${OPENAI_API_KEY}
#   and ${GOOGLE_API_KEY}; provide them at runtime with docker run -e,
#   --env-file, Compose secrets, Kubernetes Secrets, or your platform secret
#   manager.
#
#   Example orbit.env:
#     OPENAI_API_KEY=sk-...
#     GOOGLE_API_KEY=...
#     DATASOURCE_QDRANT_API_KEY=...
#
#   Example runtime command:
#     docker run -d --name orbit-2.7.11-openai \
#       --env-file ./orbit.env \
#       -p 3000:3000 \
#       schmitech/orbit:2.7.11-openai
#
# Image contents:
#   - Lean server-only image; no Ollama, no Node.js, no bundled models.
#   - Runtime GPU/CPU detection is handled by docker/docker-entrypoint.sh.
#   - /orbit/env.example is included for reference, but /orbit/.env is not
#     created so runtime environment variables remain authoritative.
#
# USAGE:
#   ./publish.sh [OPTIONS]
#
# OPTIONS:
#   --build              Build the Docker image
#   --publish            Build and push to Docker Hub
#   --tag VERSION        Tag version (e.g., v1.0.0)
#   --source SOURCE      Source for image code: release, local-tarball, or checkout
#   --release-tag TAG    Stable GitHub release tarball to use as source
#   --config-dir DIR     Overlay config directory for targeted builds
#   --help               Show this help message
#
# EXAMPLES:
#   ./publish.sh --build
#   ./publish.sh --build --tag v2.7.11
#   ./publish.sh --build --tag 2.7.11-openai --config-dir ../deploy/openai
#   ./publish.sh --publish --tag 2.7.11-openai --config-dir ../deploy/openai
#   ./publish.sh --build --source checkout
#
set -euo pipefail

# Default values
BUILD=false
PUBLISH=false
NO_CACHE=false
VERSION_TAG=""
SOURCE_MODE="release"
RELEASE_TAG=""
CONFIG_DIR=""
CUDA_VER="cu121"
UID_ARG="1001"
GID_ARG="0"
IMAGE_NAME="schmitech/orbit"
IMAGE_TAG_BASIC="basic"
IMAGE_TAG_LATEST="latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INVOCATION_DIR="$(pwd)"
# Change to project root (one level up from docker/)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_CONTEXT="$PROJECT_ROOT"
STAGING_DIR=""

cleanup() {
    if [ -n "$STAGING_DIR" ] && [ -d "$STAGING_DIR" ]; then
        rm -rf "$STAGING_DIR"
    fi
}
trap cleanup EXIT

print_help() {
    echo "Usage: ./publish.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build              Build the Docker image"
    echo "  --publish            Build and push to Docker Hub"
    echo "  --tag VERSION        Tag version (e.g., v1.0.0)"
    echo "                       Also selects the release tarball when --source release is used"
    echo "  --source SOURCE      Source for image code: release (default), local-tarball, checkout"
    echo "  --release-tag TAG    Release tag to download when --source release is used"
    echo "  --config-dir DIR     Overlay config directory copied into /orbit/config"
    echo "  --cuda-ver VER       CUDA wheel channel (default: cu121, e.g. cu124, cu128)"
    echo "  --uid UID            User ID for the orbit process (default: 1001)"
    echo "  --gid GID            Group ID for the orbit process (default: 0)"
    echo "  --no-cache           Build without using Docker layer cache"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./publish.sh --build"
    echo "  ./publish.sh --build --tag v2.7.11"
    echo "  ./publish.sh --build --tag 2.7.11-openai --release-tag v2.7.11 --config-dir ../deploy/openai"
    echo "  ./publish.sh --build --source local-tarball --tag v2.7.11"
    echo "  ./publish.sh --build --source checkout"
    echo "  ./publish.sh --build --no-cache"
    echo "  ./publish.sh --publish --tag v1.0.0"
    echo "  ./publish.sh --publish --cuda-ver cu128 --tag v1.0.0"
    exit 0
}

strip_v_prefix() {
    local value="$1"
    echo "${value#v}"
}

release_tag_from_image_tag() {
    local value="$1"
    value="${value#v}"

    if [[ "$value" =~ ^([0-9]+[.][0-9]+[.][0-9]+)([-_].*)?$ ]]; then
        echo "v${BASH_REMATCH[1]}"
    else
        echo "$1"
    fi
}

latest_release_tag() {
    curl -fsSL "https://api.github.com/repos/schmitech/orbit/releases/latest" \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p; t done; b; :done q'
}

normalize_release_context() {
    local context_dir="$1"

    rm -rf "$context_dir/docker"
    cp -R "$PROJECT_ROOT/docker" "$context_dir/docker"
    mkdir -p "$context_dir/docker/config-custom"

    if [ -f "$context_dir/orbit.db" ] && [ ! -f "$context_dir/install/orbit.db.default" ]; then
        mkdir -p "$context_dir/install"
        cp "$context_dir/orbit.db" "$context_dir/install/orbit.db.default"
    fi

    if [ -d "$context_dir/config" ] && [ ! -d "$context_dir/install/default-config" ]; then
        mkdir -p "$context_dir/install/default-config"
        cp -R "$context_dir/config/." "$context_dir/install/default-config/"
    fi

    if [ ! -f "$context_dir/env.example" ] && [ ! -f "$context_dir/.env" ]; then
        touch "$context_dir/env.example"
    elif [ ! -f "$context_dir/env.example" ] && [ -f "$context_dir/.env" ]; then
        cp "$context_dir/.env" "$context_dir/env.example"
    fi

    if [ -f "$PROJECT_ROOT/LICENSE" ] && [ ! -f "$context_dir/LICENSE" ]; then
        cp "$PROJECT_ROOT/LICENSE" "$context_dir/LICENSE"
    fi
}

resolve_config_dir() {
    local config_dir="$1"

    if [[ "$config_dir" = /* ]]; then
        echo "$config_dir"
    elif [ -d "$INVOCATION_DIR/$config_dir" ]; then
        (cd "$INVOCATION_DIR/$config_dir" && pwd)
    elif [ -d "$PROJECT_ROOT/$config_dir" ]; then
        (cd "$PROJECT_ROOT/$config_dir" && pwd)
    else
        echo "$config_dir"
    fi
}

apply_config_overlay() {
    local config_dir="$1"
    local resolved_config_dir

    resolved_config_dir="$(resolve_config_dir "$config_dir")"
    if [ ! -d "$resolved_config_dir" ]; then
        echo -e "${RED}Config directory not found: ${config_dir}${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Applying custom config overlay: ${resolved_config_dir}${NC}"
    rm -rf "$BUILD_CONTEXT/docker/config-custom"
    mkdir -p "$BUILD_CONTEXT/docker/config-custom"
    cp -R "$resolved_config_dir/." "$BUILD_CONTEXT/docker/config-custom/"
}

prepare_checkout_context() {
    STAGING_DIR="$(mktemp -d)"
    BUILD_CONTEXT="$STAGING_DIR/context"
    mkdir -p "$BUILD_CONTEXT"

    echo -e "${YELLOW}Staging current checkout as Docker build context...${NC}"
    (cd "$PROJECT_ROOT" && tar --exclude "./.git" --exclude "./dist" -cf - .) \
        | (cd "$BUILD_CONTEXT" && tar -xf -)
    mkdir -p "$BUILD_CONTEXT/docker/config-custom"
}

prepare_release_context() {
    local tag="$1"
    local version
    version="$(strip_v_prefix "$tag")"

    STAGING_DIR="$(mktemp -d)"
    BUILD_CONTEXT="$STAGING_DIR/context"
    mkdir -p "$BUILD_CONTEXT"

    local tarball="$STAGING_DIR/orbit-${version}.tar.gz"
    local checksum_file="$STAGING_DIR/orbit-${version}.tar.gz.sha256"
    local url="https://github.com/schmitech/orbit/releases/download/${tag}/orbit-${version}.tar.gz"
    local checksum_url="${url}.sha256"

    echo -e "${YELLOW}Downloading stable release tarball: ${url}${NC}"
    curl -fL "$url" -o "$tarball"

    if curl -fL "$checksum_url" -o "$checksum_file"; then
        echo -e "${YELLOW}Verifying release tarball checksum...${NC}"
        local expected_checksum
        local actual_checksum
        expected_checksum="$(awk '{print $1; exit}' "$checksum_file")"
        if command -v sha256sum &> /dev/null; then
            actual_checksum="$(sha256sum "$tarball" | awk '{print $1}')"
        else
            actual_checksum="$(shasum -a 256 "$tarball" | awk '{print $1}')"
        fi
        if [ "$actual_checksum" != "$expected_checksum" ]; then
            echo -e "${RED}Checksum verification failed for ${tarball}${NC}"
            exit 1
        fi
        echo -e "${GREEN}Checksum verification passed.${NC}"
    else
        echo -e "${YELLOW}Checksum file not found for ${tag}; continuing without checksum verification.${NC}"
    fi

    echo -e "${YELLOW}Extracting release tarball into Docker build context...${NC}"
    tar -xzf "$tarball" -C "$BUILD_CONTEXT" --strip-components=1
    normalize_release_context "$BUILD_CONTEXT"
}

prepare_local_tarball_context() {
    local tag="$1"
    local version
    version="$(strip_v_prefix "$tag")"

    STAGING_DIR="$(mktemp -d)"
    BUILD_CONTEXT="$STAGING_DIR/context"
    mkdir -p "$BUILD_CONTEXT"

    echo -e "${YELLOW}Building local tarball from this checkout for Docker context...${NC}"
    "$PROJECT_ROOT/utils/scripts/build-tarball.sh" "$version"

    local tarball="$PROJECT_ROOT/dist/orbit-${version}.tar.gz"
    if [ ! -f "$tarball" ]; then
        echo -e "${RED}Expected tarball not found: ${tarball}${NC}"
        exit 1
    fi

    tar -xzf "$tarball" -C "$BUILD_CONTEXT" --strip-components=1
    normalize_release_context "$BUILD_CONTEXT"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build) BUILD=true; shift ;;
        --publish) PUBLISH=true; BUILD=true; shift ;;
        --no-cache) NO_CACHE=true; shift ;;
        --tag) VERSION_TAG="$2"; shift 2 ;;
        --source) SOURCE_MODE="$2"; shift 2 ;;
        --release-tag) RELEASE_TAG="$2"; shift 2 ;;
        --config-dir) CONFIG_DIR="$2"; shift 2 ;;
        --cuda-ver) CUDA_VER="$2"; shift 2 ;;
        --uid) UID_ARG="$2"; shift 2 ;;
        --gid) GID_ARG="$2"; shift 2 ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
done

# Change to project root
cd "$PROJECT_ROOT"

case "$SOURCE_MODE" in
    release|local-tarball|checkout) ;;
    *) echo -e "${RED}Invalid --source value: ${SOURCE_MODE}. Use release, local-tarball, or checkout.${NC}"; exit 1 ;;
esac

if [ "$BUILD" != true ]; then
    echo -e "${YELLOW}No action specified. Use --build or --publish.${NC}"
    exit 0
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

if [ "$SOURCE_MODE" = "release" ]; then
    if [ -z "$RELEASE_TAG" ]; then
        if [ -n "$VERSION_TAG" ]; then
            RELEASE_TAG="$(release_tag_from_image_tag "$VERSION_TAG")"
        fi
    fi
    if [ -z "$RELEASE_TAG" ]; then
        echo -e "${YELLOW}No release tag specified; resolving latest stable release from GitHub...${NC}"
        RELEASE_TAG="$(latest_release_tag)"
    fi
    if [ -z "$RELEASE_TAG" ]; then
        echo -e "${RED}Unable to resolve latest release tag. Pass --tag vX.Y.Z or --release-tag vX.Y.Z.${NC}"
        exit 1
    fi
    prepare_release_context "$RELEASE_TAG"
elif [ "$SOURCE_MODE" = "local-tarball" ]; then
    if [ -z "$VERSION_TAG" ]; then
        echo -e "${RED}--source local-tarball requires --tag VERSION so the tarball name is deterministic.${NC}"
        exit 1
    fi
    prepare_local_tarball_context "$VERSION_TAG"
else
    echo -e "${YELLOW}Using current checkout as Docker build context. This is for development/testing only.${NC}"
    if [ -n "$CONFIG_DIR" ]; then
        prepare_checkout_context
    fi
fi

if [ -n "$CONFIG_DIR" ]; then
    if [ -z "$VERSION_TAG" ]; then
        echo -e "${RED}--config-dir requires --tag so the targeted image has an explicit tag.${NC}"
        exit 1
    fi
    apply_config_overlay "$CONFIG_DIR"
fi

# Verify required files exist
if [ ! -f "$BUILD_CONTEXT/docker/Dockerfile" ]; then
    echo -e "${RED}docker/Dockerfile not found${NC}"
    exit 1
fi

if [ ! -f "$BUILD_CONTEXT/install/default-config/ollama.yaml" ]; then
    echo -e "${RED}install/default-config/ollama.yaml not found${NC}"
    exit 1
fi

if [ ! -f "$BUILD_CONTEXT/install/default-config/inference.yaml" ]; then
    echo -e "${RED}install/default-config/inference.yaml not found${NC}"
    exit 1
fi

if [ ! -f "$BUILD_CONTEXT/install/orbit.db.default" ]; then
    echo -e "${RED}install/orbit.db.default not found${NC}"
    exit 1
fi

if [ "$BUILD" = true ]; then
    echo -e "${BLUE}Building ORBIT server Docker image...${NC}"

    echo -e "${GREEN}Configuration:${NC}"
    echo -e "${BLUE}   Image: Server-only (Ollama runs separately via docker-compose)${NC}"
    echo -e "${BLUE}   Presets: smollm2-1.7b-cpu / smollm2-1.7b-gpu (auto-detected)${NC}"
    echo -e "${BLUE}   Source: ${SOURCE_MODE}${NC}"
    if [ "$SOURCE_MODE" = "release" ]; then
        echo -e "${BLUE}   Release: ${RELEASE_TAG}${NC}"
    fi
    if [ -n "$CONFIG_DIR" ]; then
        echo -e "${BLUE}   Config overlay: ${CONFIG_DIR}${NC}"
    fi
    echo -e "${BLUE}   CUDA wheel channel: ${CUDA_VER}${NC}"
    echo -e "${BLUE}   UID/GID: ${UID_ARG}/${GID_ARG}${NC}"
    echo -e "${GREEN}Hardware Support:${NC}"
    echo -e "${BLUE}   CPU: Optimized with OpenBLAS${NC}"
    echo -e "${BLUE}   GPU: NVIDIA CUDA (use docker-compose.gpu.yml override)${NC}"

    # Verify default database exists
    if [ -f "$BUILD_CONTEXT/install/orbit.db.default" ]; then
        db_size=$(du -h "$BUILD_CONTEXT/install/orbit.db.default" | cut -f1)
        echo -e "${GREEN}Default database found: install/orbit.db.default (${db_size})${NC}"
    fi

    # Build the Docker image
    echo -e "${YELLOW}Building Docker image...${NC}"

    BUILD_ARGS=(
        --build-arg "CUDA_VER=${CUDA_VER}"
        --build-arg "UID=${UID_ARG}"
        --build-arg "GID=${GID_ARG}"
    )
    if [ "$NO_CACHE" = true ]; then
        BUILD_ARGS+=(--no-cache)
    fi

    DOCKER_TAG_ARGS=()
    if [ -n "$CONFIG_DIR" ]; then
        DOCKER_TAG_ARGS+=(
            -t "${IMAGE_NAME}:${VERSION_TAG}"
            -t "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
        )
    else
        DOCKER_TAG_ARGS+=(
            -t "${IMAGE_NAME}:${IMAGE_TAG_BASIC}"
            -t "${IMAGE_NAME}:${IMAGE_TAG_LATEST}"
        )
    fi

    if docker build \
        -f "$BUILD_CONTEXT/docker/Dockerfile" \
        "${BUILD_ARGS[@]}" \
        "${DOCKER_TAG_ARGS[@]}" \
        "$BUILD_CONTEXT"; then
        echo -e "${GREEN}Docker image built successfully${NC}"

        # Show image info
        echo -e "${BLUE}Image information:${NC}"
        if [ -n "$CONFIG_DIR" ]; then
            docker images "${IMAGE_NAME}:${VERSION_TAG}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        else
            docker images "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        fi
    else
        echo -e "${RED}Failed to build Docker image${NC}"
        exit 1
    fi

    # Add version tag if specified
    if [ -n "$VERSION_TAG" ] && [ -z "$CONFIG_DIR" ]; then
        echo -e "${YELLOW}Tagging image with version: $VERSION_TAG${NC}"
        docker tag "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
        docker tag "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" "${IMAGE_NAME}:${VERSION_TAG}"
        echo -e "${GREEN}Tagged as ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
        echo -e "${GREEN}Tagged as ${IMAGE_NAME}:${VERSION_TAG}${NC}"
    fi
fi

# Publish the image
if [ "$PUBLISH" = true ]; then
    echo -e "${BLUE}Publishing Docker image to Docker Hub...${NC}"

    if [ -z "$CONFIG_DIR" ]; then
        # Push basic tag
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG_BASIC}...${NC}"
        if docker push "${IMAGE_NAME}:${IMAGE_TAG_BASIC}"; then
            echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_BASIC}${NC}"
        else
            echo -e "${RED}Failed to push ${IMAGE_NAME}:${IMAGE_TAG_BASIC}${NC}"
            exit 1
        fi

        # Push latest tag
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG_LATEST}...${NC}"
        if docker push "${IMAGE_NAME}:${IMAGE_TAG_LATEST}"; then
            echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_LATEST}${NC}"
        else
            echo -e "${RED}Failed to push ${IMAGE_NAME}:${IMAGE_TAG_LATEST}${NC}"
            exit 1
        fi
    fi

    # Push version tag if specified
    if [ -n "$VERSION_TAG" ]; then
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${VERSION_TAG}...${NC}"
        if docker push "${IMAGE_NAME}:${VERSION_TAG}"; then
            echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${VERSION_TAG}${NC}"
        else
            echo -e "${RED}Failed to push ${IMAGE_NAME}:${VERSION_TAG}${NC}"
            exit 1
        fi

        echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}...${NC}"
        if docker push "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"; then
            echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
        else
            echo -e "${RED}Failed to push ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}Successfully published ORBIT server image to Docker Hub!${NC}"
    echo -e "${BLUE}Published tags:${NC}"
    if [ -z "$CONFIG_DIR" ]; then
        echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_BASIC}"
        echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_LATEST}"
    fi
    if [ -n "$VERSION_TAG" ]; then
        echo -e "   - ${IMAGE_NAME}:${VERSION_TAG}"
        echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
    fi

    RUN_TAG="${IMAGE_TAG_BASIC}"
    if [ -n "$CONFIG_DIR" ]; then
        RUN_TAG="${VERSION_TAG}"
    fi
    CONTAINER_NAME="orbit-${RUN_TAG}"
    CONTAINER_NAME="${CONTAINER_NAME//[^A-Za-z0-9_.-]/-}"

    echo ""
    echo -e "${BLUE}Run the published image:${NC}"
    echo -e "   docker pull ${IMAGE_NAME}:${RUN_TAG}"
    if [ -z "$CONFIG_DIR" ]; then
        echo -e "   docker run -d --name ${CONTAINER_NAME} --add-host=host.docker.internal:host-gateway -e OLLAMA_HOST=host.docker.internal:11434 -p 3000:3000 ${IMAGE_NAME}:${RUN_TAG}"
    else
        echo -e "   docker run -d --name ${CONTAINER_NAME} -p 3000:3000 ${IMAGE_NAME}:${RUN_TAG}"
    fi
    echo ""
    echo -e "${BLUE}Run with provider credentials:${NC}"
    echo -e "   docker run -d --name ${CONTAINER_NAME} --env-file ./orbit.env -p 3000:3000 ${IMAGE_NAME}:${RUN_TAG}"
    echo -e "   # or: docker run -d --name ${CONTAINER_NAME} -e OPENAI_API_KEY=... -p 3000:3000 ${IMAGE_NAME}:${RUN_TAG}"
    echo ""
    echo -e "${BLUE}Connect orbitchat from host:${NC}"
    echo -e "   npm install -g orbitchat"
    echo -e "   ORBIT_ADAPTER_KEYS='{\"simple-chat\":\"default-key\"}' orbitchat"
fi

echo -e "${GREEN}Done!${NC}"
