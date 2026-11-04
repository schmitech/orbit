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
- [ ] **Fix `_content_indicates_empty`'s tab/space-separated pattern gap,
      don't generalize it.** The 7 `total_patterns` regexes (lines
      ~778-789) are *not* a full 3-label × 3-style combination as originally
      assumed — the colon-separated and markdown-table styles each cover all
      three labels (total/count/sum), but the tab/space-separated style
      (`r'total\s+\w+\s+(0|n/?a|...)'`) only exists for `total`, not `count`
      or `sum`. Generating the full 3×3 cross product would silently expand
      matching behavior to two currently-unmatched cases. If the missing
      `count`/`sum` whitespace-separated variants are wanted, add them as a
      deliberate, tested behavior change — not as a side effect of a
      template refactor. Otherwise leave the 7 patterns as literal entries;
      collapsing them into a template is not worth the risk of silently
      changing what matches.

## Phase 2 — Multilingual "no results" detection consolidation

Both the reuse and simplification reviews independently flagged this as the
largest piece of duplication in the file, but it's a tuned heuristic that
directly controls when the "continue conversation" threading button appears
— a regression here is a silent UX bug, not a crash, so it needs its own
test pass before any merge.

- [ ] **Audit for real drift between the three heuristics first.**
      `_NO_RESULTS_PATTERNS`/`_no_results_regex` (class-level, ~58 patterns
      across 7 languages), `negative_indicators` (~100 keywords inside
      `_response_indicates_no_results`), and `apologetic_starters` (~40
      prefixes) were built independently and already disagree in places —
      e.g. the regex list scopes `outside|beyond` with
      `(my|the) (scope|knowledge|data)` while the keyword list has bare
      `'outside'`/`'beyond'`, which is a much weaker, false-positive-prone
      match (a response like "my dataset extends beyond Q3" would trip it).
      Before merging anything, write a fixture corpus of real/representative
      responses (true no-results replies and true data-bearing replies, in
      each of the 7 supported languages) and record what each of the three
      heuristics currently returns on it — this becomes the regression
      baseline.
- [ ] **Step A — merge phrase definitions only, keep the three detection
      rules unchanged.** Fold `negative_indicators` and
      `apologetic_starters`'s phrases into `_NO_RESULTS_PATTERNS` as the
      single source of truth (tightening any bare-word entries found in the
      audit step to the same qualified form the regex list already uses),
      but keep evaluating them as three separate rules against that one
      source: the ≥150-char short-response gate for the keyword-count and
      regex checks, the ≥300-char gate for the apologetic-prefix check, and
      distinct-keyword counting for the ≥2-match rule. These aren't
      interchangeable today — the keyword rule counts how many distinct
      entries from `negative_indicators` appear in the response, while the
      regex rule is a boolean "does `_no_results_regex` match at all,"
      with no count semantics — and the two length thresholds (150 vs. 300)
      are deliberately different cutoffs.
      Changing phrase *source* without changing detection *policy* keeps
      this step behavior-neutral and verifiable against the Phase 2 fixture
      corpus.
- [ ] **Step B — only then consider simplifying the detection policy**
      (e.g. unifying the two length thresholds, or switching the ≥2-keyword
      rule to a single regex-based count), as a separate, explicitly
      reviewed change with its own before/after comparison against the
      fixture corpus — not bundled into Step A.
- [ ] **Add the fixture corpus as a permanent regression test**, not a
      one-off audit script — this heuristic will keep attracting ad hoc
      phrase additions, and a single merged source makes that one place to
      extend instead of two or three.

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
