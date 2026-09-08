"""
Bounded, document-safe recovery for embedding submission.

Phase 3 of docs/roadmap/chunking/chunking-safeguards.md. Wraps an embedding
client's document-embedding calls with:

- packing against per-input, batch-item, and aggregate-token limits
- structured error classification (status/code data, never a bare "token"
  message match)
- one attempt/deadline budget shared across manager- and provider-level
  retries
- bounded concurrency, split depth, and generated-piece count, with
  cancellation propagated to the caller
- cardinality/dimension/finite-value validation of returned vectors, with
  input-to-vector provenance preserved across splits and retries

This module only ever calls `embed_documents`/`embed_documents_tracked` --
including for a single oversized input -- so every document retains document
embedding semantics. Query embedding (`embed_query`) is untouched and stays
exclusively for retrieval queries.
"""

import asyncio
import itertools
import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai_services.providers.usage_reporting import accumulate_usage_sink

from utils.embedding_budget import EmbeddingBudget, resolve_embedding_budget, split_text_to_budget

logger = logging.getLogger(__name__)


class FailureCategory:
    """Recovery policy categories from the Phase 3 failure/recovery table."""

    AUTH = "auth"
    TRANSIENT = "transient"
    BATCH_SIZE_EXCEEDED = "batch_size_exceeded"
    PER_INPUT_CONTEXT_EXCEEDED = "per_input_context_exceeded"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CANCELLED = "cancelled"


_AUTH_STATUS = {401, 403}
_BATCH_SIZE_STATUS = {413}
_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
_AMBIGUOUS_STATUS = {400, 422}  # cannot classify further without a structured code

_AUTH_NAMES = {"AuthenticationError", "PermissionDeniedError", "UnauthorizedResponseError", "ForbiddenResponseError"}
_TRANSIENT_NAMES = {
    "RateLimitError", "TooManyRequestsResponseError",
    "APITimeoutError", "Timeout", "TimeoutError", "RequestTimeoutResponseError",
    "APIConnectionError", "ConnectionError", "ServiceUnavailableError", "ServiceUnavailableResponseError",
    "InternalServerError", "InternalServerResponseError",
}

# Structured provider error codes (never raw message substrings) that
# indicate a specific size category. Provider-specific adapters may extend
# this via `extra_context_codes`/`extra_batch_codes` on RecoveryConfig if a
# provider exposes its own structured code that isn't OpenAI-shaped.
_CONTEXT_CODES = {"context_length_exceeded", "string_too_long", "invalid_input_length"}
_BATCH_CODES = {"batch_size_exceeded", "request_too_large", "too_many_inputs", "max_batch_size_exceeded"}


@dataclass
class ClassifiedError:
    category: str
    retry_after: float | None = None
    status_code: int | None = None
    reason: str = ""


def _status_code(error: BaseException) -> int | None:
    for attr in ("status_code", "status", "http_status"):
        value = getattr(error, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    return None


def _retry_after_hint(error: BaseException) -> float | None:
    value = getattr(error, "retry_after", None)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers is not None:
        for key in ("Retry-After", "retry-after"):
            try:
                raw = headers.get(key)
            except Exception:  # noqa: BLE001 - defensive header-shape fallback
                raw = None
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
    return None


def _structured_code(error: BaseException) -> str | None:
    code = getattr(error, "code", None)
    if code is None:
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            inner = body.get("error")
            code = inner.get("code") if isinstance(inner, dict) else body.get("code")
    return str(code).lower() if code else None


def classify_embedding_error(error: BaseException) -> ClassifiedError:
    """Classify a provider exception using structured status/code data.

    Deliberately avoids message-string matching -- a bare "token" substring
    is not a valid classifier. Any provider-specific message matching a
    caller needs stays isolated in that provider's own adapter and is not
    performed here.
    """
    # ProviderServiceError (server/ai_services/errors.py) wraps the raw SDK
    # exception in `original_error`; classify against the original so status
    # codes/structured codes from the SDK are still visible.
    original = getattr(error, "original_error", None) or error
    name = type(original).__name__
    status = _status_code(original)
    retry_after = _retry_after_hint(original)
    code = _structured_code(original)

    if status in _AUTH_STATUS or name in _AUTH_NAMES:
        return ClassifiedError(FailureCategory.AUTH, status_code=status, reason=name)

    if code and code in _CONTEXT_CODES:
        return ClassifiedError(FailureCategory.PER_INPUT_CONTEXT_EXCEEDED, status_code=status, reason=code)

    if code and code in _BATCH_CODES:
        return ClassifiedError(FailureCategory.BATCH_SIZE_EXCEEDED, status_code=status, reason=code)

    if status in _BATCH_SIZE_STATUS:
        return ClassifiedError(FailureCategory.BATCH_SIZE_EXCEEDED, status_code=status, reason=name)

    if status in _TRANSIENT_STATUS or name in _TRANSIENT_NAMES:
        return ClassifiedError(FailureCategory.TRANSIENT, retry_after=retry_after, status_code=status, reason=name)

    if status in _AMBIGUOUS_STATUS:
        # A 400/422 without a recognized structured code cannot be safely
        # attributed to a specific size category -- treat as unknown rather
        # than guessing from the message.
        return ClassifiedError(FailureCategory.UNKNOWN, status_code=status, reason=name)

    return ClassifiedError(FailureCategory.UNKNOWN, status_code=status, reason=name)


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid_embedding_response(vectors: Any, expected_count: int) -> bool:
    """Validate cardinality, per-vector dimensional consistency, and finite values."""
    if vectors is None or not isinstance(vectors, (list, tuple)) or len(vectors) != expected_count:
        return False
    dimension: int | None = None
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) == 0:
            return False
        if dimension is None:
            dimension = len(vector)
        elif len(vector) != dimension:
            return False
        if not all(_is_finite_number(v) for v in vector):
            return False
    return True


@dataclass
class RecoveryConfig:
    """Bounds shared across every attempt made while embedding one call's inputs."""

    max_attempts: int = 5
    deadline_seconds: float = 30.0
    base_delay: float = 0.25
    max_delay: float = 8.0
    max_concurrency: int = 4
    max_split_depth: int = 3
    max_pieces_per_input: int = 8
    batch_item_limit: int | None = None
    aggregate_token_limit: int | None = None


@dataclass
class EmbeddedPiece:
    text: str
    vector: list
    source_index: int
    split_depth: int = 0


@dataclass
class RecoveryResult:
    pieces: list = field(default_factory=list)
    failed_indices: list = field(default_factory=list)
    failure_reasons: dict = field(default_factory=dict)
    terminal_error: ClassifiedError | None = None
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return not self.failed_indices and self.terminal_error is None


@dataclass
class _Job:
    items: list  # list[(source_index, text)]
    order: int
    split_depth: int = 0
    attempts: int = 0


class _Deadline:
    def __init__(self, seconds: float | None, now_fn: Callable[[], float]):
        self._now_fn = now_fn
        self._end = (now_fn() + seconds) if seconds is not None else None

    def remaining(self) -> float | None:
        if self._end is None:
            return None
        return max(0.0, self._end - self._now_fn())

    def expired(self) -> bool:
        remaining = self.remaining()
        return remaining is not None and remaining <= 0


def _pack_jobs(
    indexed_texts: list,
    budget: EmbeddingBudget,
    batch_item_limit: int,
    aggregate_token_limit: int | None,
    order_counter: itertools.count,
) -> list:
    jobs: list[_Job] = []
    current: list = []
    current_tokens = 0

    for idx, text in indexed_texts:
        token_count = budget.count(text).count
        exceeds_items = len(current) >= batch_item_limit
        exceeds_aggregate = (
            aggregate_token_limit is not None
            and current
            and (current_tokens + token_count) > aggregate_token_limit
        )
        if current and (exceeds_items or exceeds_aggregate):
            jobs.append(_Job(items=current, order=next(order_counter)))
            current = []
            current_tokens = 0
        current.append((idx, text))
        current_tokens += token_count

    if current:
        jobs.append(_Job(items=current, order=next(order_counter)))
    return jobs


def _shrunk_budget(budget: EmbeddingBudget, split_depth: int) -> EmbeddingBudget:
    """A tighter budget for re-splitting a single input that a provider
    rejected despite fitting the original (possibly estimated) budget --
    each additional split attempt asks for a smaller piece."""
    shrink_factor = 0.5 ** split_depth
    tighter_max = max(1, int(budget.effective_max_tokens * shrink_factor))
    return resolve_embedding_budget(
        max_embedding_tokens=tighter_max,
        model=budget.model,
        chunk_target_tokens=tighter_max,
        safety_margin=1.0,
    )


async def _attempt_job(embedding_client: Any, job: _Job) -> tuple:
    """Make exactly one provider call for `job`. Returns (vectors, usage, classified_error)."""
    texts = [text for _, text in job.items]
    try:
        if hasattr(embedding_client, "embed_documents_tracked"):
            local_usage: dict = {}
            vectors = await embedding_client.embed_documents_tracked(texts, usage_sink=local_usage)
        else:
            vectors = await embedding_client.embed_documents(texts)
            local_usage = None
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise
    except Exception as exc:  # noqa: BLE001 - classified below, never swallowed silently
        return None, None, classify_embedding_error(exc)

    if not _valid_embedding_response(vectors, len(texts)):
        return None, None, ClassifiedError(FailureCategory.MALFORMED, reason="malformed_or_wrong_cardinality")

    return vectors, local_usage, None


async def embed_documents_with_recovery(
    embedding_client: Any,
    texts: list,
    budget: EmbeddingBudget,
    *,
    usage_sink: dict | None = None,
    config: RecoveryConfig | None = None,
    now_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], Any] = asyncio.sleep,
    cancel_event: asyncio.Event | None = None,
) -> RecoveryResult:
    """Embed `texts` as documents with bounded, policy-driven recovery.

    Every call -- including a singleton fallback for one oversized input --
    uses `embed_documents`/`embed_documents_tracked`; this function never
    calls `embed_query`. Order of `result.pieces` matches input order, with
    any pieces produced by splitting one oversized input kept contiguous and
    tagged with that input's `source_index`.
    """
    config = config or RecoveryConfig()
    result = RecoveryResult()
    if not texts:
        return result

    deadline = _Deadline(config.deadline_seconds, now_fn)
    batch_item_limit = config.batch_item_limit or getattr(embedding_client, "batch_size", None) or len(texts)
    batch_item_limit = max(1, batch_item_limit)
    aggregate_token_limit = config.aggregate_token_limit or getattr(embedding_client, "aggregate_token_limit", None)

    order_counter = itertools.count()
    jobs = _pack_jobs(list(enumerate(texts)), budget, batch_item_limit, aggregate_token_limit, order_counter)
    semaphore = asyncio.Semaphore(max(1, config.max_concurrency))

    def _fail(job: _Job, reason: str) -> None:
        for idx, _ in job.items:
            result.failed_indices.append(idx)
            result.failure_reasons[idx] = reason

    ordered_pieces: list = []
    stop_all = False
    stop_holder = [False]

    while jobs and not stop_all:
        if cancel_event is not None and cancel_event.is_set():
            for job in jobs:
                _fail(job, FailureCategory.CANCELLED)
            raise asyncio.CancelledError("Embedding recovery cancelled")

        if deadline.expired():
            for job in jobs:
                _fail(job, FailureCategory.DEADLINE_EXCEEDED)
            break

        # The attempt budget is shared across the whole operation, not per
        # job -- only dispatch as many calls this wave as remain in it, and
        # fail the rest outright rather than letting every job spend its own
        # full retry allowance.
        remaining_budget = config.max_attempts - result.attempts
        if remaining_budget <= 0:
            for job in jobs:
                _fail(job, FailureCategory.MAX_ATTEMPTS_EXCEEDED)
            break
        wave, deferred = jobs[:remaining_budget], jobs[remaining_budget:]

        async def _run(job: _Job):
            async with semaphore:
                if stop_holder[0]:
                    # An authentication failure was already observed in this
                    # wave -- do not fan out into further individual calls.
                    return job, None, None, ClassifiedError(
                        FailureCategory.AUTH, reason="stopped_after_auth_failure",
                    )
                vectors, usage, classified = await _attempt_job(embedding_client, job)
                if classified is not None and classified.category == FailureCategory.AUTH:
                    stop_holder[0] = True
                return job, vectors, usage, classified

        remaining = deadline.remaining()
        task_map = {asyncio.create_task(_run(job)): job for job in wave}
        if remaining is None:
            done, pending = await asyncio.wait(task_map)
        else:
            done, pending = await asyncio.wait(task_map, timeout=remaining)

        for task in pending:
            task.cancel()
            _fail(task_map[task], FailureCategory.DEADLINE_EXCEEDED)
            # Cancellation is a request, not a guarantee -- a provider
            # coroutine that catches and suppresses CancelledError could
            # otherwise block this call waiting on it, pushing the actual
            # runtime past deadline_seconds. Detach immediately (the
            # deadline already elapsed, so there is no remaining time to
            # wait) and drain whatever result/exception eventually arrives
            # via a done-callback so it never becomes a "Task exception was
            # never retrieved" warning.
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

        outcomes = [task.result() for task in done]
        jobs = deferred

        for job, vectors, usage, classified in outcomes:
            result.attempts += 1
            job.attempts += 1

            if classified is None:
                for (idx, text), vector in zip(job.items, vectors):
                    ordered_pieces.append((idx, job.order, EmbeddedPiece(
                        text=text, vector=vector, source_index=idx, split_depth=job.split_depth,
                    )))
                if usage:
                    accumulate_usage_sink(usage_sink, usage)
                continue

            if classified.category == FailureCategory.AUTH:
                result.terminal_error = classified
                _fail(job, FailureCategory.AUTH)
                stop_all = True
                continue

            if result.attempts >= config.max_attempts:
                _fail(job, FailureCategory.MAX_ATTEMPTS_EXCEEDED)
                continue

            if classified.category == FailureCategory.TRANSIENT:
                delay = min(config.max_delay, config.base_delay * (2 ** (job.attempts - 1)))
                if classified.retry_after is not None:
                    delay = max(delay, classified.retry_after)
                delay += random.uniform(0, config.base_delay)
                remaining = deadline.remaining()
                if remaining is not None:
                    if remaining <= 0:
                        _fail(job, FailureCategory.DEADLINE_EXCEEDED)
                        continue
                    delay = min(delay, remaining)
                await sleep_fn(delay)
                jobs.append(job)
                continue

            if classified.category == FailureCategory.BATCH_SIZE_EXCEEDED:
                if len(job.items) > 1:
                    mid = len(job.items) // 2
                    jobs.append(_Job(items=job.items[:mid], order=next(order_counter), split_depth=job.split_depth))
                    jobs.append(_Job(items=job.items[mid:], order=next(order_counter), split_depth=job.split_depth))
                    continue
                # A single-item "batch" reported as too large: fall through to
                # the same per-input splitting path as a context-exceeded item.
                classified = ClassifiedError(
                    FailureCategory.PER_INPUT_CONTEXT_EXCEEDED, status_code=classified.status_code, reason=classified.reason,
                )

            if classified.category == FailureCategory.PER_INPUT_CONTEXT_EXCEEDED:
                if len(job.items) > 1:
                    for idx, text in job.items:
                        jobs.append(_Job(items=[(idx, text)], order=next(order_counter), split_depth=job.split_depth))
                    continue

                idx, text = job.items[0]
                if job.split_depth >= config.max_split_depth:
                    _fail(job, FailureCategory.PER_INPUT_CONTEXT_EXCEEDED)
                    continue

                try:
                    tighter = _shrunk_budget(budget, job.split_depth + 1)
                    pieces = split_text_to_budget(text, tighter)
                except ValueError:
                    _fail(job, FailureCategory.PER_INPUT_CONTEXT_EXCEEDED)
                    continue

                if len(pieces) <= 1 or len(pieces) > config.max_pieces_per_input:
                    _fail(job, FailureCategory.PER_INPUT_CONTEXT_EXCEEDED)
                    continue

                for piece_text in pieces:
                    jobs.append(_Job(
                        items=[(idx, piece_text)], order=next(order_counter), split_depth=job.split_depth + 1,
                    ))
                continue

            # MALFORMED / UNKNOWN: explicit failure now, no unbounded speculative retries.
            _fail(job, classified.category)

    if stop_all:
        # Any jobs never dispatched -- deferred by the attempt budget, or
        # queued behind the wave that hit an auth failure -- are covered by
        # the same terminal stop, not silently dropped.
        for job in jobs:
            _fail(job, FailureCategory.AUTH)

    ordered_pieces.sort(key=lambda item: (item[0], item[1]))
    result.pieces = [piece for _, _, piece in ordered_pieces]
    return result
