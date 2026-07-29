#!/usr/bin/env python3
"""Check install/default-config/pricing.yaml for drift against public pricing sources.

Compares the canonical hand-maintained rate table (the template new installs
are seeded from — `config/pricing.yaml` is a deployment's local copy of it)
against two external sources and prints a report of new/changed/missing
rates. It never writes to pricing.yaml — cost estimates feed billing-adjacent
numbers in the admin panel, so updates must be reviewed and applied by hand.

Sources
-------
  - LiteLLM's community-maintained model_prices_and_context_window.json
    (https://github.com/BerriAI/litellm), covering most providers.
  - OpenRouter's /api/v1/models endpoint, which reports live pricing for
    the models it proxies (useful cross-check, especially for providers
    OpenRouter mirrors directly).

Neither source is authoritative for every provider in pricing.yaml —
Anthropic, xAI, and others without public pricing APIs may not appear in
either, and will still need manual updates from the vendor's pricing page.

Usage
-----
  venv/bin/python utils/scripts/check_pricing_drift.py
  venv/bin/python utils/scripts/check_pricing_drift.py --provider openai
  venv/bin/python utils/scripts/check_pricing_drift.py --threshold-pct 5
"""

import argparse
import fnmatch
import json
import sys
import urllib.request
from pathlib import Path

import yaml

LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

REPO_ROOT = Path(__file__).resolve().parents[2]
PRICING_PATH = REPO_ROOT / "install" / "default-config" / "pricing.yaml"

# LiteLLM's `litellm_provider` values don't always match pricing.yaml's
# provider keys — map the ones we price locally.
LITELLM_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "vertex_ai-language-models": "vertexai",
    "xai": "xai",
    "mistral": "mistral",
    "cohere": "cohere",
    "cohere_chat": "cohere",
    "deepseek": "deepseek",
    "groq": "groq",
    "openrouter": "openrouter",
}


def fetch_json(url: str, timeout: int = 20) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def load_local_pricing() -> dict:
    with open(PRICING_PATH) as f:
        return yaml.safe_load(f)["pricing"]["providers"]


def resolve_local_rate(providers: dict, provider: str, model: str):
    """Mirror PricingService.resolve(): exact key, then longest glob match."""
    patterns = providers.get(provider)
    if not patterns:
        return None
    if model in patterns:
        return patterns[model]
    matches = [p for p in patterns if p != model and fnmatch.fnmatch(model, p)]
    if not matches:
        return None
    matches.sort(key=len, reverse=True)
    return patterns[matches[0]]


def collect_litellm_rates(data: dict) -> dict:
    """Return {(provider, model): (input_per_1m, output_per_1m)} for models
    whose litellm_provider maps to a provider we price locally."""
    rates = {}
    for model, spec in data.items():
        if not isinstance(spec, dict):
            continue
        litellm_provider = spec.get("litellm_provider")
        provider = LITELLM_PROVIDER_MAP.get(litellm_provider)
        if not provider:
            continue
        input_cost = spec.get("input_cost_per_token")
        output_cost = spec.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            continue
        # LiteLLM prefixes some providers' model keys with the provider slug
        # (e.g. "gemini/gemini-2.5-flash") — pricing.yaml keys are bare model
        # names, so strip it before comparing.
        if "/" in model and model.split("/", 1)[0] == litellm_provider:
            model = model.split("/", 1)[1]
        rates[(provider, model)] = (input_cost * 1_000_000, output_cost * 1_000_000)
    return rates


def collect_openrouter_rates(data: dict) -> dict:
    """Return {(provider, model): (input_per_1m, output_per_1m)} keyed by the
    OpenRouter model id's provider prefix (e.g. "mistralai/mistral-large" ->
    provider "mistral"). OpenRouter's own "*"-priced entries are skipped."""
    rates = {}
    slug_to_provider = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gemini",
        "x-ai": "xai",
        "mistralai": "mistral",
        "cohere": "cohere",
        "deepseek": "deepseek",
    }
    for entry in data.get("data", []):
        model_id = entry.get("id", "")
        if "/" not in model_id:
            continue
        slug, _, name = model_id.partition("/")
        provider = slug_to_provider.get(slug)
        if not provider:
            continue
        pricing = entry.get("pricing") or {}
        try:
            input_cost = float(pricing.get("prompt", "0"))
            output_cost = float(pricing.get("completion", "0"))
        except (TypeError, ValueError):
            continue
        if input_cost == 0 and output_cost == 0:
            continue
        rates[(provider, name)] = (input_cost * 1_000_000, output_cost * 1_000_000)
    return rates


def pct_diff(a: float, b: float) -> float:
    if a == 0:
        return 0.0 if b == 0 else float("inf")
    return abs(a - b) / a * 100


def is_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[")


def find_stale_local_entries(rates: dict, local: dict, provider_filter):
    """Local exact-model rates whose (provider, model) no longer appears in
    `rates`, even though the source does cover other models for that
    provider — a sign the model was retired/renamed upstream and the local
    entry is now unverifiable against any source."""
    providers_seen = {provider for provider, _ in rates}
    models_by_provider = {}
    for provider, model in rates:
        models_by_provider.setdefault(provider, set()).add(model)

    stale = []
    for provider, patterns in local.items():
        if provider_filter and provider != provider_filter:
            continue
        if provider not in providers_seen:
            continue  # source doesn't cover this provider at all
        for pattern in patterns:
            if is_glob(pattern):
                continue  # can't compare a glob against a fixed model list
            if pattern not in models_by_provider[provider]:
                stale.append((provider, pattern))
    return stale


def report(source_name: str, rates: dict, local: dict, provider_filter, threshold_pct: float):
    new_entries = []
    changed_entries = []
    for (provider, model), (input_rate, output_rate) in sorted(rates.items()):
        if provider_filter and provider != provider_filter:
            continue
        local_rate = resolve_local_rate(local, provider, model)
        if local_rate is None:
            new_entries.append((provider, model, input_rate, output_rate))
            continue
        local_input = local_rate.get("input_per_1m")
        local_output = local_rate.get("output_per_1m")
        if local_input is None or local_output is None:
            continue
        input_diff = pct_diff(local_input, input_rate)
        output_diff = pct_diff(local_output, output_rate)
        if input_diff >= threshold_pct or output_diff >= threshold_pct:
            changed_entries.append(
                (provider, model, local_input, input_rate, local_output, output_rate)
            )

    stale_entries = find_stale_local_entries(rates, local, provider_filter)

    print(f"\n=== {source_name} ===")
    print(f"{len(rates)} priced models seen for mapped providers")

    if changed_entries:
        print(f"\n-- Rate mismatches (>= {threshold_pct}% diff) --")
        for provider, model, li, ri, lo, ro in changed_entries:
            print(f"  [{provider}] {model}")
            print(f"      input:  local={li:.4f}  source={ri:.4f} $/1M")
            print(f"      output: local={lo:.4f}  source={ro:.4f} $/1M")
    else:
        print("\n-- No rate mismatches above threshold --")

    if new_entries:
        print(f"\n-- Models priced by source but absent from pricing.yaml ({len(new_entries)}) --")
        for provider, model, ri, ro in new_entries[:50]:
            print(f"  [{provider}] {model}: input={ri:.4f} output={ro:.4f} $/1M")
        if len(new_entries) > 50:
            print(f"  ... and {len(new_entries) - 50} more (use --provider to narrow)")
    else:
        print("\n-- No new models found --")

    if stale_entries:
        print(f"\n-- Local exact-model entries no longer found in this source ({len(stale_entries)}) --")
        print("   (source covers this provider but not this exact model key — may be retired/renamed)")
        for provider, model in stale_entries:
            print(f"  [{provider}] {model}")
    else:
        print("\n-- No stale local entries detected --")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", help="Only check this pricing.yaml provider key (e.g. openai)")
    parser.add_argument(
        "--threshold-pct", type=float, default=1.0,
        help="Minimum %% difference to flag a rate mismatch (default: 1.0)",
    )
    parser.add_argument(
        "--source", choices=["litellm", "openrouter", "both"], default="both",
        help="Which source(s) to check against (default: both)",
    )
    args = parser.parse_args()

    local = load_local_pricing()

    if args.source in ("litellm", "both"):
        try:
            litellm_data = fetch_json(LITELLM_URL)
        except Exception as e:
            print(f"Failed to fetch LiteLLM pricing data: {e}", file=sys.stderr)
        else:
            report("LiteLLM", collect_litellm_rates(litellm_data), local, args.provider, args.threshold_pct)

    if args.source in ("openrouter", "both"):
        try:
            openrouter_data = fetch_json(OPENROUTER_URL)
        except Exception as e:
            print(f"Failed to fetch OpenRouter models data: {e}", file=sys.stderr)
        else:
            report("OpenRouter", collect_openrouter_rates(openrouter_data), local, args.provider, args.threshold_pct)

    print(
        "\nNote: this is a read-only comparison — install/default-config/pricing.yaml is not modified. "
        "Review flagged entries against the vendor's pricing page before editing rates by hand."
    )


if __name__ == "__main__":
    main()
