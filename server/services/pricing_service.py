"""
Pricing Service
===============

Resolves a per-request cost estimate from a local, hand-maintained rate table
(config/pricing.yaml) rather than any provider billing API. Cost is an
estimate, not an invoice — see docs on config/pricing.yaml.
"""

import logging
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelRate:
    input_per_1m: Optional[float]
    output_per_1m: Optional[float]


@dataclass
class CostEstimate:
    cost_usd: Optional[float]
    input_rate_per_1m: Optional[float]
    output_rate_per_1m: Optional[float]
    pricing_source: str  # exact | pattern | provider_default | local_zero | unpriced


class PricingService:
    """
    Sync, in-memory pricing lookup. No I/O after construction.

    Matching order for a (provider, model) pair: exact model key, then the
    longest-matching glob pattern (so "gpt-4o-mini" beats "gpt-4o*" beats
    "*"), then a provider-level "*" default, else unpriced.
    """

    def __init__(self, config: Dict[str, Any]):
        pricing_config = (config or {}).get('pricing', {}) or {}
        self._currency = pricing_config.get('currency', 'USD')
        self._updated = pricing_config.get('updated')
        self._stale_after_days = pricing_config.get('stale_after_days', 120)
        self._providers: Dict[str, Dict[str, ModelRate]] = {}
        for provider, models in (pricing_config.get('providers', {}) or {}).items():
            rates: Dict[str, ModelRate] = {}
            for model_pattern, rate in (models or {}).items():
                rates[model_pattern] = ModelRate(
                    input_per_1m=rate.get('input_per_1m'),
                    output_per_1m=rate.get('output_per_1m'),
                )
            self._providers[provider] = rates
        self._warned_pairs = set()

    @property
    def updated(self) -> Optional[str]:
        return self._updated

    @property
    def currency(self) -> str:
        return self._currency

    def resolve(self, provider: Optional[str], model: Optional[str]) -> Optional[ModelRate]:
        """Return the matching ModelRate, or None if nothing matches."""
        rate, _source = self._resolve_with_source(provider, model)
        return rate

    def _resolve_with_source(
        self, provider: Optional[str], model: Optional[str]
    ) -> "tuple[Optional[ModelRate], Optional[str]]":
        """
        Return (rate, source) where source names the match that actually
        produced the rate — "exact" | "pattern" | "provider_default" — so
        the caller never has to re-derive provenance from unrelated
        presence checks (e.g. "some other pattern exists on this provider").
        """
        if not provider:
            return None, None
        rates = self._providers.get(provider)
        if not rates:
            return None, None

        if model and model in rates:
            return rates[model], "exact"

        if model:
            # Longest pattern wins so specific patterns beat generic ones
            # (e.g. "gpt-4o-mini" exact already handled above; among globs,
            # "gpt-4o*" should beat a bare "*").
            candidates = [p for p in rates if p != "*" and "*" in p]
            for pattern in sorted(candidates, key=len, reverse=True):
                if fnmatch(model, pattern):
                    return rates[pattern], "pattern"

        if "*" in rates:
            return rates["*"], "provider_default"

        return None, None

    def estimate(
        self,
        provider: Optional[str],
        model: Optional[str],
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
    ) -> CostEstimate:
        rate, matched_source = self._resolve_with_source(provider, model)
        if rate is None:
            self._warn_unpriced(provider, model)
            return CostEstimate(
                cost_usd=None,
                input_rate_per_1m=None,
                output_rate_per_1m=None,
                pricing_source="unpriced",
            )

        if rate.input_per_1m is None or rate.output_per_1m is None:
            return CostEstimate(
                cost_usd=None,
                input_rate_per_1m=rate.input_per_1m,
                output_rate_per_1m=rate.output_per_1m,
                pricing_source="unpriced",
            )

        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        cost = (prompt_tokens / 1_000_000.0) * rate.input_per_1m + \
               (completion_tokens / 1_000_000.0) * rate.output_per_1m

        # local_zero is a priced-zero (a real "$0" rate) — takes precedence over
        # the structural exact/pattern/provider_default label so the UI can tell
        # "known free" apart from "no rate configured" (see "unpriced" above).
        source = "local_zero" if (rate.input_per_1m == 0.0 and rate.output_per_1m == 0.0) else matched_source

        return CostEstimate(
            cost_usd=round(cost, 6),
            input_rate_per_1m=rate.input_per_1m,
            output_rate_per_1m=rate.output_per_1m,
            pricing_source=source,
        )

    def _warn_unpriced(self, provider: Optional[str], model: Optional[str]) -> None:
        key = (provider, model)
        if key in self._warned_pairs:
            return
        self._warned_pairs.add(key)
        logger.warning(
            "No pricing entry for provider=%s model=%s — cost will be reported as unpriced. "
            "Add a rate to config/pricing.yaml.", provider, model,
        )
