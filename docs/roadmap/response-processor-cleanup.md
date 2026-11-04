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

- [ ] **Specify the signal's semantics precisely before writing any code.**
      A row/hit count alone is not sufficient — it conflates several
      distinct cases that need explicit handling:
      - **Unknown vs. empty.** A source that doesn't report a count at all
        (field absent) must be distinguishable from one that reports a
        confirmed-zero count. Collapsing "we don't know" into "it was empty"
        (or vice versa) reintroduces a version of the same bug being fixed
        in Phase 1's `row_count`/`result_count` item.
      - **Aggregate rows that are themselves empty.** A SQL aggregate query
        (`SELECT COUNT(*) ...`, `SELECT SUM(...) ...`) can return exactly
        one row whose value is zero — `row_count=1` but the result is still
        "no data." The signal must be the *meaningfulness* of the result,
        not merely whether any rows came back.
      - **Vector/relevance confidence.** A nonzero hit count from a vector
        retriever doesn't mean the hits are relevant — low-similarity hits
        below a confidence floor should not count as "has results" just
        because they exist. Reuse or formalize the existing confidence
        check in `_has_meaningful_results` Signal 2 rather than dropping it
        once a count exists.
      - **Mixed-source aggregation.** When a turn's `sources` list contains
        results from more than one retriever/adapter call (composite
        adapters), define how per-source signals combine into one
        turn-level "has results" value — any-source-has-results,
        all-sources-have-results, and a weighted/primary-source rule are all
        defensible; pick one explicitly and document why.
      - **Precedence when fields disagree.** If the structured signal says
        "has results" but the Phase 2 prose heuristic says "no results" (or
        vice versa), define which wins and why, rather than leaving it to
        whichever check happens to run first.
- [ ] **Define a typed field (exact shape TBD by the spec above, e.g.
      `has_results: bool` plus a separate `result_count: Optional[int]`)**
      on retrieval results, attached at the source: `server/retrievers/base/
      intent_sql_base.py`, `intent_http_base.py`, and the formatters in
      `server/retrievers/implementations/intent/domain/response/
      formatters.py`. SQL/NoSQL retrievers already know their row count at
      query time; vector retrievers already know their hit count and
      similarity scores.
- [ ] **Thread the field through `sources`/`metadata`** so it survives to
      `build_result` unchanged, the same way `row_count`/`empty_results`
      already partially do in `_has_meaningful_results`'s Signal 2/3 checks
      — reconciled with the Phase 1 `row_count`/`result_count` fix so the
      new field and the old ones can't disagree with each other.
- [ ] **Make `_has_meaningful_results` prefer the structured signal when
      present**, applying the precedence rule defined above, and falling
      back to the Phase 2 consolidated prose heuristic for any source that
      doesn't carry the field. This keeps behavior unchanged for
      unmigrated/non-structured sources while removing the language-drift
      fragility for migrated ones.
- [ ] **Add end-to-end tests covering both streaming and non-streaming
      response paths**, not just the formatter/unit level — confirm the
      structured signal survives whichever path a given adapter/request
      actually takes through the pipeline to `build_result`.
- [ ] **Migrate adapters incrementally**, starting with the highest-traffic
      intent-SQL adapters, and track migration status so coverage is
      visible — the prose fallback is kept permanently for unmigrated or
      inherently unstructured sources, not deleted once migration
      "completes."

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

- [ ] **Audit every adapter config under `config/adapters/`** for a missing
      `capabilities.supports_threading` key, and add it explicitly wherever
      absent. This should shrink the set of adapters relying on the
      name-prefix fallback to near zero.
- [ ] **Switch `_adapter_supports_threading` to use
      `get_capability_registry().get(adapter_name)`** instead of re-scanning
      `self.config['adapters']` by hand. Confirm first (with a test) that the
      registry is populated for every adapter this method is called with at
      the point `build_result` runs — the registry's population lifecycle is
      different from a static config scan, so this needs verification before
      the swap, not just a signature-compatible drop-in. Extend the test
      coverage to the registry's lifecycle edge cases specifically: a config
      reload/hot-reload path (if one exists for adapters) that changes or
      removes an adapter's registration after startup, and a lookup for an
      adapter name that was never registered at all (confirm it returns
      `None`/a safe default rather than raising, and that
      `_adapter_supports_threading` handles that the same way the current
      config-scan version handles an unmatched name).
- [ ] **Delete the name-prefix fallback** once the config audit above closes
      the gap it exists for, so there's exactly one place (`capabilities.py`)
      that decides whether an adapter supports threading.
