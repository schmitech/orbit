#!/bin/bash
#
# ORBIT Flavor Image Publishing Script
# -------------------------------------
# Builds and optionally publishes the self-contained "pull-and-run" flavor
# images (ORBIT + orbitchat +, for the ollama flavor, a bundled Ollama
# runtime) from docker/Dockerfile.flavor. See docs/docker-bundle-plan.md.
#
# Unlike publish.sh, this script only builds from the current checkout
# (clients/orbitchat/dist and docker/entrypoint-flavor.sh are not part of
# the release tarball produced by utils/scripts/build-tarball.sh yet), so it
# is for maintainer use, not the profile-less server image covered by
# publish.sh.
#
# Each flavor publishes to its own Docker Hub repository:
#   schmitech/orbit-ollama, schmitech/orbit-openai, schmitech/orbit-gemini
#
# USAGE:
#   ./publish-flavor.sh --build --flavor ollama --tag 1.0.0
#   ./publish-flavor.sh --build --all-flavors --tag 1.0.0
#   ./publish-flavor.sh --publish --flavor openai --tag 1.0.0
#
# OPTIONS:
#   --build              Build the Docker image(s)
#   --publish            Build and push to Docker Hub
#   --flavor NAME        One of: ollama, openai, gemini
#   --all-flavors        Build/publish every flavor
#   --tag VERSION        Version tag (e.g. 1.0.0); also updates :latest
#   --no-cache           Build without using Docker layer cache
#   --help               Show this help message

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BUILD=false
PUBLISH=false
NO_CACHE=false
VERSION_TAG=""
FLAVOR=""
ALL_FLAVORS=false

FLAVORS=(ollama openai gemini)

print_help() {
    sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

repo_for_flavor() {
    echo "schmitech/orbit-$1"
}

include_ollama_for_flavor() {
    case "$1" in
        ollama) echo "true" ;;
        openai|gemini) echo "false" ;;
        *) echo -e "${RED}Unknown flavor: $1${NC}" >&2; exit 1 ;;
    esac
}

build_flavor() {
    local flavor="$1"
    local repo
    repo="$(repo_for_flavor "$flavor")"
    local include_ollama
    include_ollama="$(include_ollama_for_flavor "$flavor")"

    echo -e "${BLUE}Building ${repo} (ORBIT_FLAVOR=${flavor}, INCLUDE_OLLAMA=${include_ollama})...${NC}"

    local build_args=(
        --build-arg "ORBIT_FLAVOR=${flavor}"
        --build-arg "INCLUDE_OLLAMA=${include_ollama}"
    )
    if [ "$NO_CACHE" = true ]; then
        build_args+=(--no-cache)
    fi

    local tag_args=(-t "${repo}:latest")
    if [ -n "$VERSION_TAG" ]; then
        tag_args+=(-t "${repo}:${VERSION_TAG}")
    fi

    docker build \
        -f "$PROJECT_ROOT/docker/Dockerfile.flavor" \
        "${build_args[@]}" \
        "${tag_args[@]}" \
        "$PROJECT_ROOT"

    echo -e "${GREEN}Built ${repo}${NC}"
}

publish_flavor() {
    local flavor="$1"
    local repo
    repo="$(repo_for_flavor "$flavor")"

    echo -e "${YELLOW}Pushing ${repo}:latest...${NC}"
    docker push "${repo}:latest"

    if [ -n "$VERSION_TAG" ]; then
        echo -e "${YELLOW}Pushing ${repo}:${VERSION_TAG}...${NC}"
        docker push "${repo}:${VERSION_TAG}"
    fi

    echo -e "${GREEN}Published ${repo}${NC}"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --build) BUILD=true; shift ;;
        --publish) PUBLISH=true; BUILD=true; shift ;;
        --no-cache) NO_CACHE=true; shift ;;
        --tag) VERSION_TAG="$2"; shift 2 ;;
        --flavor) FLAVOR="$2"; shift 2 ;;
        --all-flavors) ALL_FLAVORS=true; shift ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
done

if [ "$ALL_FLAVORS" != true ] && [ -z "$FLAVOR" ]; then
    echo -e "${RED}Specify --flavor <ollama|openai|gemini> or --all-flavors${NC}"
    exit 1
fi

if [ "$ALL_FLAVORS" = true ] && [ -n "$FLAVOR" ]; then
    echo -e "${RED}Use either --flavor or --all-flavors, not both${NC}"
    exit 1
fi

if [ -n "$FLAVOR" ]; then
    match=false
    for f in "${FLAVORS[@]}"; do
        [ "$f" = "$FLAVOR" ] && match=true
    done
    if [ "$match" != true ]; then
        echo -e "${RED}Invalid --flavor: ${FLAVOR}. Use one of: ${FLAVORS[*]}${NC}"
        exit 1
    fi
fi

if [ "$BUILD" != true ]; then
    echo -e "${YELLOW}No action specified. Use --build or --publish.${NC}"
    exit 0
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed.${NC}"
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/clients/orbitchat/dist" ]; then
    echo -e "${RED}clients/orbitchat/dist not found — build orbitchat first (npm run build in clients/orbitchat).${NC}"
    exit 1
fi

TARGET_FLAVORS=("${FLAVORS[@]}")
if [ "$ALL_FLAVORS" != true ]; then
    TARGET_FLAVORS=("$FLAVOR")
fi

for flavor in "${TARGET_FLAVORS[@]}"; do
    build_flavor "$flavor"
done

if [ "$PUBLISH" = true ]; then
    for flavor in "${TARGET_FLAVORS[@]}"; do
        publish_flavor "$flavor"
    done
fi

echo -e "${GREEN}Done!${NC}"
