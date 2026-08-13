"""
Unit tests for inference/pipeline/steps/_utils.py::record_usage's handling of
multi-line-item ("mixed") requests — e.g. a multi-iteration MCP tool-calling
loop where more than one provider call contributed usage to the same turn.

Regression coverage: a request with N line items where fewer than N actually
resolved a price must still sum token counts across ALL items (so
prompt_tokens/cached_prompt_tokens reflect true usage) while cost_usd only
reflects the ones that priced — and this must be surfaced via a warning log,
since the audit ledger has no per-call breakdown to diagnose an
unexpectedly-low cost_usd after the fact.
"""

from unittest.mock import MagicMock

import pytest

from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps._utils import record_usage
from services.pricing_service import PricingService


def _make_container(pricing_service):
    services = {"pricing_service": pricing_service}
    container = MagicMock()
    container.has.side_effect = lambda key: key in services
    container.get.side_effect = lambda key: services[key]
    container.get_or_none.side_effect = lambda key: services.get(key)
    return container


def _pricing_service():
    return PricingService({
        "pricing": {
            "providers": {
                "anthropic": {
                    "claude-sonnet*": {
                        "input_per_1m": 3.0, "output_per_1m": 15.0, "cached_input_per_1m": 0.3,
                    },
                },
            },
        }
    })


@pytest.mark.unit
class TestRecordUsageMixedPricing:
    def test_unpriced_line_item_understates_cost_but_not_token_totals(self, caplog):
        """
        Two line items from the same turn (e.g. two MCP tool-loop iterations):
        one prices normally, the other has no matching pricing entry (its
        provider isn't configured at all). cost_usd must reflect only the
        priced item; prompt/cached/completion totals must still sum both.
        """
        container = _make_container(_pricing_service())
        context = ProcessingContext(message="hello", adapter_name="test-adapter")
        usage_sink = {
            "reported": True,
            "line_items": [
                {
                    "provider": "anthropic", "model": "claude-sonnet-5",
                    "prompt_tokens": 465, "cached_prompt_tokens": None,
                    "completion_tokens": 10, "total_tokens": 475, "reported": True,
                },
                {
                    "provider": "some-unconfigured-provider", "model": "whatever",
                    "prompt_tokens": 19266, "cached_prompt_tokens": 19266,
                    "completion_tokens": 14, "total_tokens": 19280, "reported": True,
                },
            ],
        }

        with caplog.at_level("WARNING"):
            record_usage(container, context, usage_sink, "anthropic", "claude-sonnet-5")

        usage = context.metadata["usage"]
        # Token totals sum across BOTH items regardless of pricing success.
        assert usage["prompt_tokens"] == 465 + 19266
        assert usage["cached_prompt_tokens"] == 19266
        assert usage["completion_tokens"] == 24
        # cost_usd only reflects the item that actually priced.
        assert usage["cost_usd"] == pytest.approx((465 / 1e6) * 3.0 + (10 / 1e6) * 15.0)
        assert usage["pricing_source"] == "mixed"
        assert any(r.levelname == "WARNING" and "mixed" in r.message for r in caplog.records)

    def test_mixed_via_differing_sources_logs_debug_not_warning(self, caplog):
        """
        'mixed' can also arise when every line item priced successfully but
        with different pricing_source labels (e.g. one 'exact', one
        'pattern') — e.g. an ordinary inference call plus a routine embedding
        call for skill routing/RAG/tool selection. That's completely normal,
        not exceptional, so it must log at DEBUG only — a WARNING here on
        every such turn would drown out the genuinely actionable case
        (a line item that failed to price at all).
        """
        container = _make_container(_pricing_service())
        context = ProcessingContext(message="hello", adapter_name="test-adapter")
        usage_sink = {
            "reported": True,
            "line_items": [
                {
                    "provider": "anthropic", "model": "claude-sonnet-5",
                    "prompt_tokens": 100, "cached_prompt_tokens": None,
                    "completion_tokens": 5, "total_tokens": 105, "reported": True,
                },
                {
                    # Exact-key match (vs. the other item's glob "pattern" match)
                    # so pricing_source differs even though both price fine.
                    "provider": "anthropic", "model": "claude-sonnet-exact",
                    "prompt_tokens": 10, "cached_prompt_tokens": None,
                    "completion_tokens": 1, "total_tokens": 11, "reported": True,
                },
            ],
        }
        pricing_service = _pricing_service()
        pricing_service._providers["anthropic"]["claude-sonnet-exact"] = \
            pricing_service._providers["anthropic"]["claude-sonnet*"]
        container = _make_container(pricing_service)

        with caplog.at_level("DEBUG"):
            record_usage(container, context, usage_sink, "anthropic", "claude-sonnet-5")

        usage = context.metadata["usage"]
        assert usage["pricing_source"] == "mixed"
        assert usage["cost_usd"] is not None and usage["cost_usd"] > 0
        assert not any(r.levelname == "WARNING" for r in caplog.records)
        assert any(r.levelname == "DEBUG" and "Multi-call request" in r.message for r in caplog.records)

    def test_both_items_priced_with_same_source_is_not_mixed(self):
        """Two calls to the same priceable provider/model must NOT be labeled
        'mixed' just for being multiple line items — only a pricing gap does."""
        container = _make_container(_pricing_service())
        context = ProcessingContext(message="hello", adapter_name="test-adapter")
        usage_sink = {
            "reported": True,
            "line_items": [
                {
                    "provider": "anthropic", "model": "claude-sonnet-5",
                    "prompt_tokens": 100, "cached_prompt_tokens": None,
                    "completion_tokens": 5, "total_tokens": 105, "reported": True,
                },
                {
                    "provider": "anthropic", "model": "claude-sonnet-5",
                    "prompt_tokens": 200, "cached_prompt_tokens": 50,
                    "completion_tokens": 10, "total_tokens": 210, "reported": True,
                },
            ],
        }

        record_usage(container, context, usage_sink, "anthropic", "claude-sonnet-5")

        usage = context.metadata["usage"]
        assert usage["pricing_source"] == "pattern"
        expected_cost = (
            (100 / 1e6) * 3.0 + (5 / 1e6) * 15.0
            + (150 / 1e6) * 3.0 + (50 / 1e6) * 0.3 + (10 / 1e6) * 15.0
        )
        assert usage["cost_usd"] == pytest.approx(expected_cost)
