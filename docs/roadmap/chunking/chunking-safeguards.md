# Chunking Safeguards — Phased Implementation Plan

Status: in progress; Phases 1, 1b, 2, 3, 4, and 5 completed (see the completion checklist below).

## Objective and scope

Make the Firecrawl web-content pipeline preserve source content, enforce consistent embedding budgets, recover within bounded limits, and report incomplete ingestion accurately. This addresses the review of [Chunking Safeguards and Error Handling](../chunking/chunking_safeguards.md).

Primary implementation locations:

- `server/utils/content_chunker.py`
- `server/utils/chunk_manager.py`
- `server/retrievers/implementations/intent/intent_firecrawl_retriever.py`
- `server/ai_services/implementations/embedding/` and the associated provider interfaces
- `config/adapters/intent.yaml`

This plan covers web-content chunking and its embedding/storage/retrieval boundary. Phases 1–6 are scoped to Firecrawl web-content chunking only; uploaded-file chunking is out of scope for those phases specifically. Phase 1b (below, optional/follow-up) extends the Phase 1 budget abstraction to uploaded-file chunking's embedding boundary and is the one exception to that exclusion. Replacing uploaded-file chunkers' chunking strategy, adding new chunking strategies in general, and introducing a durable background ingestion service remain outside scope throughout. Shared embedding changes must retain compatibility with existing callers.

Tests establish the contracts below under specified conditions; they cannot guarantee provider availability or answer quality. Live provider checks supplement deterministic tests and do not replace them.

## Confirmed starting gaps

| Finding | Current behavior | Target behavior |
|---|---|---|
| Inconsistent limits | Preparation accepts 100% of the configured budget; fallback accepts 95% | One effective budget for every document submission |
| Approximate counting | `len(text) // 3` is treated as a safe token count | Model-aware counting where supported; explicit estimated mode otherwise |
| Incorrect fallback semantics | Individual document fallback calls `embed_query()` | Every document attempt uses document embedding semantics |
| Partial ingestion hidden | Successful subset is stored and the whole URL is cached | Explicit complete/partial/failed result and recoverable missing pieces |
| Content loss and oversize chunks | Preamble can disappear; long paragraphs and overlap can exceed the target | Source coverage and final chunk size are validated |
| Undifferentiated retries | Every batch exception triggers individual calls | Error-specific recovery with a shared attempt/deadline budget |
| Overstated guarantees | Full-content fallback, unconditional reliability claims, unexplained timing figures | Bounded context, observable degradation, and measured performance |

## Delivery and test rules

Implement phases in order. Each phase includes production changes and its tests in the same reviewable change. Run its gate plus all earlier phase gates before marking it complete. Do not carry expected failures or skipped acceptance tests into a completed phase.

Create a dedicated `server/tests/test_chunking_safeguards/` package. Use deterministic embedding clients, fake clocks/sleep, and a vector-store fake that records writes, supports retrieval, and can simulate partial writes. Do not require network access, credentials, tokenizer downloads, or real retry delays for these gates. Model-specific local tokenizer fixtures should be pinned and provisioned with test dependencies.

The test module names below are proposed deliverables, not existing tests. From the repository root, using the configured Python environment:

```bash
python -m pytest -c server/tests/pyproject.toml server/tests/test_chunking_safeguards/test_budget.py
```

Substitute the phase's module name for its focused gate. By Phase 6, run the whole package and the existing embedding usage tests:

```bash
python -m pytest -c server/tests/pyproject.toml server/tests/test_chunking_safeguards server/tests/test_embeddings/test_embedding_cost_tracking.py
git diff --check
```

## Phase 1 — Establish one embedding budget

**Changes**

- Introduce a small shared budget/counting abstraction used by chunk preparation and fallback. Keep `max_embedding_tokens` as a compatible configuration input; calculate the existing 95% margin once and expose the effective value.
- Resolve the actual provider/model's input limit and counting capability through the embedding client. Clamp configured budgets to known model limits; keep model capability data in one place with provenance rather than duplicating provider tables.
- Validate positive integer limits, usable effective budgets, nonnegative overlap, and overlap smaller than the chunk target. Define `min_chunk_tokens` as a soft target that never permits dropping short content or exceeding hard limits.
- Prefer the model's tokenizer where available. Mark estimates explicitly when exact counting is unavailable; do not claim that a character ratio guarantees acceptance. Count the final submitted input, including any provider-added document prefix under application control.
- Revalidate every final split piece with the same effective budget. Ensure hard splitting makes progress even for tiny budgets or unsplittable characters; return a clear failure when no valid nonempty piece can be produced.

**Tests: `test_budget.py`**

- Check effective-budget minus one, equal, and plus one at preparation and submission boundaries.
- Reproduce the default 7,126–7,500 estimated-token gap and assert that preparation splits pieces which fallback would otherwise reject.
- Cover empty/whitespace input, invalid configuration, tiny budgets, unknown models, and tokenizer-unavailable mode.
- Use Unicode, emoji, CJK, and code fixtures to exercise counting without assuming English character ratios.
- Assert all emitted nonempty pieces satisfy the selected counter, splitting terminates, and estimates are labeled as estimates.

**Exit gate:** All budget tests pass; no path applies a different document cutoff. Exact and estimated modes have distinct, documented guarantees. Provider rejection recovery is completed in Phase 3.

## Phase 1b — Extend the shared budget to uploaded-file chunking (follow-up)

Status: proposed; depends on the Phase 1 shared budget abstraction (`server/utils/embedding_budget.py`). Phase 1's offline-tokenizer-provisioning exit criterion (pinned `TIKTOKEN_CACHE_DIR` fixtures for a clean install) is still unresolved as of this writing; Phase 1b's exact-counting paths inherit that same open item rather than re-solving it.

**Why this is separate from Phase 1, and why it is now explicitly in scope:** Phase 1's top-level scope statement says uploaded-file chunkers are out of scope; this phase supersedes that exclusion for the uploaded-file path specifically (the top-level scope note should be read as "out of scope for Phase 1," not for the roadmap as a whole). Scope here is deliberately narrow: **uploaded-file chunking and the one point where its output reaches an embedding call.** It does not extend to template-example embedding (`intent_composite_base.py`, `intent_http_base.py`, `intent_sql_base.py` embed retrieval-template examples, not document chunks) or to retrievers that only embed queries (most of `vector`/`qa`/`relational`). If a later audit finds other genuine document-embedding call sites outside this list, they get their own phase rather than being folded in here silently.

**The hard guarantee belongs at the embedding boundary, not in the chunkers.** `FileVectorRetriever.index_file_chunks()` (`server/retrievers/implementations/file/file_retriever.py:473`) is the one place uploaded-file chunks are handed to `embed_documents`/`embed_documents_tracked`/`embed_query` fallback. Chunker-level budgeting (Changes, below) exists to make that boundary's job easy — chunkers should already produce well-sized pieces — but `index_file_chunks()` is where every outgoing document is actually validated or split; a chunker bug or misconfiguration must not be able to bypass that.

**Confirmed starting gaps**

| Finding | Current behavior | Target behavior |
|---|---|---|
| No validation at the embedding boundary | `FileVectorRetriever.index_file_chunks()` embeds `chunk.text` for every chunk unconditionally; nothing revalidates chunk size against the configured embedding model before calling `embed_documents(_tracked)` | `index_file_chunks()` resolves an `EmbeddingBudget` for its embedding client/model and validates (splitting via `split_text_to_budget` if needed) every chunk text immediately before embedding, regardless of which chunker produced it |
| Silent unit mismatch | `token_chunker.py` defaults `tokenizer="character"`; `utils.py:SimpleTokenizer` encodes 1 character = 1 "token" (`ord(c)` per char) with no ratio correction and no `estimated` label | A `"character"`/no-real-tokenizer configuration reports token counts explicitly labeled `estimated`, not silently reported as exact |
| Decode-failure fallback uses an unlabeled, divergent ratio | Both `token_chunker.py` and `fixed_chunker.py`'s token mode estimate `len(token_slice) * 4` characters per token when `tokenizer.decode()` fails, diverging from Phase 1's `len(text) // 3` convention | One counting/estimation convention (`embedding_budget.count_tokens`) shared with Firecrawl chunking for this fallback path in both chunkers |
| Overlap/chunk-size units differ per chunker | `TokenChunker` and `FixedSizeChunker`'s token mode validate only `overlap >= chunk_size` in tokenizer units (characters, by default); `FixedSizeChunker`'s character mode uses characters; `SemanticChunker` uses sentence counts | Each chunker still validates chunk-size/overlap in its own local unit (tokens, characters, or sentences — unifying these would change chunker semantics, which is out of scope), but the *text each chunker emits* is what gets checked against `EmbeddingBudget` at the embedding boundary described above |

**Changes**

- In `FileVectorRetriever.index_file_chunks()`, resolve an `EmbeddingBudget` for `self.embeddings`' model (mirroring how `IntentFirecrawlRetriever.initialize()` builds one) and, immediately before calling `embed_documents`/`embed_documents_tracked`/the per-chunk `embed_query` fallback, validate every `chunk.text` against it — splitting via `split_text_to_budget` and re-associating split pieces with the originating chunk's `chunk_id`/metadata where a chunk is oversized. This is the hard guarantee; everything else below is best-effort chunker-side hygiene.
- For `token_chunker.py`: require that any tokenizer passed to it either (a) implements the full `TokenizerProtocol` (`encode`, `decode`, `count_tokens`) against a real model-compatible vocabulary, so slicing by token index and decoding back to text stays reversible, or (b) is left as the `"character"` default, in which case `TokenChunker` should slice via `split_text_to_budget` against a resolved `EmbeddingBudget` instead of raw character-as-token slicing. A bare `count_tokens()` adapter is not sufficient on its own — `TokenChunker.chunk_text()` needs `encode()`/`decode()` to build and materialize token slices, not just count them.
- Replace both `token_chunker.py`'s and `fixed_chunker.py`'s `len(token_slice) * 4` decode-failure estimate with `embedding_budget.count_tokens`'s estimation convention, and revalidate the recovered text against the caller's `EmbeddingBudget` (via `index_file_chunks()`, not by having the chunker call the embedding client itself).
- Do not change `TextChunker`/`Chunk`'s public shape (`chunk_text`, `Chunk` fields), and do not unify `TokenChunker`/`FixedSizeChunker`/`SemanticChunker` overlap units — each keeps validating its own configuration in its own local unit. This phase adds one more validation layer (the resolved `EmbeddingBudget` at the embedding boundary), it does not replace chunker-local validation.

**Tests: `test_file_chunking_budget.py`** (new, alongside the existing `test_chunking_safeguards` package)

- Assert `index_file_chunks()` splits (or rejects with a clear error) a chunk whose text exceeds the resolved `EmbeddingBudget`, using a fake embedding client that fails the test if it ever receives a document over the effective budget.
- Assert a `"character"`-tokenizer configuration reports `estimated=True` token counts rather than treating character counts as exact tokens.
- Assert both `token_chunker.py`'s and `fixed_chunker.py`'s decode-failure fallback paths use the shared estimation convention, and that recovered text is still caught by `index_file_chunks()`'s boundary validation if oversized.
- Assert `TokenChunker` rejects a tokenizer missing `encode`/`decode` (or falls back to `split_text_to_budget` slicing) rather than silently treating characters as tokens.

**Exit gate:** New tests pass alongside Phase 1's `test_budget.py`. `FileVectorRetriever.index_file_chunks()` never calls `embed_documents(_tracked)`/`embed_query` with a document over its resolved `EmbeddingBudget`. No uploaded-file chunker reports or treats an estimate as an exact count. Phase 1b's tests are **not** included in Phase 6's `pytest ... server/tests/test_chunking_safeguards server/tests/test_embeddings/test_embedding_cost_tracking.py` gate unless Phase 1b has itself been implemented and merged by then — Phase 6 validates the Firecrawl pipeline this roadmap's Phases 1–6 cover, and must not be blocked on an optional follow-up. If Phase 1b lands before Phase 6, add its test module to that gate's command explicitly at that time.

## Phase 2 — Preserve content and bound overlap

**Changes**

- Preserve text before the first heading and heading-free documents. Keep heading hierarchy while avoiding interpreting fenced-code headings as document sections.
- Split large sections through paragraphs, sentences, and a hard boundary fallback without inventing punctuation or dropping meaningful text.
- Represent chunks using source spans and explicit overlap spans so source coverage can be tested independently of presentation whitespace.
- Reserve room for overlap within the chunk target and effective embedding budget. Trim overlap before sacrificing new source content; compute overlap from original spans to prevent overlap accumulating across chunks.
- Recompute token counts after overlap and splitting. Give final pieces unique IDs and correct final positions/counts while retaining parent identity and source offsets.

**Tests: `test_content_preservation.py`**

- Cover a preamble, no headings, nested headings, fenced code, tables, long paragraphs, long unbroken strings, punctuation, Unicode, and trailing short content.
- Verify the ordered non-overlap source spans reconstruct the original content exactly; separately test any documented display whitespace normalization.
- Exercise zero overlap, overlap of one/two tokens, and overlap near the allowed maximum. Assert no whole-previous-chunk duplication from a zero-length slice.
- Assert every final input fits the smaller of the chunk target and embedding budget, including separators and overlap.
- Assert IDs are unique and deterministic, positions/counts describe final pieces, and every split retains source provenance.

**Exit gate:** All content-preservation tests and Phase 1 tests pass. No fixture loses source text or exceeds its final measured budget.

## Phase 3 — Preserve embedding semantics and bound recovery

**Changes**

- Replace document fallback calls to `embed_query()` with singleton `embed_documents([text])` calls, including tracked variants. Keep query embedding exclusively for retrieval queries.
- Pack requests against separate per-input, batch-item, and aggregate-token limits exposed by provider capabilities. Reuse existing provider batching where possible and avoid conflicting retry loops.
- Classify provider exceptions using structured status/code data where available. Isolate any necessary message matching in provider-specific adapters; the word `token` alone is insufficient.
- Apply one overall attempt budget and deadline across manager and provider retries. Bound concurrency, split depth, and generated-piece count; propagate cancellation.
- Validate embedding cardinality, vector dimensions, and finite numeric values before treating an input as successful. Preserve input-to-vector mapping and tracked usage across retries without double counting.

| Failure | Recovery policy |
|---|---|
| Authentication/authorization or invalid model configuration | Stop; do not fan out into individual calls |
| Rate limit, timeout, transient service failure | Bounded backoff with jitter; honor retry hints within the deadline |
| Batch item/aggregate size exceeded | Reduce the batch while retaining completed results |
| Per-input context exceeded | Split the offending input further and retry as documents; retain provenance |
| Unknown error or malformed embedding response | Explicit failure; no unbounded speculative retries |

**Tests: `test_embedding_recovery.py`**

- Use a fake that fails if document ingestion calls a query API; exercise normal, singleton, tracked, and untracked paths. Mock Cohere's client to verify document input type on fallback.
- Assert exact input ordering/mapping under batch partitioning and individual failures; test short, empty, wrong-dimensional, and nonfinite responses.
- Inject each error category and assert attempt counts, batch limits, delays, and terminal reason. Include an estimated-count input rejected by the provider and then successfully split.
- Verify no singleton fan-out on authentication errors, no retry storm when provider retries are active, and prompt cancellation.
- Extend existing embedding usage tests to cover document fallback and usage reported before a failure, without counting unreported usage as provider-reported usage.

**Exit gate:** Recovery and existing embedding usage tests pass alongside earlier gates. Every simulated failure terminates within its configured limits and every document retains document embedding semantics.

**Status: complete.** Implemented in `server/utils/embedding_recovery.py` (new): structured error classification (`classify_embedding_error`, using status codes and provider-exposed `.code`/`.body` fields only -- never a bare message match), a `RecoveryConfig`/deadline-and-attempt budget shared across every batch/split/retry, request packing against a provider's `batch_size` and an optional `aggregate_token_limit`, and response validation (cardinality, per-vector dimensional consistency, finite values) before any input is treated as embedded. `ChunkManager.store_chunks` (`server/utils/chunk_manager.py`) now calls `embed_documents_with_recovery` directly instead of the old two-step batch-then-individual-embed_query fallback; the individual/singleton fallback path was the `embed_query()` document-embedding bug this phase fixes -- it now always calls `embed_documents(_tracked)`, including for a single oversized input, and query embedding (`ChunkManager.retrieve_chunks`) is untouched. `intent_firecrawl_retriever.py` needed no changes: it never called `embed_query` for documents.

Test commands run from the repo root (`venv/bin/python -m pytest -c server/tests/pyproject.toml ...`):

- `server/tests/test_chunking_safeguards/test_embedding_recovery.py` -- 32 passed
- `server/tests/test_chunking_safeguards` (full package) -- 99 passed
- `server/tests/test_embeddings/test_embedding_cost_tracking.py` -- 22 passed (extended: the batch/fallback usage test now asserts the singleton fallback uses `embed_documents_tracked`, not `embed_query_tracked`)

`ruff check` passes on all changed files. Limitations: the packing/classification layer bounds concurrency and split depth but batches within one round are still dispatched with `asyncio.gather` rather than a work-stealing pool, so `max_concurrency` bounds concurrent provider calls per round, not globally across rounds; this is intentional (rounds are short-lived and bounded by the shared deadline) but worth revisiting if a provider needs stricter global concurrency. Provider-specific structured-code tables (`_CONTEXT_CODES`/`_BATCH_CODES`) are seeded from OpenAI's error shape; providers exposing different structured codes for context/batch-size errors will classify as `unknown` until their codes are added.

## Phase 4 — Make ingestion completeness and cache state explicit

**Changes**

- Replace the ambiguous storage boolean with a structured result carrying `complete`, `partial`, or `failed`, expected/stored/failed piece counts, failed IDs, and categorized reasons. Update all callers explicitly; do not rely on object truthiness.
- Mark complete only after all expected pieces are confirmed stored. Distinguish embedding failures from vector-store failures, including partial writes.
- Key ingestion identity by source URL, content hash, model identity, and chunking/budget version. Preserve deterministic piece IDs so retries are idempotent.
- Keep failed-piece retry state for the current ingestion lifetime; a later request retries missing pieces rather than accepting partial state as a complete cache hit. Apply Phase 3 retry limits on each attempt.
- On process restart, either recover trustworthy completion metadata or treat the source as uncached and rebuild idempotently. Do not imply durable retry support from an in-memory map.
- Isolate document generations in retrieval so changed/shorter content cannot return stale pieces. Test adapter capabilities before depending on metadata deletion; filter by generation where atomic replacement is unavailable.
- Log actual prepared, embedded, stored, and failed counts instead of the original input count as storage success.

**Tests: `test_ingestion_state.py`**

- Simulate one failure among several pieces: result is partial, complete cache lookup is false, and the next attempt can recover the missing piece.
- Assert successful pieces remain correctly aligned and are not duplicated on retries.
- Cover all embeddings failing, storage returning failure, partial writes, TTL expiry, explicit invalidation, and a new manager instance after restart.
- Change content at the same URL to fewer chunks; change model and budget versions; assert retrieval returns only the selected generation.
- Assert complete/partial/failed counts reflect confirmed persistence, including re-split pieces, and concurrent requests cannot publish false completion.

**Exit gate:** Ingestion-state tests and earlier gates pass. Missing content is never represented as a complete cached ingestion; retries and refreshes cannot mix generations.

**Status: complete.** `ChunkManager.store_chunks` (`server/utils/chunk_manager.py`) now returns a structured `IngestionResult` (`complete`/`partial`/`failed` `IngestionStatus`, expected/stored/failed counts, failed piece ids, and per-piece failure reasons) instead of a bare boolean; callers must read `.status` explicitly. Ingestion identity is `(source URL, prepared-content hash, embedding model identity, embedding budget version)`, hashed into a `generation_id`; piece ids are deterministic (`"{url_hash}:{generation_id}_p{index}[_s{split}]"`) so retries are idempotent and never re-store an already-confirmed piece. A partial result keeps only its still-missing pieces pending (in-memory, current-process-lifetime only) and a later `store_chunks` call for the same generation retries just those, without re-embedding or re-storing pieces already confirmed written. Vector-store write failures are now distinguished from embedding failures (`vector_store_write_failed` vs. the Phase 3 `FailureCategory` reasons) by writing each embedded piece individually and catching write failures per piece rather than treating a bulk write as all-or-nothing. `retrieve_chunks` filters by the latest known `generation_id` for a URL (tracked in-memory per process) so a superseded generation's stale pieces are never mixed into a query's results; without a known generation (e.g. immediately after a process restart, before any `store_chunks` call), no generation filter is applied -- this is documented as a limitation of the in-memory map, not a durable guarantee. `invalidate_cache` and `cleanup_expired_chunks` clear the associated ingestion/pending state so a URL is treated as fully uncached, not left as a stale partial.

Test commands run from the repo root (`venv/bin/python -m pytest -c server/tests/pyproject.toml ...`):

- `server/tests/test_chunking_safeguards/test_ingestion_state.py` -- 11 passed
- `server/tests/test_chunking_safeguards` (full package) -- 137 passed
- `server/tests/test_embeddings/test_embedding_cost_tracking.py` -- 22 passed

`ruff check` passes on all changed files (pre-existing `BLE001`/`DTZ003` findings in `chunk_manager.py`/`chroma_store.py` predate this phase and are unchanged in kind). Two review-driven fixes since the initial implementation:

- `server/vector_stores/implementations/chroma_store.py`'s `add_vectors` used `collection.add()`, which rejects an id that already exists rather than upserting it; on the default persistent Chroma adapter this meant a retry after a process restart -- reusing the same deterministic piece ids -- reported every already-stored piece as a failed write and never reached `COMPLETE`. Changed to `collection.upsert()`. As defense in depth for any other add-only adapter, `ChunkManager.store_chunks` now also confirms a rejected write's id already exists (via `get_vector`, when the store supports it) before counting it as a real failure.
- `invalidate_cache` and `cleanup_expired_chunks` previously cleared only the *latest* generation's `_ingestion_state`/`_pending_pieces` entry for a URL. An older partial generation's pending map survived invalidation; re-ingesting that older content could report `COMPLETE` after storing only its previously-missing pieces, since the retained pending map skipped pieces that `delete_by_metadata` had just deleted. Both now clear every generation's state for the URL hash.

Limitations: partial-write detection and idempotent piece ids depend on `add_vectors` returning `False`/raising on a rejected write rather than silently dropping it; a store that silently drops part of a bulk write without signaling failure would not be caught, and the existing-id fallback depends on the store implementing `get_vector`. Ingestion and generation state lives only in the `ChunkManager` process instance -- a restart does not recover partial-completion metadata (a fresh instance treats every URL as uncached and rebuilds idempotently, per the roadmap's own guidance, now compatible with add-only stores via the upsert/existing-id fixes above), and multiple `ChunkManager` instances (e.g. multiple worker processes) do not share pending-piece or generation state, so cross-process partial-retry coalescing and generation filtering are out of scope here.

## Phase 5 — Integrate bounded, visible retrieval degradation

**Changes**

- Make the Firecrawl retriever consume the structured ingestion result instead of ignoring storage success. Preserve access to successful partial results while indicating incomplete coverage in response metadata and a concise user-facing message where supported.
- Bound both retrieved-chunk output and raw-content fallback using the caller's remaining context allowance, reserving space for formatting and metadata. If that allowance is unavailable, use an explicit configured retrieval-context cap and document that the final prompt assembler remains responsible for the complete prompt budget.
- For missing embeddings or no relevant results, return deterministic source excerpts within that budget, with source attribution and truncation/coverage information. Do not silently send the entire page.
- Handle a budget too small for useful content with an explicit bounded unavailable result. Keep provider and implementation details in diagnostics rather than user-facing text.

**Tests: `test_firecrawl_fallback.py`**

- Exercise complete, partial, and failed ingestion, initialization failure, no similarity matches, and unavailable vector storage through the retriever boundary.
- Verify partial status survives formatting and failed ingestion does not log successful storage.
- Test oversized pages and long metadata: final formatted output, including notices, fits the supplied budget.
- Verify excerpt selection is deterministic, attribution survives, truncation is disclosed, and a tiny/zero allowance does not create an unbounded error message.
- Assert retrieval query embeddings continue to use query semantics.

**Exit gate:** Retriever tests and earlier gates pass. Every fallback is bounded and incomplete coverage remains observable to callers.

**Status: complete.** `IntentFirecrawlRetriever` now resolves a `retrieval_context_budget` (configurable via `max_retrieval_context_tokens`, default 6000) in `initialize()`, independent of whether chunking itself is enabled. The pipeline does not currently pass this retriever the caller's remaining prompt-context allowance, so this is the explicit configured cap the roadmap permits as a fallback; the final prompt assembler remains responsible for the complete prompt budget.

- `_process_with_chunking` now consumes `ChunkManager.store_chunks`'s `IngestionResult` explicitly: `FAILED` skips chunk retrieval entirely and returns the bounded raw-content excerpt; `PARTIAL` proceeds to retrieval but discloses incomplete coverage in the formatted output; `COMPLETE` (including the cache-hit path, which is COMPLETE by construction) proceeds normally. The resulting `ingestion_status` is also surfaced in the context item's metadata, not just the formatted text.
- `_format_chunked_results` assembles sections in relevance order against the resolved budget, truncating (never silently dropping mid-section) the first section that doesn't fully fit and disclosing both truncation and how many of the ranked sections were actually shown.
- `_format_firecrawl_results` (the raw-content fallback used for small pages, no-similarity-match results, and indexing failures alike) now returns a deterministic, budget-bounded excerpt via `split_text_to_budget` instead of the full page unconditionally, with source attribution and truncation disclosed.
- A budget too small to show anything useful (below `_MIN_USEFUL_CONTEXT_TOKENS`, both paths) returns an explicit bounded "unavailable" message instead of an unbounded error or a squeezed, useless fragment. Provider/implementation details (which vector store, which recovery path) stay in logs; user-facing text only says content is unavailable within budget.
- Query embedding is unaffected -- `retrieve_chunks` (and therefore `embed_query`) is called with the original query text unchanged.

Three review-driven fixes since the initial implementation, all about paths that bypassed the budget rather than being bounded by it: `_bounded_unavailable_message` now checks its own message against the budget (falling back to a shorter constant, then a hard character split, since a long source URL or a tiny configured budget could otherwise make the "unavailable" response itself exceed the budget it's reporting on); the "no content extracted" branch of `_format_firecrawl_results` (a successful scrape with empty markdown/HTML/text, but still page metadata and up to 10 links to assemble) now checks the assembled result against the budget and falls back to the bounded unavailable message if an arbitrarily long title or link list would exceed it; and the empty-`results`/failed-scrape early returns (previously returning before any budget was even constructed) now check their message against the budget too, falling back to `_bounded_unavailable_message` for a tiny budget or an arbitrarily long provider error string.

Test commands run from the repo root (`venv/bin/python -m pytest -c server/tests/pyproject.toml ...`):

- `server/tests/test_chunking_safeguards/test_firecrawl_fallback.py` -- 21 passed
- `server/tests/test_chunking_safeguards` (full package) -- 158 passed
- `server/tests/test_embeddings/test_embedding_cost_tracking.py` -- 22 passed

`ruff check` on `intent_firecrawl_retriever.py` went from 23 to 20 pre-existing findings (no new findings introduced); the new test file is ruff-clean. Limitations: token counting for the retrieval-context budget always uses the "estimated" character-ratio mode (no LLM tokenizer is plumbed through to this retriever), so the budget is a conservative approximation, not an exact accounting of what the eventual LLM call will see -- a small fixed slack (`_ESTIMATION_SLACK_TOKENS`) absorbs the rounding gap between per-piece and assembled-string estimates. The configured cap is a per-retriever default, not the caller's actual remaining context allowance, since that isn't currently threaded through the retrieval pipeline to this retriever.

## Phase 6 — Validate the integrated contract and update documentation

**Changes**

- Add an offline integration test from scraped Markdown through chunking, embedding, storage, retrieval, and final formatting. Use fixtures whose content coverage and relevant sections are known.
- Record counters for splits, retry categories, rejected pieces, ingestion outcomes, cache outcomes, and bounded fallback activations. Log effective budgets and counting mode without logging document bodies.
- Replace unsupported reliability/latency claims in the safeguards document. Separate implemented behavior from limitations, document configuration placement/defaults, explain retry ownership and partial-cache semantics, and link this roadmap.
- Verify any retained provider/model limit table against official documentation at implementation time, recording source and verification date. Do not infer limits from provider name alone.
- Benchmark fixed small, large, Unicode, and forced-fallback fixtures; record environment, fixture sizes, request counts, and p50/p95 timings. Compare normal-path overhead with a recorded baseline rather than publishing unmeasured figures.

**Tests: `test_pipeline.py` and documentation checks**

- Run successful ingestion and retrieval, a transient batch failure, underestimated input size, one permanently failing piece, cache repair, and all-provider-failure fallback end to end.
- Assert source coverage before embedding, final request budgets, correct document/query semantics, generation isolation, accurate completion state, and bounded output.
- Capture logs/metrics and assert counts match actual writes and attempts; no partial result produces a complete-success event.
- Run the complete safeguard package, existing embedding usage tests, and affected provider/retriever tests. Record environment-related exclusions explicitly; required offline acceptance tests must not be skipped.
- Validate relative documentation links and YAML examples against implemented configuration. Optional live-provider smoke tests run separately with credentials and costs explicitly controlled.

**Exit gate:** All offline acceptance gates pass without expected failures; affected regression suites pass; benchmark results and documentation match the implementation; `git diff --check` passes.

## Completion checklist

- [x] Phase 1: consistent budgets and explicit counting modes
- [x] Phase 1b (follow-up, optional; not part of the Phase 6 gate unless merged first): `FileVectorRetriever.index_file_chunks()` validates every outgoing chunk against a resolved `EmbeddingBudget`; uploaded-file chunkers' decode-failure estimates and unlabeled character-as-token counting are fixed
- [x] Phase 2: source preservation and bounded final chunks
- [x] Phase 3: document-safe, bounded embedding recovery
- [x] Phase 4: explicit completeness and recoverable cache state
- [x] Phase 5: bounded retrieval and visible partial coverage
- [ ] Phase 6: integrated validation and accurate documentation

Record test commands/results and any remaining limitations with each completed phase. Do not mark the roadmap complete solely because normal-path ingestion works.
