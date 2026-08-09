# Intent-eval: template matching accuracy harness

Measures whether intent adapters match the right template for a natural-language
query — independent of the LLM pipeline, HTTP layer, and admin auth. It drives a
real retriever in-process, calls `server/utils/template_diagnostics.py` per query,
and reports top-1 match rate, recall@3/@5, and confusion pairs against a
checked-in baseline.

This exists because template-matching accuracy had no regression coverage:
changing the reranker, the confidence threshold, or the `nl_examples` in a
template library could silently make matching worse, and nothing would fail.
See `docs/roadmap/intent-template-retrieval.md` (Phase 1A) for the fuller
rationale.

## Quick start

```bash
# From repo root, with Ollama running locally (embedding + inference models pulled):
venv/bin/python -m pytest server/tests/intent_eval/test_regression.py -q -m "" -s
```

`-m ""` overrides the default marker filter — the test is tagged
`integration`/`slow` and `pyproject.toml`'s default run excludes those. `-s`
shows the eval summary (`top1_match_rate`, `recall_at_3`, `recall_at_5`,
`mean_top1_confidence`) instead of swallowing it as captured output.

**First run vs. later runs:** the very first run against a query needs a
reachable embedding provider (Ollama by default) to compute that query's
vector; every subsequent run reuses the committed cache and needs nothing
running. See [Offline vs. online runs](#offline-vs-online-runs) below.

## What's in this directory

| Path | Purpose |
|---|---|
| `runner.py` | Builds a real `IntentSQLiteRetriever` in-process and runs a corpus through it. `build_hr_retriever()`, `run_eval()`. |
| `generate_corpus_from_templates.py` | Seeds/refreshes a corpus from a template library's own `nl_examples`. |
| `corpora/*.yaml` | `(query, expected_template_id, expect)` cases per adapter. |
| `baseline.json` | Checked-in pass/fail floor per adapter, as raw counts (not rates — see below). |
| `fixtures/embeddings_cache_*.json` | Committed query→vector cache, keyed by `provider::model::query`. Makes CI offline. |
| `fixtures/chroma_*` | Local vector store for template embeddings. **Not** committed — rebuilt from the templates file on first run (see `.gitignore`). |
| `test_regression.py` | The pytest entry point; asserts current results ≥ baseline. |

## Prerequisites

- The venv interpreter: `/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python`.
- Ollama running at `http://localhost:11434` **only if** you're adding new
  queries or the embedding cache doesn't already cover the corpus — see below.
  Pull the models the harness expects:
  ```bash
  ollama pull nomic-embed-text   # embedding
  ollama pull gemma4:e2b         # inference (parameter-extraction LLM fallback)
  ```
  `runner.py`'s `default_hr_retriever_config()` hardcodes these two model
  names; if you change either, update `HR_EMBEDDING_MODEL` in `runner.py` too
  so the cache-identity check (below) stays honest.

## Offline vs. online runs

Every query embedding is cached to `fixtures/embeddings_cache_<adapter>.json`
under a key of the form `{provider_class}::{model}::{query text}`. On each
run, `test_regression.py::_cache_covers_corpus()` checks whether *every* query
in the corpus already has a cache entry under the **current** provider/model
identity (`runner.hr_cache_key()`) — not just whether the query text appears
under some old key. That distinction matters: if you change the embedding
model, old entries for the same query text are for a different vector space
and must not be treated as "covered."

- **Cache fully covers the corpus:** the test runs entirely offline, no
  network calls, deterministic.
- **Cache is missing entries and Ollama is unreachable:** the test
  `pytest.skip()`s with an explanatory message rather than failing — a
  missing local model shouldn't look like a matching regression.
- **Cache is missing entries and Ollama is reachable:** the run proceeds,
  fetches the missing embeddings live, and **you should re-save the cache**
  (see below) so the next run and CI don't need Ollama again.

Expect roughly 4-5 seconds per *uncached* query — the harness runs the full
`diagnose_template_query()` pipeline (match → rerank → parameter extraction),
and local LLM fallback for missing required parameters is the dominant cost,
not the embedding call itself. A cold run over the 149-case HR corpus takes
roughly 12-14 minutes; a fully-cached run is dominated by the same LLM
fallback cost per query (parameter extraction still runs even when matching
is a cache hit), so expect a similar wall-clock time either way — caching
saves you from needing Ollama's embedding endpoint reachable, not from the
LLM inference cost.

## Adding queries to the corpus

Prefer appending directly to `corpora/<adapter>.yaml`:

```yaml
- query: "some new phrasing to cover"
  expected_template_id: some_existing_template_id
  expect: match
```

Then run the regression test once with Ollama reachable so the new query's
embedding gets cached, and re-save the cache (see next section).

To pull in new templates' `nl_examples` wholesale instead of adding by hand:

```bash
venv/bin/python server/tests/intent_eval/generate_corpus_from_templates.py \
  --templates examples/intent-templates/sql-intent-template/sqlite/hr/hr-templates.yaml \
  --output server/tests/intent_eval/corpora/intent-sql-sqlite-hr.yaml \
  --adapter intent-sql-sqlite-hr
```

This **regenerates** every case whose query text matches a current
`nl_example` (the templates file is the source of truth for those) but
**preserves** any case you appended whose query text isn't one of them. It
does not merge hand-edits to a case that *is* one of the regenerated
ones — edit the `nl_examples` in the templates file instead, upstream of the
corpus.

Why seed from `nl_examples` at all rather than hand-labeling the larger
markdown corpora (`hr_test_queries.md`, etc.)? Each `nl_example` is the
template author's own claim that a phrasing should match — the cheapest,
least-disputable ground truth available, and enough to catch real
regressions in matching/reranking logic. Hand-labeling the markdown corpora
with expected template IDs would give broader coverage and is a reasonable
next step, but is unclaimed, deliberately-scoped-out work — see the honest
gap called out in `docs/roadmap/intent-template-retrieval.md`.

## Updating the baseline

Only after a **genuine** accuracy improvement — never to silence a real
regression. `baseline.json` stores raw counts, not rates:

```json
{
  "intent-sql-sqlite-hr": {
    "total": 149,
    "top1_correct": 148,
    "recall_at_3_correct": 149,
    "recall_at_5_correct": 149
  }
}
```

Raw counts, not `top1_correct / total`, because rounding a rate for storage
and then comparing it against a freshly-computed float invites exactly the
kind of 1-ULP "regression" that isn't one. See the regeneration snippet at
the bottom of `test_regression.py` for the exact commands.

## Adding a new adapter's corpus

1. Write `corpora/<adapter>.yaml` (by hand, or seed it with
   `generate_corpus_from_templates.py` if the adapter has a template library).
2. Add a `build_<adapter>_retriever()` next to `build_hr_retriever()` in
   `runner.py` for that adapter's config shape, following the same pattern:
   real embedding client wrapped in `_CachingEmbeddingClient`, real vector
   store, `register_all_services()` once.
3. Add a `test_<adapter>_match_rate_meets_baseline()` in `test_regression.py`
   mirroring `test_hr_sqlite_match_rate_meets_baseline()`, and its own
   `hr_cache_key`-style helper if the provider/model identity differs.
4. Run once with Ollama reachable, confirm the summary looks right, then
   record the baseline as above.

## Related unit tests

These don't need Ollama or a corpus — they test matching/validation logic in
isolation with hand-built fixtures:

- `server/tests/test_retrievers/test_template_reranker.py`
- `server/tests/test_retrievers/test_rescue_by_nl_example.py`
- `server/tests/test_retrievers/test_intent_validator.py`
- `server/tests/test_services/test_template_processor.py` (pre-existing)

```bash
venv/bin/python -m pytest server/tests/test_retrievers/test_template_reranker.py \
  server/tests/test_retrievers/test_rescue_by_nl_example.py \
  server/tests/test_retrievers/test_intent_validator.py -q
```
