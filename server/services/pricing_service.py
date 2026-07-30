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
    # Optional tiered rate for providers that bill audio tokens separately
    # from text (e.g. OpenAI Realtime). None means "no separate audio tier
    # configured" — audio tokens reported against a rate lacking these are
    # priced as unpriced, never silently folded into the text rate.
    audio_input_per_1m: Optional[float] = None
    audio_output_per_1m: Optional[float] = None


@dataclass
class CostEstimate:
    cost_usd: Optional[float]
    input_rate_per_1m: Optional[float]
    output_rate_per_1m: Optional[float]
    pricing_source: str  # exact | pattern | provider_default | local_zero | unpriced


@dataclass
class MediaRate:
    unit: str
    per_unit: Optional[float]


@dataclass
class MediaCostEstimate:
    cost_usd: Optional[float]
    unit: Optional[str]
    per_unit: Optional[float]
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
                    audio_input_per_1m=rate.get('audio_input_per_1m'),
                    audio_output_per_1m=rate.get('audio_output_per_1m'),
                )
            self._providers[provider] = rates

        self._media_providers: Dict[str, Dict[str, MediaRate]] = {}
        for provider, models in (pricing_config.get('media', {}) or {}).items():
            rates: Dict[str, MediaRate] = {}
            for model_pattern, rate in (models or {}).items():
                rates[model_pattern] = MediaRate(
                    unit=rate.get('unit'),
                    per_unit=rate.get('per_unit'),
                )
            self._media_providers[provider] = rates

        self._warned_pairs = set()
        self._warned_media_pairs = set()

    @staticmethod
    def _resolve_rate_with_source(
        rates_by_provider: Dict[str, Dict[str, Any]], provider: Optional[str], model: Optional[str]
    ) -> "tuple[Optional[Any], Optional[str]]":
        """
        Generic exact -> longest-glob -> provider-"*"-default matcher, shared
        by the text (ModelRate) and media (MediaRate) rate tables — both are
        keyed identically ({provider: {model_pattern: rate}}), only the rate
        payload shape differs.
        """
        if not provider:
            return None, None
        rates = rates_by_provider.get(provider)
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
        return self._resolve_rate_with_source(self._providers, provider, model)

    def estimate(
        self,
        provider: Optional[str],
        model: Optional[str],
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        audio_prompt_tokens: Optional[int] = None,
        audio_completion_tokens: Optional[int] = None,
    ) -> CostEstimate:
        """
        Estimate cost for text tokens, plus an optional audio-token portion
        (e.g. OpenAI Realtime voice sessions) billed at a separate tier.
        Audio tokens present without a configured audio rate are reported as
        unpriced rather than silently priced at the text rate — audio tokens
        typically cost far more (~10-20x) than text, so folding them into the
        text rate would materially understate cost.
        """
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

        has_audio_tokens = bool(audio_prompt_tokens) or bool(audio_completion_tokens)
        if has_audio_tokens and (rate.audio_input_per_1m is None or rate.audio_output_per_1m is None):
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

        if has_audio_tokens:
            cost += (audio_prompt_tokens or 0) / 1_000_000.0 * rate.audio_input_per_1m
            cost += (audio_completion_tokens or 0) / 1_000_000.0 * rate.audio_output_per_1m

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

    def estimate_media(
        self,
        provider: Optional[str],
        model: Optional[str],
        unit: Optional[str],
        quantity: Optional[float],
    ) -> MediaCostEstimate:
        """
        Estimate cost for a discrete-unit media call (images, video seconds,
        TTS characters, STT seconds, OCR pages). Uses the same exact ->
        longest-glob -> provider-"*" matching as text pricing, against the
        separate pricing.media rate table (keyed the same way).
        """
        rate, matched_source = self._resolve_rate_with_source(self._media_providers, provider, model)
        if rate is None:
            self._warn_unpriced_media(provider, model)
            return MediaCostEstimate(cost_usd=None, unit=unit, per_unit=None, pricing_source="unpriced")

        if rate.per_unit is None:
            return MediaCostEstimate(cost_usd=None, unit=rate.unit, per_unit=None, pricing_source="unpriced")

        # A resolved rate for a different unit than what was actually
        # reported (e.g. rate configured in "seconds" but the caller reports
        # "images") is a configuration mismatch — report unpriced rather than
        # silently multiplying the wrong quantity by the wrong rate. Exempt
        # the provider-"*" catch-all: a single local provider (ollama,
        # whisper, ...) can serve several media categories, so its fallback
        # entry may reasonably omit "unit" entirely and just declare
        # per_unit — that's how every local-provider $0.00 entry is written.
        if unit and rate.unit and unit != rate.unit and matched_source != "provider_default":
            return MediaCostEstimate(cost_usd=None, unit=unit, per_unit=None, pricing_source="unpriced")

        quantity = quantity or 0.0
        cost = quantity * rate.per_unit
        source = "local_zero" if rate.per_unit == 0.0 else matched_source

        return MediaCostEstimate(
            cost_usd=round(cost, 6),
            unit=rate.unit or unit,
            per_unit=rate.per_unit,
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

    def _warn_unpriced_media(self, provider: Optional[str], model: Optional[str]) -> None:
        key = (provider, model)
        if key in self._warned_media_pairs:
            return
        self._warned_media_pairs.add(key)
        logger.warning(
            "No media pricing entry for provider=%s model=%s — cost will be reported as unpriced. "
            "Add a rate to config/pricing.yaml under pricing.media.", provider, model,
        )
