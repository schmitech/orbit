"""Regression tests for embedding usage extraction and request-level pricing."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from ai_services.implementations.embedding.openai_embedding_service import (
    OpenAIEmbeddingService,
)
from ai_services.services.embedding_service import EmbeddingService
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps._utils import add_usage_component, record_usage
from services.pricing_service import PricingService


def _openai_embedding_service(usages, batch_size=10):
    service = object.__new__(OpenAIEmbeddingService)
    service.initialized = True
    service.provider_name = "openai"
    service.model = "text-embedding-3-small"
    service.dimensions = 1536
    service.batch_size = batch_size
    responses = [
        SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(index)])
                for index in range(count)
            ],
            usage=SimpleNamespace(prompt_tokens=tokens, total_tokens=tokens),
        )
        for count, tokens in usages
    ]
    service.client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(side_effect=responses))
    )
    return service


def _container(pricing_service):
    services = {"pricing_service": pricing_service}
    container = MagicMock()
    container.has.side_effect = lambda key: key in services
    container.get.side_effect = lambda key: services[key]
    return container


def _pricing_service(include_embedding=True):
    openai_rates = {
        "gpt-test": {"input_per_1m": 1.0, "output_per_1m": 2.0},
    }
    if include_embedding:
        openai_rates["text-embedding-3-small"] = {
            "input_per_1m": 0.02,
            "output_per_1m": 0.0,
        }
    return PricingService({"pricing": {"providers": {"openai": openai_rates}}})


def _repository_pricing():
    root = Path(__file__).resolve().parents[2]
    with (root / "config" / "pricing.yaml").open(encoding="utf-8") as handle:
        return PricingService(yaml.safe_load(handle))


class LegacyEmbeddingService(EmbeddingService):
    """An unmigrated/local provider that must never receive usage_sink."""

    async def initialize(self):
        return True

    async def embed_query(self, text):
        return [1.0]

    async def embed_documents(self, texts):
        return [[1.0] for _ in texts]

    async def get_dimensions(self):
        return 1

    async def verify_connection(self):
        return True

    async def close(self):
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_query_reports_input_tokens():
    service = _openai_embedding_service([(1, 37)])
    usage = {}

    result = await service.embed_query_tracked("hello", usage_sink=usage)

    assert result == [0.0]
    assert usage == {
        "prompt_tokens": 37,
        "completion_tokens": 0,
        "total_tokens": 37,
        "reasoning_tokens": None,
        "model": "text-embedding-3-small",
        "provider": "openai",
        "reported": True,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_embedding_provider_drops_usage_sink():
    service = object.__new__(LegacyEmbeddingService)
    usage = {}

    assert await service.embed_query_tracked("hello", usage_sink=usage) == [1.0]
    assert await service.embed_documents_tracked(
        ["a", "b"], usage_sink=usage
    ) == [[1.0], [1.0]]
    assert usage == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openai_document_batches_accumulate_every_round_trip(monkeypatch):
    service = _openai_embedding_service([(2, 10), (2, 20), (1, 30)], batch_size=2)
    usage = {}
    monkeypatch.setattr(
        "ai_services.implementations.embedding.openai_embedding_service.asyncio.sleep",
        AsyncMock(),
    )

    result = await service.embed_documents_tracked(
        ["a", "b", "c", "d", "e"], usage_sink=usage
    )

    assert len(result) == 5
    assert usage["prompt_tokens"] == 60
    assert usage["completion_tokens"] == 0
    assert usage["total_tokens"] == 60
    assert usage["calls"] == 3
    assert len(usage["line_items"]) == 3


@pytest.mark.unit
def test_embedding_and_generation_are_priced_independently_then_summed():
    context = ProcessingContext()
    add_usage_component(
        context,
        {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "total_tokens": 1_000_000,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        },
        "embedding",
    )

    record_usage(
        _container(_pricing_service()),
        context,
        {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "total_tokens": 1_000_000,
            "reported": True,
        },
        "openai",
        "gpt-test",
    )

    usage = context.metadata["usage"]
    # Embedding tokens must not inflate the primary/generation token counts
    # mirrored onto the OpenAI-compatible response — they surface only via
    # embedding_prompt_tokens/embedding_cost_usd below.
    assert usage["prompt_tokens"] == 1_000_000
    assert usage["total_tokens"] == 1_000_000
    assert usage["cost_usd"] == pytest.approx(1.02)
    assert usage["embedding_prompt_tokens"] == 1_000_000
    assert usage["embedding_cost_usd"] == pytest.approx(0.02)


@pytest.mark.unit
def test_unpriced_embedding_does_not_silently_understate_total_cost():
    context = ProcessingContext()
    add_usage_component(
        context,
        {
            "prompt_tokens": 1_000,
            "completion_tokens": 0,
            "total_tokens": 1_000,
            "provider": "unknown",
            "model": "embedding-model",
            "reported": True,
        },
        "embedding",
    )

    record_usage(
        _container(_pricing_service(include_embedding=False)),
        context,
        {
            "prompt_tokens": 1_000,
            "completion_tokens": 100,
            "total_tokens": 1_100,
            "reported": True,
        },
        "openai",
        "gpt-test",
    )

    usage = context.metadata["usage"]
    assert usage["reported"] is True
    # The unpriced embedding line item must not blank out the generation
    # call's known, real cost -- only the priceable items are summed.
    assert usage["cost_usd"] == pytest.approx(0.0012)
    assert usage["pricing_source"] == "mixed"


@pytest.mark.unit
def test_repository_embedding_rates_cover_paid_unpriced_and_local_models():
    pricing = _repository_pricing()

    openai = pricing.estimate(
        "openai", "text-embedding-3-small", 1_000_000, 0
    )
    cohere = pricing.estimate("cohere", "embed-english-v3.0", 1_000_000, 0)
    local = pricing.estimate(
        "sentence_transformers", "BAAI/bge-m3", 1_000_000, 0
    )

    assert openai.cost_usd == pytest.approx(0.02)
    assert cohere.cost_usd is None
    assert cohere.pricing_source == "unpriced"
    assert local.cost_usd == 0.0
    assert local.pricing_source == "local_zero"


@pytest.mark.unit
def test_document_generation_unpriced_embedding_does_not_blank_out_cost():
    from inference.pipeline.steps.document_generation import DocumentGenerationStep

    context = ProcessingContext()
    add_usage_component(
        context,
        {
            "prompt_tokens": 1_000,
            "completion_tokens": 0,
            "total_tokens": 1_000,
            "provider": "nvidia",
            "model": "nv-embed-v1",
            "reported": True,
        },
        "embedding",
    )

    step = object.__new__(DocumentGenerationStep)
    step.container = _container(_pricing_service(include_embedding=False))

    step._record_spec_usage(
        context,
        [
            {
                "provider": "openai",
                "model": "gpt-test",
                "prompt_tokens": 1_000,
                "completion_tokens": 100,
            }
        ],
    )

    usage = context.metadata["usage"]
    assert usage["reported"] is True
    # An unpriced skill-routing embedding attempt must not blank out the
    # document-generation call's own known cost.
    assert usage["cost_usd"] == pytest.approx(0.0012)
    assert usage["pricing_source"] == "mixed"
    # Embedding tokens must not inflate the generation call's own totals.
    assert usage["prompt_tokens"] == 1_000
    assert usage["completion_tokens"] == 100
    assert usage["embedding_prompt_tokens"] == 1_000


@pytest.mark.unit
def test_document_generation_pricing_failure_never_raises():
    from inference.pipeline.steps.document_generation import DocumentGenerationStep

    context = ProcessingContext()
    add_usage_component(
        context,
        {
            "prompt_tokens": 1_000,
            "completion_tokens": 0,
            "total_tokens": 1_000,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        },
        "embedding",
    )
    pricing_service = MagicMock()
    pricing_service.estimate.side_effect = RuntimeError("pricing unavailable")
    step = object.__new__(DocumentGenerationStep)
    step.container = _container(pricing_service)

    step._record_spec_usage(
        context,
        [
            {
                "provider": "openai",
                "model": "gpt-test",
                "prompt_tokens": 1_000,
                "completion_tokens": 100,
            }
        ],
    )

    usage = context.metadata["usage"]
    assert usage["reported"] is True
    assert usage["cost_usd"] is None
    assert usage["embedding_prompt_tokens"] == 1_000
    assert "embedding_cost_usd" not in usage


@pytest.mark.unit
def test_media_generation_embedding_tokens_do_not_inflate_primary_totals():
    from inference.pipeline.steps._utils import record_media_generation_usage

    context = ProcessingContext()
    add_usage_component(
        context,
        {
            "prompt_tokens": 500,
            "completion_tokens": 0,
            "total_tokens": 500,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        },
        "embedding",
    )

    record_media_generation_usage(
        _container(_pricing_service()),
        context,
        "openai",
        "dall-e-3",
        media_usage={"unit": "images", "quantity": 1},
    )

    usage = context.metadata["usage"]
    assert usage["reported"] is True
    assert usage["embedding_prompt_tokens"] == 500
    assert usage["embedding_cost_usd"] == pytest.approx(0.00001)
    # Media-generation billing is per-image, not per-token — prompt_tokens
    # must stay None/absent, not silently become the embedding's token count.
    assert usage.get("prompt_tokens") in (None, 0)
    assert usage.get("total_tokens") in (None, 0)
