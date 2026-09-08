"""
Phase 3 gate: document-safe, bounded embedding recovery.

Covers server/utils/embedding_recovery.py directly plus the ChunkManager
integration point that consumes it (document fallback must never call
embed_query, and usage/provenance must survive splits and retries).
"""

import asyncio
import time

import pytest
from utils.embedding_budget import resolve_embedding_budget
from utils.embedding_recovery import (
    FailureCategory,
    RecoveryConfig,
    classify_embedding_error,
    embed_documents_with_recovery,
)

pytestmark = pytest.mark.unit


def _budget(max_tokens=100):
    return resolve_embedding_budget(max_embedding_tokens=max_tokens, safety_margin=1.0)


class FakeError(Exception):
    """A structured provider-style error: attributes only, no message reliance."""

    def __init__(self, status_code=None, code=None, retry_after=None, message="error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        if retry_after is not None:
            self.retry_after = retry_after


class QueryCallingClient:
    """Fails the test if document ingestion ever reaches a query embedding API."""

    def __init__(self, dimension=4):
        self.dimension = dimension
        self.embed_documents_tracked_calls = []

    async def embed_query(self, text, usage_sink=None):
        raise AssertionError("document ingestion must never call embed_query()")

    async def embed_query_tracked(self, text, usage_sink=None):
        raise AssertionError("document ingestion must never call embed_query_tracked()")

    async def embed_documents_tracked(self, texts, usage_sink=None):
        self.embed_documents_tracked_calls.append(list(texts))
        if usage_sink is not None:
            usage_sink.update({
                "prompt_tokens": len(texts) * 3,
                "completion_tokens": 0,
                "total_tokens": len(texts) * 3,
                "provider": "fake",
                "model": "fake-model",
                "reported": True,
            })
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class UntrackedClient:
    """No *_tracked methods -- exercises the untracked embed_documents path."""

    def __init__(self):
        self.calls = []

    async def embed_documents(self, texts):
        self.calls.append(list(texts))
        return [[0.5, 0.5] for _ in texts]


class ScriptedClient:
    """Replays one outcome per call to embed_documents_tracked: an exception,
    a vector-response callable, or a plain list of vectors."""

    def __init__(self, outcomes, batch_size=None, aggregate_token_limit=None):
        self.outcomes = list(outcomes)
        self.calls = []
        if batch_size is not None:
            self.batch_size = batch_size
        if aggregate_token_limit is not None:
            self.aggregate_token_limit = aggregate_token_limit

    async def embed_documents_tracked(self, texts, usage_sink=None):
        self.calls.append(list(texts))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome = outcome(texts)
        if usage_sink is not None:
            usage_sink.update({
                "prompt_tokens": len(texts),
                "completion_tokens": 0,
                "total_tokens": len(texts),
                "provider": "fake",
                "model": "fake-model",
                "reported": True,
            })
        return outcome


async def _fake_sleep(_seconds):
    return None


def _no_delay_config(**overrides):
    kwargs = {"max_attempts": 5, "deadline_seconds": 30.0, "base_delay": 0.01, "max_delay": 0.02, "max_concurrency": 4}
    kwargs.update(overrides)
    return RecoveryConfig(**kwargs)


# ---------------------------------------------------------------------------
# Document vs query API usage: normal, singleton, tracked, and untracked paths
# ---------------------------------------------------------------------------

async def test_normal_batch_uses_document_api_only():
    client = QueryCallingClient()
    result = await embed_documents_with_recovery(client, ["a", "b", "c"], _budget())

    assert result.ok
    assert [p.vector for p in result.pieces] == [[0.1, 0.2, 0.3, 0.4]] * 3
    assert client.embed_documents_tracked_calls == [["a", "b", "c"]]


async def test_singleton_fallback_uses_document_api_not_query_api():
    client = QueryCallingClient()
    result = await embed_documents_with_recovery(client, ["solo"], _budget())

    assert result.ok
    assert client.embed_documents_tracked_calls == [["solo"]]


async def test_untracked_client_uses_embed_documents():
    client = UntrackedClient()
    result = await embed_documents_with_recovery(client, ["x", "y"], _budget())

    assert result.ok
    assert client.calls == [["x", "y"]]
    assert [p.vector for p in result.pieces] == [[0.5, 0.5], [0.5, 0.5]]


async def test_tracked_usage_is_accumulated_across_batches():
    client = ScriptedClient([[[0.1]], [[0.2]]], batch_size=1)
    usage = {}
    result = await embed_documents_with_recovery(
        client, ["a", "b"], _budget(), usage_sink=usage, config=_no_delay_config(),
    )

    assert result.ok
    assert usage["prompt_tokens"] == 2
    assert usage["calls"] == 2


# ---------------------------------------------------------------------------
# Ordering, mapping, and response validation
# ---------------------------------------------------------------------------

async def test_ordering_preserved_under_batch_partitioning():
    client = ScriptedClient(
        [[[0.0] for _ in range(2)], [[1.0] for _ in range(2)]], batch_size=2,
    )
    result = await embed_documents_with_recovery(client, ["a", "b", "c", "d"], _budget())

    assert result.ok
    assert [p.source_index for p in result.pieces] == [0, 1, 2, 3]


async def test_individual_failure_does_not_disturb_surviving_order():
    def batch_two(texts):
        return [[0.0], FakeError(status_code=500)][:len(texts)] if False else None

    # First batch [a, b] fails outright (unknown), second batch [c, d] succeeds.
    client = ScriptedClient(
        [FakeError(status_code=418), [[9.0], [9.0]]], batch_size=2,
    )
    result = await embed_documents_with_recovery(
        client, ["a", "b", "c", "d"], _budget(), config=_no_delay_config(),
    )

    assert sorted(result.failed_indices) == [0, 1]
    assert [p.source_index for p in result.pieces] == [2, 3]


async def test_short_response_is_malformed():
    client = ScriptedClient([[[0.1]]])  # one vector for two inputs
    result = await embed_documents_with_recovery(
        client, ["a", "b"], _budget(), config=_no_delay_config(),
    )

    assert result.failed_indices == [0, 1]
    assert result.failure_reasons[0] == FailureCategory.MALFORMED


async def test_empty_response_is_malformed():
    client = ScriptedClient([[]])
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(), config=_no_delay_config(),
    )
    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.MALFORMED


async def test_wrong_dimensional_response_is_malformed():
    client = ScriptedClient([[[0.1, 0.2], [0.1]]])  # inconsistent dimensions
    result = await embed_documents_with_recovery(
        client, ["a", "b"], _budget(), config=_no_delay_config(),
    )
    assert result.failed_indices == [0, 1]
    assert result.failure_reasons[0] == FailureCategory.MALFORMED


async def test_nonfinite_response_is_malformed():
    client = ScriptedClient([[[0.1, float("nan")]]])
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(), config=_no_delay_config(),
    )
    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.MALFORMED


# ---------------------------------------------------------------------------
# Error classification (structured status/code, not a bare "token" match)
# ---------------------------------------------------------------------------

def test_classifier_uses_status_code_for_auth():
    classified = classify_embedding_error(FakeError(status_code=401))
    assert classified.category == FailureCategory.AUTH


def test_classifier_uses_status_code_for_rate_limit():
    classified = classify_embedding_error(FakeError(status_code=429, retry_after=2.5))
    assert classified.category == FailureCategory.TRANSIENT
    assert classified.retry_after == 2.5


def test_classifier_uses_structured_code_for_context_length():
    # Message deliberately contains no recognizable keyword; only .code matters.
    classified = classify_embedding_error(
        FakeError(status_code=400, code="context_length_exceeded", message="nope")
    )
    assert classified.category == FailureCategory.PER_INPUT_CONTEXT_EXCEEDED


def test_classifier_uses_structured_code_for_batch_size():
    classified = classify_embedding_error(FakeError(status_code=413, code="request_too_large"))
    assert classified.category == FailureCategory.BATCH_SIZE_EXCEEDED


def test_classifier_does_not_use_bare_token_word_as_signal():
    # A message containing "token" with no structured status/code must not
    # be classified as context-exceeded -- it falls through to unknown.
    classified = classify_embedding_error(Exception("something about a token happened"))
    assert classified.category == FailureCategory.UNKNOWN


def test_classifier_unwraps_provider_service_error():
    from ai_services.errors import ProviderServiceError

    original = FakeError(status_code=401)
    wrapped = ProviderServiceError("sanitized", original_error=original, provider="openai")
    assert classify_embedding_error(wrapped).category == FailureCategory.AUTH


# ---------------------------------------------------------------------------
# Per-category recovery policy: attempts, limits, delays, terminal reason
# ---------------------------------------------------------------------------

async def test_auth_error_stops_without_fan_out_to_individual_calls():
    client = ScriptedClient([FakeError(status_code=401)] * 5, batch_size=3)
    result = await embed_documents_with_recovery(
        client, ["a", "b", "c"], _budget(), config=_no_delay_config(),
    )

    assert result.terminal_error.category == FailureCategory.AUTH
    assert sorted(result.failed_indices) == [0, 1, 2]
    # Exactly one attempt: no singleton retries were spawned after auth failure.
    assert len(client.calls) == 1
    assert result.pieces == []


async def test_transient_error_retries_with_bounded_backoff_and_delay_recorded():
    sleeps = []

    async def recording_sleep(seconds):
        sleeps.append(seconds)

    client = ScriptedClient([FakeError(status_code=503), [[1.0]]])
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(),
        config=_no_delay_config(max_attempts=5, base_delay=0.01, max_delay=0.05),
        sleep_fn=recording_sleep,
    )

    assert result.ok
    assert len(sleeps) == 1
    assert sleeps[0] <= 0.05 + 0.01  # capped at max_delay plus jitter bound


async def test_transient_error_honors_retry_after_hint():
    sleeps = []

    async def recording_sleep(seconds):
        sleeps.append(seconds)

    client = ScriptedClient([FakeError(status_code=429, retry_after=0.03), [[1.0]]])
    await embed_documents_with_recovery(
        client, ["a"], _budget(),
        config=_no_delay_config(base_delay=0.001, max_delay=1.0),
        sleep_fn=recording_sleep,
    )

    assert sleeps[0] >= 0.03


async def test_transient_error_exhausts_attempt_budget_with_terminal_reason():
    client = ScriptedClient([FakeError(status_code=503)] * 10)
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(),
        config=_no_delay_config(max_attempts=3), sleep_fn=_fake_sleep,
    )

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.MAX_ATTEMPTS_EXCEEDED
    assert len(client.calls) == 3


async def test_batch_size_exceeded_reduces_batch_and_keeps_completed_results():
    client = ScriptedClient(
        [FakeError(status_code=413, code="request_too_large"), [[1.0]], [[2.0]]],
        batch_size=2,
    )
    result = await embed_documents_with_recovery(
        client, ["a", "b"], _budget(), config=_no_delay_config(), sleep_fn=_fake_sleep,
    )

    assert result.ok
    assert sorted(p.source_index for p in result.pieces) == [0, 1]
    assert client.calls == [["a", "b"], ["a"], ["b"]]


async def test_per_input_context_exceeded_splits_and_retains_provenance():
    budget = _budget(max_tokens=200)
    long_text = "sentence one. " * 40 + "sentence two. " * 40

    call_count = {"n": 0}

    async def scripted(texts, usage_sink=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise FakeError(status_code=400, code="context_length_exceeded")
        return [[0.7]] * len(texts)

    client = ScriptedClient([])
    client.embed_documents_tracked = scripted

    result = await embed_documents_with_recovery(
        client, [long_text], budget, config=_no_delay_config(), sleep_fn=_fake_sleep,
    )

    assert result.ok
    assert len(result.pieces) > 1
    assert all(p.source_index == 0 for p in result.pieces)
    assert all(p.split_depth >= 1 for p in result.pieces)


async def test_estimated_count_input_rejected_then_successfully_split():
    """Reproduces the Phase 1 estimated/exact gap: a piece that fits the
    estimated budget is rejected by the provider, and recovery splits and
    resubmits it as documents rather than giving up."""
    budget = _budget(max_tokens=300)
    text = ("word " * 150).strip()
    assert budget.fits(text)  # passes the estimated-mode budget check

    attempts = {"n": 0}

    async def scripted(texts, usage_sink=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise FakeError(status_code=422, code="string_too_long")
        return [[0.3]] * len(texts)

    client = ScriptedClient([])
    client.embed_documents_tracked = scripted

    result = await embed_documents_with_recovery(
        client, [text], budget, config=_no_delay_config(), sleep_fn=_fake_sleep,
    )

    assert result.ok
    assert len(result.pieces) >= 1
    assert all(p.source_index == 0 for p in result.pieces)


async def test_per_input_context_exceeded_gives_up_past_split_depth():
    async def always_context_exceeded(texts, usage_sink=None):
        raise FakeError(status_code=400, code="context_length_exceeded")

    client = ScriptedClient([])
    client.embed_documents_tracked = always_context_exceeded

    result = await embed_documents_with_recovery(
        client, ["short but never accepted"], _budget(max_tokens=200),
        config=_no_delay_config(max_attempts=20, max_split_depth=2), sleep_fn=_fake_sleep,
    )

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.PER_INPUT_CONTEXT_EXCEEDED


async def test_unknown_error_fails_explicitly_without_speculative_retries():
    client = ScriptedClient([FakeError(status_code=418)])
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(), config=_no_delay_config(), sleep_fn=_fake_sleep,
    )

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.UNKNOWN
    assert len(client.calls) == 1


async def test_malformed_response_fails_explicitly_without_retry():
    client = ScriptedClient([[[0.1], [0.2]]])  # 2 vectors for 1 input
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(), config=_no_delay_config(), sleep_fn=_fake_sleep,
    )

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.MALFORMED
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# No retry storm when provider retries are active
# ---------------------------------------------------------------------------

async def test_provider_side_retries_do_not_compound_with_manager_retries():
    """A client that already retries internally (never raises) must not be
    re-driven through additional manager-level attempts beyond one call."""
    client = ScriptedClient([[[0.4]]])
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(), config=_no_delay_config(max_attempts=5), sleep_fn=_fake_sleep,
    )

    assert result.ok
    assert len(client.calls) == 1
    assert result.attempts == 1


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

async def test_cancellation_is_propagated_promptly():
    cancel_event = asyncio.Event()
    cancel_event.set()
    client = ScriptedClient([[[0.1]]])

    with pytest.raises(asyncio.CancelledError):
        await embed_documents_with_recovery(
            client, ["a"], _budget(), config=_no_delay_config(), cancel_event=cancel_event,
        )
    assert client.calls == []


async def test_deadline_exceeded_terminates_pending_work():
    times = iter([0.0, 100.0, 100.0, 100.0])

    def clock():
        return next(times, 100.0)

    client = ScriptedClient([FakeError(status_code=503)])
    result = await embed_documents_with_recovery(
        client, ["a"], _budget(),
        config=_no_delay_config(deadline_seconds=1.0), now_fn=clock, sleep_fn=_fake_sleep,
    )

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.DEADLINE_EXCEEDED


# ---------------------------------------------------------------------------
# Global attempt budget, order preservation, deadline on in-flight calls,
# and no fan-out past an authentication failure
# ---------------------------------------------------------------------------

async def test_attempt_budget_is_shared_across_batches_not_per_batch():
    """20 independent one-item batches that always fail transiently must not
    each get their own retry budget -- max_attempts bounds the whole
    operation's total provider calls, not each batch's."""
    class AlwaysTransientClient:
        def __init__(self):
            self.call_count = 0

        async def embed_documents_tracked(self, texts, usage_sink=None):
            self.call_count += 1
            raise FakeError(status_code=503)

    client = AlwaysTransientClient()
    texts = [f"text-{i}" for i in range(20)]
    result = await embed_documents_with_recovery(
        client, texts, _budget(),
        config=_no_delay_config(max_attempts=5, batch_item_limit=1), sleep_fn=_fake_sleep,
    )

    assert client.call_count <= 5
    assert result.attempts <= 5
    assert len(result.failed_indices) == 20


async def test_split_retry_children_preserve_original_input_order():
    """A batch that gets split after a batch-size error must not shift its
    pieces after batches that succeeded on the first try."""
    async def scripted(texts, usage_sink=None):
        if texts == ["a", "b"]:
            raise FakeError(status_code=413, code="request_too_large")
        return [[float(ord(t))] for t in texts]

    client = ScriptedClient([], batch_size=2)
    client.embed_documents_tracked = scripted

    result = await embed_documents_with_recovery(
        client, ["a", "b", "c", "d"], _budget(),
        config=_no_delay_config(batch_item_limit=2), sleep_fn=_fake_sleep,
    )

    assert result.ok
    assert [p.source_index for p in result.pieces] == [0, 1, 2, 3]
    assert [p.text for p in result.pieces] == ["a", "b", "c", "d"]


async def test_deadline_bounds_a_hanging_provider_call():
    """A client that never returns must still be bounded by deadline_seconds
    -- the deadline has to cancel in-flight calls, not just gate new waves."""
    class HangingClient:
        async def embed_documents_tracked(self, texts, usage_sink=None):
            await asyncio.sleep(30)
            return [[0.1]] * len(texts)

    client = HangingClient()
    result = await asyncio.wait_for(
        embed_documents_with_recovery(
            client, ["a"], _budget(), config=_no_delay_config(deadline_seconds=0.05),
        ),
        timeout=5.0,
    )

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.DEADLINE_EXCEEDED


async def test_deadline_bounds_a_call_that_suppresses_cancellation():
    """A provider coroutine that catches and swallows CancelledError must not
    be able to block recovery past its deadline -- cancellation is only a
    request, so the wrapper must detach rather than wait on it. The client
    here never actually finishes, so this only passes if recovery returns
    without waiting on the task at all."""
    class UncancellableClient:
        async def embed_documents_tracked(self, texts, usage_sink=None):
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                pass  # swallows the first cancellation instead of terminating
            # Still not done right after cancellation -- long enough that a
            # synchronous cleanup wait (even a short, bounded one) would show
            # up in elapsed time; short enough that a second cancel() during
            # test-runner teardown reaps it quickly.
            await asyncio.sleep(2)
            return [[0.1]] * len(texts)

    client = UncancellableClient()
    start = time.monotonic()
    result = await asyncio.wait_for(
        embed_documents_with_recovery(
            client, ["a"], _budget(), config=_no_delay_config(deadline_seconds=0.05),
        ),
        timeout=5.0,
    )
    elapsed = time.monotonic() - start

    assert result.failed_indices == [0]
    assert result.failure_reasons[0] == FailureCategory.DEADLINE_EXCEEDED
    # The deadline is operation-wide: recovery must not wait for cancellation
    # to actually take effect before returning.
    assert elapsed < 0.5


async def test_auth_failure_skips_still_queued_calls():
    """With batch_size=1 and several inputs, an auth failure must not let
    already-queued individual calls still reach the provider."""
    class AuthThenCountingClient:
        def __init__(self):
            self.call_count = 0

        async def embed_documents_tracked(self, texts, usage_sink=None):
            self.call_count += 1
            raise FakeError(status_code=401)

    client = AuthThenCountingClient()
    texts = [f"text-{i}" for i in range(10)]
    result = await embed_documents_with_recovery(
        client, texts, _budget(),
        config=_no_delay_config(batch_item_limit=1, max_concurrency=1, max_attempts=20), sleep_fn=_fake_sleep,
    )

    assert client.call_count == 1
    assert result.terminal_error is not None
    assert result.terminal_error.category == FailureCategory.AUTH
    assert len(result.failed_indices) == 10


# ---------------------------------------------------------------------------
# ChunkManager integration: document fallback semantics end-to-end
# ---------------------------------------------------------------------------

async def test_chunk_manager_store_chunks_never_calls_embed_query():
    from unittest.mock import AsyncMock

    from utils.chunk_manager import ChunkManager

    vector_store = AsyncMock()
    vector_store.add_vectors = AsyncMock(return_value=True)
    client = QueryCallingClient()

    manager = ChunkManager(vector_store, client)
    chunks = [
        {"content": "chunk one", "chunk_id": 0, "total_chunks": 2},
        {"content": "chunk two", "chunk_id": 1, "total_chunks": 2},
    ]

    ok = await manager.store_chunks(chunks, "https://example.com", metadata={})

    assert ok is True
    assert client.embed_documents_tracked_calls == [["chunk one", "chunk two"]]


async def test_cohere_singleton_fallback_uses_document_input_type():
    """Mocks Cohere's client directly to verify the singleton fallback call
    still uses input_type="search_document" (never "search_query")."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from ai_services.implementations.embedding.cohere_embedding_service import (
        CohereEmbeddingService,
    )

    service = object.__new__(CohereEmbeddingService)
    service.initialized = True
    service.provider_name = "cohere"
    service.model = "embed-english-v3.0"
    service.dimensions = 1024
    service.batch_size = 96
    service.input_type = "search_document"
    service.truncate = "NONE"
    embed_response = SimpleNamespace(embeddings=[[0.1, 0.2]], meta=None)
    service.client = SimpleNamespace(embed=AsyncMock(return_value=embed_response))

    result = await embed_documents_with_recovery(service, ["solo document"], _budget())

    assert result.ok
    call_kwargs = service.client.embed.call_args.kwargs
    assert call_kwargs["input_type"] == "search_document"


async def test_chunk_manager_reports_usage_before_partial_failure():
    """Usage from a successful batch is not lost when a later batch fails,
    and unreported provider usage is never counted as reported."""
    from unittest.mock import AsyncMock

    from utils.chunk_manager import ChunkManager
    from utils.embedding_recovery import RecoveryConfig

    client = ScriptedClient(
        [[[0.1]], FakeError(status_code=418)], batch_size=1,
    )
    vector_store = AsyncMock()
    vector_store.add_vectors = AsyncMock(return_value=True)

    manager = ChunkManager(
        vector_store, client, recovery_config=RecoveryConfig(max_attempts=1, deadline_seconds=5),
    )
    chunks = [
        {"content": "one", "chunk_id": 0, "total_chunks": 2},
        {"content": "two", "chunk_id": 1, "total_chunks": 2},
    ]
    usage = {}

    ok = await manager.store_chunks(chunks, "https://example.com", metadata={}, usage_sink=usage)

    # One chunk embedded and stored; usage reflects only the reported call.
    assert ok is True
    assert usage.get("reported") is True
    assert usage["prompt_tokens"] == 1
