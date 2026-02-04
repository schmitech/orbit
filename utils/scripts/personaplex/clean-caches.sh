#!/usr/bin/env bash
# Free disk space by cleaning package/model caches. Safe to run; only removes
# cached downloads, not the PersonaPlex model once fully downloaded.
# Run from personaplex repo root.

set -e

echo "=== Cleaning caches to free disk space ==="

# Pip cache (often 10–20 GB)
if command -v pip &>/dev/null; then
  echo "Purging pip cache..."
  pip cache purge 2>/dev/null || true
fi

# uv cache
if command -v uv &>/dev/null; then
  echo "Cleaning uv cache..."
  uv cache clean 2>/dev/null || true
fi

# Remove incomplete Hugging Face downloads (failed partial model.safetensors, etc.)
HF_BLOBS="${HOME}/.cache/huggingface/hub/models--nvidia--personaplex-7b-v1/blobs"
if [[ -d "$HF_BLOBS" ]]; then
  echo "Removing incomplete HF blobs..."
  find "$HF_BLOBS" -name "*.incomplete" -delete 2>/dev/null || true
fi

echo "Done. Check free space with: df -h /"
