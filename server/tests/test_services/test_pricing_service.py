"""Tests for server.services.pricing_service.PricingService."""

import pytest

from services.pricing_service import PricingService


def make_config(providers, media=None):
    pricing = {
        "currency": "USD",
        "updated": "2026-01-01",
        "providers": providers,
    }
    if media is not None:
        pricing["media"] = media
    return {"pricing": pricing}


@pytest.mark.unit
class TestPricingServiceResolve:
    def test_exact_match(self):
        svc = PricingService(make_config({
            "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
        }))
        rate = svc.resolve("openai", "gpt-4o-mini")
        assert rate.input_per_1m == 0.15
        assert rate.output_per_1m == 0.60

    def test_longest_glob_wins_over_shorter_glob(self):
        svc = PricingService(make_config({
            "openai": {
                "gpt-4o-mini*": {"input_per_1m": 0.15, "output_per_1m": 0.60},
                "gpt-4o*": {"input_per_1m": 2.50, "output_per_1m": 10.00},
            },
        }))
        rate = svc.resolve("openai", "gpt-4o-mini-2024-07-18")
        assert rate.input_per_1m == 0.15

    def test_versioned_suffix_matches_glob(self):
        svc = PricingService(make_config({
            "anthropic": {"claude-sonnet-4*": {"input_per_1m": 3.0, "output_per_1m": 15.0}},
        }))
        rate = svc.resolve("anthropic", "claude-sonnet-4-6-20250929")
        assert rate.input_per_1m == 3.0

    def test_provider_wildcard_default(self):
        svc = PricingService(make_config({
            "groq": {"*": {"input_per_1m": 0.05, "output_per_1m": 0.08}},
        }))
        rate = svc.resolve("groq", "llama-3.1-8b-instant")
        assert rate.input_per_1m == 0.05

    def test_unknown_provider_returns_none(self):
        svc = PricingService(make_config({"openai": {"*": {"input_per_1m": 1, "output_per_1m": 1}}}))
        assert svc.resolve("nonexistent", "some-model") is None

    def test_unknown_model_no_wildcard_returns_none(self):
        svc = PricingService(make_config({
            "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
        }))
        assert svc.resolve("openai", "gpt-9000") is None


@pytest.mark.unit
class TestPricingServiceEstimate:
    def test_arithmetic(self):
        svc = PricingService(make_config({
            "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
        }))
        estimate = svc.estimate("openai", "gpt-4o-mini", prompt_tokens=1_500_000, completion_tokens=0)
        assert estimate.cost_usd == pytest.approx(0.225)
        assert estimate.pricing_source == "exact"

    def test_miss_returns_none_not_zero(self):
        svc = PricingService(make_config({
            "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
        }))
        estimate = svc.estimate("openai", "totally-unknown-model", prompt_tokens=1000, completion_tokens=1000)
        assert estimate.cost_usd is None
        assert estimate.pricing_source == "unpriced"

    def test_explicit_zero_rate_is_local_zero_not_unpriced(self):
        svc = PricingService(make_config({
            "ollama": {"*": {"input_per_1m": 0.0, "output_per_1m": 0.0}},
        }))
        estimate = svc.estimate("ollama", "llama3", prompt_tokens=1000, completion_tokens=1000)
        assert estimate.cost_usd == 0.0
        assert estimate.pricing_source == "local_zero"

    def test_unknown_provider_returns_unpriced(self):
        svc = PricingService(make_config({}))
        estimate = svc.estimate("mystery", "model", prompt_tokens=100, completion_tokens=100)
        assert estimate.cost_usd is None
        assert estimate.pricing_source == "unpriced"

    def test_pattern_source_label(self):
        svc = PricingService(make_config({
            "anthropic": {"claude-sonnet-4*": {"input_per_1m": 3.0, "output_per_1m": 15.0}},
        }))
        estimate = svc.estimate("anthropic", "claude-sonnet-4-6", prompt_tokens=1000, completion_tokens=1000)
        assert estimate.pricing_source == "pattern"

    def test_provider_default_source_label(self):
        svc = PricingService(make_config({
            "groq": {"*": {"input_per_1m": 0.05, "output_per_1m": 0.08}},
        }))
        estimate = svc.estimate("groq", "some-new-model", prompt_tokens=1000, completion_tokens=1000)
        assert estimate.pricing_source == "provider_default"

    def test_provider_default_label_only_when_default_actually_matched(self):
        """A provider with BOTH specific patterns and a "*" fallback must label
        an unmatched model provider_default (the "*" match), not pattern —
        the source must reflect which rule actually produced the rate, not
        merely that some pattern exists somewhere on the provider."""
        svc = PricingService(make_config({
            "openai": {
                "gpt-4o-mini*": {"input_per_1m": 0.15, "output_per_1m": 0.60},
                "*": {"input_per_1m": 1.0, "output_per_1m": 2.0},
            },
        }))
        estimate = svc.estimate("openai", "some-unlisted-model", prompt_tokens=1000, completion_tokens=1000)
        assert estimate.pricing_source == "provider_default"
        assert estimate.input_rate_per_1m == 1.0


@pytest.mark.unit
class TestPricingServiceAudioTiering:
    def test_audio_tokens_priced_at_audio_tier(self):
        svc = PricingService(make_config({
            "openai": {"gpt-realtime*": {
                "input_per_1m": 4.0, "output_per_1m": 16.0,
                "audio_input_per_1m": 32.0, "audio_output_per_1m": 64.0,
            }},
        }))
        estimate = svc.estimate(
            "openai", "gpt-realtime",
            prompt_tokens=1_000_000, completion_tokens=1_000_000,
            audio_prompt_tokens=1_000_000, audio_completion_tokens=1_000_000,
        )
        # text: 4 + 16 = 20; audio: 32 + 64 = 96; total 116
        assert estimate.cost_usd == pytest.approx(116.0)
        assert estimate.pricing_source == "pattern"

    def test_audio_tokens_without_audio_rate_are_unpriced(self):
        """A model with a text rate but no configured audio tier must not
        silently fold audio tokens into the text rate — audio is billed far
        higher, so a wrong number is worse than a flagged gap."""
        svc = PricingService(make_config({
            "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
        }))
        estimate = svc.estimate(
            "openai", "gpt-4o-mini",
            prompt_tokens=1000, completion_tokens=1000,
            audio_prompt_tokens=1000, audio_completion_tokens=1000,
        )
        assert estimate.cost_usd is None
        assert estimate.pricing_source == "unpriced"

    def test_no_audio_tokens_unaffected_by_missing_audio_rate(self):
        """A model with no audio tier configured must still price normally
        when the call has no audio tokens at all."""
        svc = PricingService(make_config({
            "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
        }))
        estimate = svc.estimate("openai", "gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=0)
        assert estimate.cost_usd == pytest.approx(0.15)
        assert estimate.pricing_source == "exact"


@pytest.mark.unit
class TestPricingServiceMedia:
    def test_media_arithmetic(self):
        svc = PricingService(make_config({}, media={
            "openai": {"dall-e-3*": {"unit": "images", "per_unit": 0.04}},
        }))
        estimate = svc.estimate_media("openai", "dall-e-3", "images", 3)
        assert estimate.cost_usd == pytest.approx(0.12)
        assert estimate.pricing_source == "pattern"
        assert estimate.unit == "images"

    def test_media_unit_mismatch_is_unpriced(self):
        """A resolved rate for a different unit than what was actually
        reported (a configuration mistake) must not silently price the
        wrong quantity against the wrong rate."""
        svc = PricingService(make_config({}, media={
            "openai": {"dall-e-3*": {"unit": "images", "per_unit": 0.04}},
        }))
        estimate = svc.estimate_media("openai", "dall-e-3", "seconds", 3)
        assert estimate.cost_usd is None
        assert estimate.pricing_source == "unpriced"

    def test_media_unknown_model_is_unpriced_not_zero(self):
        svc = PricingService(make_config({}, media={
            "openai": {"dall-e-3*": {"unit": "images", "per_unit": 0.04}},
        }))
        estimate = svc.estimate_media("openai", "totally-unknown-model", "images", 1)
        assert estimate.cost_usd is None
        assert estimate.pricing_source == "unpriced"

    def test_media_local_zero_provider_default_ignores_unit(self):
        """A local provider's bare "*" fallback may omit `unit` entirely
        (it can serve several media categories under one provider name) —
        the unit-mismatch guard must not apply to it."""
        svc = PricingService(make_config({}, media={
            "ollama": {"*": {"per_unit": 0.0}},
        }))
        estimate = svc.estimate_media("ollama", "llava", "images", 5)
        assert estimate.cost_usd == 0.0
        assert estimate.pricing_source == "local_zero"
        assert estimate.unit == "images"

    def test_media_pattern_local_zero_still_enforces_unit(self):
        """Unlike the provider-"*" catch-all, an explicit pattern/exact media
        rate that declares a unit must still guard against a mismatch, even
        when priced at $0."""
        svc = PricingService(make_config({}, media={
            "ollama": {"llava*": {"unit": "images", "per_unit": 0.0}},
        }))
        estimate = svc.estimate_media("ollama", "llava", "seconds", 5)
        assert estimate.cost_usd is None
        assert estimate.pricing_source == "unpriced"
