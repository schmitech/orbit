"""Regression tests for embedding usage extraction and request-level pricing."""

import asyncio
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
    root = Path(__file__).resolve().parents[3]
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
@pytest.mark.asyncio
async def test_chunk_manager_reports_query_embedding_usage():
    from utils.chunk_manager import ChunkManager

    async def embed_query_tracked(_query, usage_sink):
        usage_sink.update({
            "prompt_tokens": 42,
            "completion_tokens": 0,
            "total_tokens": 42,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        })
        return [0.1, 0.2]

    embedding_client = SimpleNamespace(embed_query_tracked=embed_query_tracked)
    vector_store = SimpleNamespace(
        search_vectors=AsyncMock(return_value=[]),
    )
    manager = ChunkManager(vector_store, embedding_client)
    usage = {}

    await manager.retrieve_chunks("find this", usage_sink=usage)

    assert usage["reported"] is True
    assert usage["prompt_tokens"] == 42
    assert usage["provider"] == "openai"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chunk_manager_reports_batch_and_fallback_embedding_usage():
    from utils.chunk_manager import ChunkManager

    async def embed_documents_tracked(texts, usage_sink):
        usage_sink.update({
            "prompt_tokens": len(texts) * 10,
            "completion_tokens": 0,
            "total_tokens": len(texts) * 10,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        })
        return [[0.1] for _ in texts]

    async def embed_query_tracked(_text, usage_sink):
        usage_sink.update({
            "prompt_tokens": 10,
            "completion_tokens": 0,
            "total_tokens": 10,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        })
        return [0.1]

    manager = ChunkManager(
        MagicMock(),
        SimpleNamespace(
            embed_documents_tracked=embed_documents_tracked,
            embed_query_tracked=embed_query_tracked,
        ),
    )
    usage = {}

    await manager._embed_chunks_safely(["one", "two"], usage_sink=usage)
    await manager._embed_chunks_individually(["three", "four"], usage_sink=usage)

    assert usage["prompt_tokens"] == 40
    assert len(usage["line_items"]) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_firecrawl_forwards_usage_to_template_matching():
    from retrievers.implementations.intent.intent_firecrawl_retriever import (
        IntentFirecrawlRetriever,
    )

    retriever = object.__new__(IntentFirecrawlRetriever)
    retriever._find_best_templates = AsyncMock(return_value=[])
    usage = {}

    await retriever.get_relevant_context("find docs", usage_sink=usage)

    retriever._find_best_templates.assert_awaited_once_with(
        "find docs", usage_sink=usage
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_context_retrieval_finalizes_billed_embedding_usage():
    from inference.pipeline.steps.context_retrieval import ContextRetrievalStep

    async def get_relevant_context(**kwargs):
        kwargs["usage_sink"].update({
            "prompt_tokens": 500,
            "completion_tokens": 0,
            "total_tokens": 500,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        })
        raise RuntimeError("vector store unavailable")

    step = object.__new__(ContextRetrievalStep)
    step.container = _container(_pricing_service())
    step._get_retriever = AsyncMock(
        return_value=SimpleNamespace(get_relevant_context=get_relevant_context)
    )
    step._get_capabilities = MagicMock(return_value=None)
    step._build_retriever_kwargs = MagicMock(return_value={})
    context = ProcessingContext(message="find docs", adapter_name="files")

    result = await step.process(context)

    assert result.has_error()
    assert result.metadata["usage"]["embedding_prompt_tokens"] == 500
    assert result.metadata["usage"]["embedding_cost_usd"] == pytest.approx(0.00001)
    assert "_usage_components" not in result.metadata


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancelled_context_retrieval_halts_pipeline_without_losing_cost():
    from inference.pipeline.pipeline import InferencePipeline
    from inference.pipeline.steps.context_retrieval import ContextRetrievalStep

    cancel_event = asyncio.Event()

    async def get_relevant_context(**kwargs):
        kwargs["usage_sink"].update({
            "prompt_tokens": 500,
            "completion_tokens": 0,
            "total_tokens": 500,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        })
        cancel_event.set()
        return []

    container = _container(_pricing_service())
    retrieval_step = object.__new__(ContextRetrievalStep)
    retrieval_step.container = container
    retrieval_step._get_retriever = AsyncMock(
        return_value=SimpleNamespace(get_relevant_context=get_relevant_context)
    )
    retrieval_step._get_capabilities = MagicMock(return_value=None)
    retrieval_step._build_retriever_kwargs = MagicMock(return_value={})
    retrieval_step.should_execute = MagicMock(return_value=True)
    retrieval_step.pre_process = AsyncMock()
    retrieval_step.post_process = AsyncMock()

    next_step = MagicMock()
    next_step.should_execute.return_value = True
    next_step.get_name.return_value = "GenerationStep"
    next_step.pre_process = AsyncMock()
    next_step.process = AsyncMock()
    next_step.post_process = AsyncMock()

    context = ProcessingContext(
        message="find docs",
        adapter_name="files",
        cancel_event=cancel_event,
    )
    result = await InferencePipeline(
        [retrieval_step, next_step], container
    ).process(context)

    assert result.has_error()
    assert result.is_blocked is True
    next_step.process.assert_not_awaited()
    assert result.metadata["usage"]["embedding_prompt_tokens"] == 500
    assert result.metadata["usage"]["embedding_cost_usd"] == pytest.approx(0.00001)


@pytest.mark.unit
def test_missing_embedding_token_fields_are_priced_as_zero():
    context = ProcessingContext()
    add_usage_component(
        context,
        {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
            "line_items": [{
                "provider": "openai",
                "model": "text-embedding-3-small",
                "reported": True,
            }],
        },
        "embedding",
    )
    pricing_service = MagicMock()
    pricing_service.estimate.return_value = SimpleNamespace(
        cost_usd=0.0,
        input_rate_per_1m=0.02,
        output_rate_per_1m=0.0,
        pricing_source="exact",
    )

    record_usage(
        _container(pricing_service), context, {}, "openai", "gpt-test"
    )

    assert context.metadata["usage"]["call_type"] == "embedding"
    assert context.metadata["usage"]["cost_usd"] == 0.0
    assert pricing_service.estimate.call_count == 1
    for call in pricing_service.estimate.call_args_list:
        assert call.args[2:] == (0, 0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multimodal_forwards_usage_to_file_retriever(monkeypatch):
    from implementations.passthrough.multimodal.multimodal_implementation import (
        MultimodalImplementation,
    )

    monkeypatch.setattr(
        "retrievers.base.base_retriever.BaseRetriever.get_relevant_context",
        AsyncMock(return_value=[]),
    )
    retriever = object.__new__(MultimodalImplementation)
    retriever.initialize = AsyncMock()
    retriever._file_retriever = SimpleNamespace(
        get_relevant_context=AsyncMock(return_value=[])
    )
    usage = {}

    await retriever.get_relevant_context(
        "find file", api_key="key", file_ids=["file-1"], usage_sink=usage
    )

    retriever._file_retriever.get_relevant_context.assert_awaited_once_with(
        query="find file",
        api_key="key",
        file_ids=["file-1"],
        collection_name=None,
        usage_sink=usage,
    )


@pytest.mark.unit
def test_embedding_and_generation_are_priced_as_separate_audit_events():
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
    assert usage["prompt_tokens"] == 1_000_000
    assert usage["total_tokens"] == 1_000_000
    assert usage["cost_usd"] == pytest.approx(1.0)
    embedding_usage = context.metadata["embedding_usage"]
    assert embedding_usage["call_type"] == "embedding"
    assert embedding_usage["embedding_prompt_tokens"] == 1_000_000
    assert embedding_usage["cost_usd"] == pytest.approx(0.02)


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
    assert usage["pricing_source"] == "exact"
    assert context.metadata["embedding_usage"]["pricing_source"] == "unpriced"


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
    assert usage["pricing_source"] == "exact"
    # Embedding tokens must not inflate the generation call's own totals.
    assert usage["prompt_tokens"] == 1_000
    assert usage["completion_tokens"] == 100
    assert context.metadata["embedding_usage"]["embedding_prompt_tokens"] == 1_000


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
    embedding_usage = context.metadata["embedding_usage"]
    assert embedding_usage["embedding_prompt_tokens"] == 1_000
    assert "embedding_cost_usd" not in embedding_usage


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
        call_type="image",
        media_usage={"unit": "images", "quantity": 1},
    )

    usage = context.metadata["usage"]
    assert usage["reported"] is True
    embedding_usage = context.metadata["embedding_usage"]
    assert embedding_usage["embedding_prompt_tokens"] == 500
    assert embedding_usage["cost_usd"] == pytest.approx(0.00001)
    # Media-generation billing is per-image, not per-token — prompt_tokens
    # must stay None/absent, not silently become the embedding's token count.
    assert usage.get("prompt_tokens") in (None, 0)
    assert usage.get("total_tokens") in (None, 0)
