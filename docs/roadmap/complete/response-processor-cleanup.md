# Response Processor Cleanup — Phased Follow-ups

## Summary

A `/simplify` pass (four parallel review angles — reuse, simplification,
efficiency, altitude) over
`server/services/chat_handlers/response_processor.py` on 2026-11-04. The
safe, single-file findings were applied directly in that session: hoisted a
local `import base64` to the module top, parallelized the two independent
`log_conversation` writes (Elasticsearch + audit) with `asyncio.gather`,
guarded the `mcp_tools_used` set-build behind `if sources:`, and short-
circuited the `negative_indicators` substring scan so it only runs for
short responses.

Everything below touches a tuned multilingual heuristic, a widely-called
public method, or another module's capability registry, so it's phased for
independent follow-up rather than folded into the same-session cleanup pass,
ordered by value vs. risk.

Reference: review findings were produced by four parallel agent passes
(reuse, simplification, efficiency, altitude) over
`server/services/chat_handlers/response_processor.py` on 2026-11-04.

---

## Phase 1 — Low-risk, single-file fixes

Contained to this file; mechanical refactors with no behavior change if done
carefully. Good first bites.

- [x] **Fix `_sources_contain_actual_data`'s `row_count or result_count`
      bug (lines ~751-752) — independent of everything else below, do this
      first.** `metadata.get('row_count') or metadata.get('result_count')`
      treated an explicit `row_count=0` as falsy and fell through to
      `result_count`, discarding the "this source has zero rows" signal the
      check exists to catch. Fixed by checking presence explicitly
      (`row_count = metadata.get('row_count'); if row_count is None:
      row_count = metadata.get('result_count')`) instead of `or`-chaining.
      Added `test_sources_contain_actual_data_zero_row_count_with_nonempty_content`
      in `server/tests/chat_handlers/test_response_processor.py`, with
      `row_count=0` and content that reads as real data, so the fix can't
      hide behind the content-inspection fallback. Full test file (99 tests)
      passes.
- [ ] *(Optional)* **Collapse the `build_result` media-block duplication.**
      Lines ~467-495 repeat the same shape four times — `if X: result[Y] =
      X; result[Y_format] = format or default; if X_revised_prompt:
      result[Y_revised_prompt] = ...` — for image, video, document, and
      generated-audio. A loop over a small table of `(value, key,
      format_value, default_format, revised_prompt_value, extra_url_value)`
      tuples would cut the line count, but four explicit, readable blocks
      may genuinely be easier to maintain than a six-element-tuple table —
      treat this as optional polish, not a required cleanup. If done, it
      must produce byte-identical output keys for every existing call site:
      write a characterization test (call `build_result` with each media
      kwarg set individually and in combination, assert the exact resulting
      dict) before refactoring, not after.
- [x] **Fix `_content_indicates_empty`'s tab/space-separated pattern gap,
      don't generalize it.** Confirmed against the current code (lines
      ~791-802): the 7 `total_patterns` regexes are *not* a full
      3-label × 3-style combination — the colon-separated and markdown-table
      styles each cover all three labels (total/count/sum), but the
      tab/space-separated style (`r'total\s+\w+\s+(0|n/?a|...)'`) only exists
      for `total`, not `count` or `sum`. No `count`/`sum` whitespace-separated
      variant was requested, so generating the full 3×3 cross product (which
      would silently expand matching behavior to two currently-unmatched
      cases) was intentionally not done. The 7 patterns are left as literal
      entries, uncollapsed, with this rationale recorded so a future
      refactor doesn't "fix" the asymmetry as a side effect.

## Phase 2 — Multilingual "no results" detection consolidation

Both the reuse and simplification reviews independently flagged this as the
largest piece of duplication in the file, but it's a tuned heuristic that
directly controls when the "continue conversation" threading button appears
— a regression here is a silent UX bug, not a crash, so it needs its own
test pass before any merge.

- [x] **Audit for real drift between the three heuristics first.**
      `_NO_RESULTS_PATTERNS`/`_no_results_regex` (class-level, ~58 patterns
      across 7 languages), `negative_indicators` (~100 keywords inside
      `_response_indicates_no_results`), and `apologetic_starters` (~40
      prefixes) were built independently and already disagreed in places —
      confirmed concretely: the regex list scopes `outside|beyond` with
      `(my|the) (scope|knowledge|data)`, but the keyword list had bare
      `'outside'`/`'beyond'`, a much weaker, false-positive-prone match. Added
      a reproducing case to the new fixture corpus
      (`server/tests/chat_handlers/test_no_results_fixture_corpus.py`) —
      `"Sales figures for products priced beyond $100 ... regions outside the
      EU ..."` — confirmed it false-positived (returned "no results" for a
      135-char, data-bearing response) before the fix below, and passes
      after. Wrote the fixture corpus as a permanent regression test (see
      last Phase 2 item) covering true no-results and true data-bearing
      responses in all 7 languages — this is now the regression baseline for
      Step A/B below.
      As a narrow, low-risk fix (not the full Step A consolidation), removed
      the bare `'outside'`/`'beyond'` entries from `negative_indicators` and
      replaced them with the same qualified-context regex check the
      `_no_results_regex` rule already uses, so a genuine "outside my
      knowledge" still counts as one indicator but unrelated uses of either
      word (prices, geography) don't. 122 tests pass (99 existing + 23 new
      fixture-corpus cases).
- [x] **Step A — merge phrase definitions, scoped to Heuristics 1+2.**
      `negative_indicators` (the ~100-entry keyword-count list) has been
      removed. Both the ≥2-match rule and the any-match rule now evaluate
      against the single `_NO_RESULTS_PATTERNS` source via a new
      `_no_results_compiled` list (individually compiled patterns from the
      same source used to build `_no_results_regex`), under the same
      ≥150-char short-response gate both rules always shared.
      `apologetic_starters` (the ≥300-char prefix rule) was **not** folded
      in — see rationale below. 122 tests pass (99 existing +
      23 fixture-corpus) with zero regressions.
- [x] **Step B — simplify the detection policy for Heuristics 1+2.**
      Since both rules now read the same qualified, multilingual pattern
      source (not bare keywords), requiring a second match adds no real
      precision over a single match: `match_count >= 2` is now a strict
      subset of `match_count >= 1`, so the two heuristics collapsed into one
      count computed once, with `>= 1` sufficient to return `True` (matching
      the old regex rule's existing single-match threshold — it never
      required 2, only the keyword rule did). This removes the
      independently-maintained keyword list entirely rather than just
      relabeling it, which is the point of Step B. Verified against the
      full fixture corpus plus all pre-existing parametrized
      `_response_indicates_no_results` tests before and after — no case
      changed outcome.
      **`apologetic_starters` was deliberately left as its own literal list,
      not merged into `_NO_RESULTS_PATTERNS`.** Its rule is anchored
      (`response_stripped.startswith(starter)`), while the shared pattern
      source encodes *contextual* phrases (e.g. `"unfortunately.{0,50}(no
      |couldn'?t|unable)"` requires specific follow-up words), not the bare
      `'unfortunately'` the starter list intentionally allows. Reusing the
      pattern source for an anchored match would silently drop coverage for
      responses like "Unfortunately, ..." that don't happen to continue with
      one of the regex's required follow-up phrases — a real regression risk
      with no existing test granularity to catch it. Left as a separate,
      explicitly scoped follow-up if ever revisited, not bundled into this
      pass.
- [x] **Add the fixture corpus as a permanent regression test**, not a
      one-off audit script — this heuristic will keep attracting ad hoc
      phrase additions, and a single merged source makes that one place to
      extend instead of two or three. Done as part of the audit step above:
      `server/tests/chat_handlers/test_no_results_fixture_corpus.py`.

**Post-merge review found and fixed a real regression in Step A/B above**:
removing `negative_indicators` dropped coverage for denial phrasing like "The
requested dataset is unavailable, so I cannot retrieve it." — neither the
regex patterns nor `apologetic_starters` covered it, so with confident
sources this could have incorrectly enabled threading. Fixed by adding two
qualified patterns to `_NO_RESULTS_PATTERNS` — `(cannot|can't) (retrieve|
access|find|locate|provide|obtain)` and `unavailable.{0,30}(cannot|can't|
unable to) (retrieve|...)` — rather than a bare `unavailable` pattern, which
was tried first and reintroduced a false positive on data-bearing short
responses that happen to mention something else being unavailable (e.g. "This
endpoint is unavailable for free-tier users, but here are the 50 results from
the paid tier..."). Both cases are now in the fixture corpus. The review also
caught an unrelated latent bug the new test surfaced: `0 results?` matched
inside "**5*0* results**" (no digit boundary) — fixed to `(?<!\d)0 results?`.
The redundant `>= 2` / `>= 1` branch pair was also collapsed into a single
boolean `self._no_results_regex.search(...)` check, dropping the now-unused
per-pattern `_no_results_compiled` list entirely — the combined regex already
does the same job. 325 tests pass (`tests/chat_handlers/`), zero known
regressions.

## Phase 3 — Structured "has results" signal from the retrieval pipeline

The altitude review's core finding: inferring retrieval success by
regex/substring-matching the LLM's free-text reply in 7 languages is a
fragile band-aid over information that already exists upstream as a
structured value (row counts, hit counts). This phase is independent of
Phase 2 and does not wait on it — the Phase 2 consolidated prose heuristic
stays in place permanently as the fallback for any source that doesn't
(or can't) emit the new structured signal, not just during a migration
window.

- [x] **Specify the signal's semantics precisely before writing any code.**
      Settled semantics for the scope actually implemented below:
      - **Unknown vs. empty**: `has_results` is `True`/`False` only when a
        retriever explicitly sets it; the field is omitted entirely (not set
        to `None`) for anything that hasn't computed it, which
        `_sources_contain_actual_data` reads as "unmigrated — fall back."
        This mirrors, and is reconciled with, the Phase 1
        `row_count`/`result_count` fix.
      - **Precedence when fields disagree**: `has_results`, when present,
        wins outright over `row_count`/`result_count`/content-pattern
        checks for that source — it's set by the retriever with strictly
        more context (e.g. it knows the true pre-truncation count) than
        `_sources_contain_actual_data` can reconstruct from metadata alone.
      - **Mixed-source aggregation**: unchanged from today's existing
        any-source-has-data loop in `_sources_contain_actual_data` — a
        `has_results=True` source returns `True` for the whole list
        immediately (any-source-wins), a `has_results=False` source is
        skipped and the loop continues to the next source, same as the
        existing `row_count`/`empty_results` checks already do.
      - **Aggregate-zero rows and vector/relevance confidence** are
        explicitly **not** covered by this pass — see the deferred items
        below. Both require inspecting formatter/query-type context this
        change didn't touch.
- [x] **Define a typed field and thread it through `sources`/`metadata`
      — scoped to `intent_sql_base.py` only (the highest-traffic case,
      per the migrate-incrementally item below).** Added `has_results: bool`
      to the four result-formatting call sites in
      `server/retrievers/base/intent_sql_base.py`
      (`_format_execution_response`, both clarification/slot-fill "0
      results" fallbacks, and `_format_sql_results`'s empty and non-empty
      branches), computed from the pre-truncation row count so it reflects
      true emptiness rather than a post-truncation count. `intent_http_base.py`
      and the vector-retriever formatters are **not migrated** — see deferred
      items below.
- [x] **Make `_has_meaningful_results` prefer the structured signal when
      present**, via `_sources_contain_actual_data`
      (`server/services/chat_handlers/response_processor.py`): `has_results
      is False` short-circuits that source to empty, `has_results is True`
      short-circuits the whole method to `True`, and its absence falls
      through unchanged to the existing row_count/content-pattern checks.
      Covered by new tests in `test_response_processor.py` (structured
      True/False/absent precedence) and
      `test_intent_sql_has_results_signal.py` (field correctly set at the
      retriever). 767 tests pass across `tests/chat_handlers/` and
      `tests/test_retrievers/`.
- [ ] **Deferred: aggregate-zero rows.** A `SELECT COUNT(*)`/`SELECT SUM(...)`
      query returning one row with value 0 would currently get
      `has_results=True` (row_count=1), which is wrong per the semantics
      above — `formatters.py` has no existing concept of "this template is
      an aggregate query" to key off, so this needs its own investigation
      into the template/query-type schema before it can be fixed correctly,
      not a guess bolted onto this pass.
- [ ] **Deferred: vector/relevance confidence.** Not addressed — no vector
      retriever was migrated in this pass. `_has_meaningful_results`'s
      existing Signal 2 confidence check is untouched and still applies.
- [ ] **Deferred: end-to-end tests covering streaming and non-streaming
      response paths.** Only formatter/unit-level and
      `_sources_contain_actual_data`-level tests were added. No change was
      made to `build_result` or the streaming pipeline in this pass, so the
      signal's survival through those paths is unverified beyond what the
      existing (unchanged) metadata-passthrough tests already cover.
- [ ] **Deferred: migrate remaining adapters.** Only
      `intent_sql_base.py` is migrated. `intent_http_base.py` and vector
      retrievers still rely entirely on the Phase 2 prose heuristic and the
      row_count/content-pattern fallback — tracked here as the next
      incremental migration target, per the "prose fallback stays permanent
      for unmigrated sources" policy above.

## Phase 4 — Adapter threading capability: single source of truth

The reuse and altitude reviews both flagged `_adapter_supports_threading`
(lines ~508-551) as a partial reimplementation of
`server/adapters/capabilities.py`'s `AdapterCapabilityRegistry`/
`AdapterCapabilities.from_config()`, plus a name-prefix fallback
(`startswith('intent-')`, `'qa' in name.lower()`, etc.) that exists nowhere
else in the capabilities system. The altitude review additionally confirmed,
by grepping `config/adapters/*.yaml`, that the overwhelming majority of
adapter configs already declare `capabilities.supports_threading` explicitly
— so the name-based fallback is largely dead weight masking a config-
completeness gap, not a genuinely needed heuristic.

- [x] **Audit every adapter config under `config/adapters/`** for a missing
      `capabilities.supports_threading` key, and add it explicitly wherever
      absent. Found 11 files missing it: `audio.yaml` (10 conversational/
      voice adapters, `false`), `passthrough.yaml`, `mcp-agent.yaml`,
      `web-search.yaml`, `web-search-providers.yaml` (8 adapters across
      these, all `false`), `file.yaml`'s `file-document-qa` (`false`), and
      three intent-DuckDB example configs —
      `alberta-shelter-occupancy.yaml`, `goc-ai-register.yaml`,
      `ottawa-hospital-ed-visits.yaml` — which had **no `capabilities` block
      at all** (not just a missing key), now added with `supports_threading:
      true`. Every value matches what the (now-deleted) name-prefix fallback
      already resolved to, so this is config-completeness only, no behavior
      change. Two untracked, uncommitted files (`talktoanyai.yaml`,
      `talktoanyai copy.yaml` — not part of this repository's committed
      config) were left alone as out of scope.
- [x] **Switch `_adapter_supports_threading` to use
      `get_capability_registry().get(adapter_name)`** instead of re-scanning
      `self.config['adapters']` by hand. Confirmed via new tests
      (`test_response_processor.py`,
      `TestResponseProcessorThreadingDetection`) covering the registry
      lifecycle edge cases: registry entry present (wins over config either
      way), registry empty for a configured adapter (falls back to the
      config scan rather than defaulting to `False`), registry empty and
      adapter unconfigured (`False`, no exception — matches
      `AdapterCapabilityRegistry.get()`'s `None`-for-unknown contract), and
      a simulated hot-reload (register → unregister, mirroring
      `adapter_reloader.py`'s delete/disable path) confirming the method
      reads current registry state rather than a cached value. 1063 tests
      pass across `tests/chat_handlers/`, `tests/test_adapters/`,
      `tests/test_retrievers/`, `tests/test_inference/test_prompt_builder.py`,
      and `tests/test_pipeline_steps/`.
- [x] **Delete the name-prefix fallback.** Done — `_adapter_supports_threading`
      no longer has `startswith('intent-')`/`'qa' in name.lower()`/etc.
      branches; an unregistered adapter now falls back only to a direct
      config scan (itself just a safety net for calls before the pipeline's
      capability-initialization step has run), with a bare `False` as the
      final default. `capabilities.py`'s registry is now the only place
      that decides whether an adapter supports threading, backed by every
      adapter config declaring the setting explicitly (previous item).

Phase 4 complete. All four phases of this roadmap are now done, with the
explicitly scoped-out items noted inline above (Phase 1's optional
`build_result` refactor; Phase 2's `apologetic_starters` merge; Phase 3's
aggregate-zero detection, vector confidence, e2e tests, and remaining
adapter migrations) left as deliberate, documented follow-ups rather than
silently dropped.
