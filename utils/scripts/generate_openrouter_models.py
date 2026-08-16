#!/usr/bin/env python3
"""Generate an `allowed_models` YAML block for a passthrough adapter, sourced
from OpenRouter's public model catalog.

OpenRouter publishes its full model list at a public, unauthenticated
endpoint (https://openrouter.ai/api/v1/models), so this needs no API key.
Useful for adapters that want to expose a large, frequently-changing set
of OpenRouter-proxied models (see the `allowed_models` pattern in
config/adapters/passthrough.yaml) without hand-maintaining every entry.

Usage
-----
    venv/bin/python utils/scripts/generate_openrouter_models.py -o openrouter_models.yaml
    venv/bin/python utils/scripts/generate_openrouter_models.py --min-context 32000 --limit 200
    venv/bin/python utils/scripts/generate_openrouter_models.py --exclude free --exclude beta

Output is a standalone YAML file containing just the `allowed_models`
list entries for provider "openrouter" — splice it into an adapter's
allowed_models section by hand; this script never writes to adapter configs
directly.
"""

import argparse
import json
import re
import sys
import urllib.request

MODELS_URL = "https://openrouter.ai/api/v1/models"

# Sensible ceiling if OpenRouter doesn't report a completion-token limit
# for a given model (some entries omit top_provider.max_completion_tokens).
DEFAULT_MAX_TOKENS_FALLBACK = 8192
FALLBACK_MAX_TOKENS_FRACTION = 0.25  # of context_length, if no explicit limit


def fetch_models():
    req = urllib.request.Request(MODELS_URL, headers={"User-Agent": "talktoanyai-model-sync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    return payload.get("data", [])


def slugify(model_id):
    # "meta-llama/llama-3.3-70b-instruct" -> "llama-3.3-70b-instruct"
    name = model_id.split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    return name.lower()


def compute_max_tokens(model):
    top_provider = model.get("top_provider") or {}
    explicit = top_provider.get("max_completion_tokens")
    if explicit:
        return int(explicit)
    context_length = model.get("context_length") or 0
    if context_length:
        return max(DEFAULT_MAX_TOKENS_FALLBACK, int(context_length * FALLBACK_MAX_TOKENS_FRACTION))
    return DEFAULT_MAX_TOKENS_FALLBACK


def passes_filters(model, args):
    model_id = model["id"]
    context_length = model.get("context_length") or 0

    if context_length < args.min_context:
        return False

    if args.text_only:
        modality = ((model.get("architecture") or {}).get("modality") or "")
        if modality and modality != "text->text":
            return False

    if not args.include_free and model_id.endswith(":free"):
        return False

    for pattern in args.exclude:
        if pattern.lower() in model_id.lower():
            return False

    if args.include and not any(p.lower() in model_id.lower() for p in args.include):
        return False

    return True


def build_entry(model):
    model_id = model["id"]
    return {
        "name": slugify(model_id),
        "provider": "openrouter",
        "model": model_id,
        "context_window": int(model.get("context_length") or 0) or None,
        "max_tokens": compute_max_tokens(model),
    }


def render_yaml(entries):
    lines = []
    for e in entries:
        lines.append(f'      - name: "{e["name"]}"')
        lines.append('        provider: "openrouter"')
        lines.append(f'        model: "{e["model"]}"')
        if e["context_window"]:
            lines.append(f'        context_window: {e["context_window"]}')
        lines.append(f'        max_tokens: {e["max_tokens"]}')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", default="openrouter_models.yaml", help="Output YAML file path")
    parser.add_argument("--min-context", type=int, default=8000, help="Minimum context_length to include a model")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of models emitted (after filtering)")
    parser.add_argument("--include-free", action="store_true", help="Include ':free' rate-limited variants (excluded by default)")
    parser.add_argument("--text-only", action="store_true", help="Only include text->text models (drop vision/audio/image variants)")
    parser.add_argument("--exclude", action="append", default=[], help="Substring to exclude from model id (repeatable)")
    parser.add_argument("--include", action="append", default=[], help="If set, only keep models whose id contains one of these substrings (repeatable)")
    parser.add_argument("--sort-by", choices=["context", "id"], default="context", help="Sort order for output")
    args = parser.parse_args()

    try:
        models = fetch_models()
    except Exception as exc:
        print(f"Failed to fetch model list from {MODELS_URL}: {exc}", file=sys.stderr)
        sys.exit(1)

    filtered = [m for m in models if passes_filters(m, args)]

    if args.sort_by == "context":
        filtered.sort(key=lambda m: m.get("context_length") or 0, reverse=True)
    else:
        filtered.sort(key=lambda m: m["id"])

    if args.limit:
        filtered = filtered[: args.limit]

    entries = [build_entry(m) for m in filtered]

    with open(args.output, "w") as f:
        f.write("# Auto-generated from OpenRouter's public model catalog\n")
        f.write(f"# Source: {MODELS_URL}\n")
        f.write(f"# {len(entries)} models included after filtering\n")
        f.write("# Splice this list into your adapter's allowed_models: section\n")
        f.write(render_yaml(entries))

    print(f"Wrote {len(entries)} models to {args.output}")


if __name__ == "__main__":
    main()
