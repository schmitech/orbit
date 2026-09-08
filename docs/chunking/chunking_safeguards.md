# Chunking Safeguards and Error Handling

This document explains the safeguards that protect the Firecrawl web-content chunking, embedding, storage, and retrieval pipeline. It reflects the implementation delivered by [`docs/roadmap/complete/chunking-safeguards.md`](../roadmap/complete/chunking-safeguards.md) (Phases 1-6); see that roadmap for the full design rationale, test coverage, and known limitations of each phase.

## The problem

Scraped web content varies wildly in size and structure. Left unchecked, this causes several distinct failure modes: chunks that exceed an embedding provider's input limit, inconsistent token-counting between chunk preparation and the actual embedding call, embedding fallback paths that silently used query-embedding semantics for documents, retries that either gave up too early or fanned out into runaway retry storms, and successful-looking ingestion that was actually missing pieces.

## Architecture

```
ContentChunker            ChunkManager                 IntentFirecrawlRetriever
(content_chunker.py)      (chunk_manager.py +          (intent_firecrawl_retriever.py)
                           embedding_recovery.py)
     |                          |                              |
     | chunk_markdown()         | store_chunks()                | retrieve_chunks() -> format
     v                          v                              v
 EmbeddingBudget-bounded    embed_documents_with_recovery   Bounded, budget-checked
 chunks, source spans       + IngestionResult (complete/    formatting; discloses
 preserved                  partial/failed)                 partial/failed coverage
```

### One shared token budget (`server/utils/embedding_budget.py`)

`EmbeddingBudget`, produced by `resolve_embedding_budget()`, is the single source of truth for what fits in one embedding call. Both `ContentChunker` (preparation) and `ChunkManager` (submission) are given the *same* `EmbeddingBudget` instance so neither applies a different cutoff. It:

- Clamps a configured `max_embedding_tokens` to the known provider/model input limit, when that limit is in `KNOWN_MODEL_INPUT_LIMITS`.
- Prefers an exact tokenizer (`tiktoken`) when available for the resolved model; otherwise counts are explicitly labeled `estimated` (`TokenCount.estimated`), never silently treated as exact.
- Exposes `split_text_to_budget()`, a paragraph -> sentence -> character-boundary splitter that always makes progress and guarantees every emitted piece fits the budget.

Configuration (adapter YAML, `adapter_config` for the Firecrawl adapter):

```yaml
max_chunk_tokens: 4000        # Target chunk size (ContentChunker)
chunk_overlap_tokens: 200     # Overlap for continuity
min_chunk_tokens: 500         # Soft minimum -- never used to drop short content
max_embedding_tokens: 7500    # Hard budget for one embedding submission
```

### Content preservation (`ContentChunker.chunk_markdown`)

Chunks carry `source_span` (and `overlap_span`) offsets into the original content. Concatenating chunks' source spans in order reconstructs the original document exactly -- this is asserted directly in `test_content_preservation.py` and again end-to-end in `test_pipeline.py`. Overlap is computed from original spans (not from already-overlapped chunk text) so it cannot accumulate across chunks.

### Bounded embedding recovery (`server/utils/embedding_recovery.py`)

`embed_documents_with_recovery()` wraps every document-embedding call (including a singleton fallback for one oversized input -- it never calls `embed_query()` for a document). Provider errors are classified from structured status/code data, never a bare `"token"` substring match:

| Failure | Recovery policy |
|---|---|
| Authentication/authorization or invalid model configuration | Stop; do not fan out into individual calls |
| Rate limit, timeout, transient service failure | Bounded backoff with jitter; honor retry hints within the deadline |
| Batch item/aggregate size exceeded | Reduce the batch while retaining completed results |
| Per-input context exceeded | Split the offending input further and retry as documents; retain provenance |
| Unknown error or malformed embedding response | Explicit failure; no unbounded speculative retries |

One `RecoveryConfig` (`max_attempts`, `deadline_seconds`, `max_concurrency`, `max_split_depth`, `max_pieces_per_input`) bounds the *entire* call, not each batch independently -- the attempt budget is shared, so a batch of many small inputs cannot multiply out into an unbounded number of provider calls. Cancellation and the deadline are honored even against a provider call that doesn't cooperate with cancellation (the wrapper detaches rather than blocking on it).

### Explicit ingestion completeness (`ChunkManager.store_chunks`)

`store_chunks()` returns a structured `IngestionResult` -- `IngestionStatus.COMPLETE` / `PARTIAL` / `FAILED`, expected/stored/failed piece counts, and per-piece failure reasons -- instead of a boolean. Callers must check `.status` explicitly; there is no meaningful truthiness shortcut.

Ingestion identity is `(source URL, prepared-content hash, embedding model, embedding budget)`, hashed into a `generation_id`. Piece ids are deterministic from that identity, so:

- A retry after a `PARTIAL` result re-embeds and re-stores only the pieces still missing, not the whole document.
- Retrieval filters by the latest known `generation_id` for a URL, so changed content, a changed embedding model, or a changed budget can never mix stale pieces from an earlier generation into a query's results.

This state (`_ingestion_state`, `_pending_pieces`, `_generation_by_url`) lives only in the `ChunkManager` process instance -- see **Limitations** below.

### Bounded, visible retrieval degradation (`IntentFirecrawlRetriever`)

The retriever consumes `IngestionResult` explicitly:

- `FAILED` -> skips chunk retrieval and returns a bounded raw-content excerpt.
- `PARTIAL` -> still retrieves ranked chunks, but discloses incomplete coverage in the formatted text and in response metadata (`ingestion_status`).
- `COMPLETE` -> normal ranked-chunk formatting.

Every formatting path -- ranked-chunk output, the raw-content fallback, and their empty/failed/no-match edge cases -- is bounded to a configured `max_retrieval_context_tokens` (default 6000). None of them send the whole page or an unbounded error message; a budget too small to show anything useful returns an explicit, itself-bounded "unavailable" message instead. Query embedding (`retrieve_chunks` -> `embed_query`) is unaffected by any of this.

```yaml
max_retrieval_context_tokens: 6000   # Bound on formatted retrieval output (both paths)
top_chunks_to_return: 3
min_chunk_similarity: 0.3
```

## Retry ownership

Retries are owned at exactly one layer for each concern, so they don't compound:

- **Provider-level retries** (transient errors, size-exceeded splits): owned by `embed_documents_with_recovery`, bounded by one shared `RecoveryConfig` per `store_chunks()` call.
- **Cross-request retries** (an earlier `PARTIAL` ingestion): owned by `ChunkManager`'s pending-piece state, replayed the next time `store_chunks()` is called for the same URL -- there is no background retry scheduler.
- **Nothing retries silently forever.** Every path terminates within its configured attempt/deadline budget and reports a terminal `FailureCategory` or `IngestionStatus`.

## Partial-cache semantics

`has_cached_chunks()` is true only for a generation that reached `IngestionStatus.COMPLETE`. A `PARTIAL` generation is never treated as a complete cache hit -- the next request for that URL re-enters `store_chunks()` and resumes from the pending pieces. `invalidate_cache()` and `cleanup_expired_chunks()` clear ingestion state for *every* generation seen for a URL, not just the latest, so an old partial generation can't resurface after its content is deleted.

## Limitations

- **No durable retry state.** Ingestion and generation state is in-memory, scoped to one `ChunkManager` instance. A process restart treats every URL as uncached and rebuilds idempotently (safe, but not fast) rather than resuming a partial ingestion. Multiple worker processes do not share this state.
- **Estimated token counting by default.** Exact counting requires a recognized model with a `tiktoken` encoding; otherwise counts are conservative character-ratio estimates, explicitly labeled as such.
- **The retrieval-context budget is a configured cap, not the caller's actual remaining prompt budget** -- the pipeline does not currently thread the live remaining-context allowance through to this retriever. The final prompt assembler remains responsible for the complete prompt budget.
- **Vector-store partial-write detection depends on the store signaling failure.** A store that silently drops part of a bulk write without returning `False` or raising would not be caught.
- **Provider-specific structured error codes** (`_CONTEXT_CODES`/`_BATCH_CODES` in `embedding_recovery.py`) are seeded from OpenAI's error shape; a provider exposing different codes for context/batch-size errors classifies as `unknown` until its codes are added.

No formal p50/p95 latency benchmarking or production metrics/counters were added as part of this work; overhead has not been measured against a recorded baseline, and no claim is made about it here.

## Troubleshooting

**"Chunk too large" / repeated splitting in logs.** Reduce `max_chunk_tokens`, or verify `max_embedding_tokens` matches your provider's actual input limit (check `KNOWN_MODEL_INPUT_LIMITS` in `embedding_budget.py` for what's recognized).

**Ingestion stays `PARTIAL` across repeated requests.** Check logs for the specific `FailureCategory` (`embedding_recovery.py`) or `vector_store_write_failed` reasons in the `IngestionResult`. An `AUTH` failure will not resolve on retry without a configuration fix.

**Chunks stored but retrieval returns nothing.** Confirm the query and the stored content share a `generation_id` (a content/model/budget change creates a new generation); force a rebuild with `await chunk_manager.invalidate_cache(source_url)` if needed.

**Formatted output looks truncated.** That's the Phase 5 bound working as intended -- raise `max_retrieval_context_tokens` if more content should be shown, and check the response metadata / formatted footer for the explicit truncation disclosure.
