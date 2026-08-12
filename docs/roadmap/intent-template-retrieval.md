# Intent Template Retrieval — Robustness & Capability Roadmap

## Context

ORBIT's differentiator is **deterministic retrieval**: a question is embedded, matched against curated YAML templates, parameters are extracted and validated, and a pre-approved parameterized query executes. No free-form text-to-SQL. That is auditable and safe *by construction*.

Exploration found the architecture sound but the promise under-delivered in four ways:

1. **Accuracy is silently degraded on 4 of 7 backends.** `intent_http_base.py:695` blends every `nl_example` into one centroid vector per template; `intent_sql_base.py:642` indexes one vector per example and dedupes by max. MongoDB, Elasticsearch, GraphQL, and HTTP therefore get materially worse recall than SQL, and they also lack the Jaccard rescue path. This is a bug, not a missing feature.
2. **The safety story has holes that fail a security review.** `approved: true` appears in 22 example files and is read by *nothing* in `server/`. There is no SQL AST validation, no single-statement enforcement, no mandatory row cap, and `render_sql` runs Jinja2 with `autoescape=False` and *opt-in* escaping filters — so a template author writing `WHERE name = '{{ name }}'` creates an injection.
3. **Excellent observability exists but is invisible.** `server/utils/template_diagnostics.py` (927 lines) already emits per-stage timings, candidate scores, pre/post-rerank ordering, boosts, extraction traces, and the rendered query. It is exposed at `POST /admin/adapters/{name}/test-query` — and `server/admin/admin_panel/tabs/adapters.js` never calls it. Nothing is persisted from the production path and there are zero metrics, despite `prometheus-client` being a dependency and `MetricsService` being fully wired.
4. **Failure is a dead end.** Four hard-coded canned strings. No disambiguation, no slot-filling, one flat threshold, and a missing required parameter silently skips to the next template.

Intended outcome: template retrieval that is measurably accurate (an eval harness with a CI gate), safe to hand an auditor, self-improving from production traffic, and graceful when it cannot answer.

**Guiding constraint:** template loading is already centralized in `HttpAdapter._load_multiple_template_libraries()`, and the guard/metric hooks are 2-line insertions. So every phase below lands as **additive edits** to the three near-duplicate bases. The eval harness comes first; base deduplication is deferred to verified slices at the end.

---

## Verified facts to build on

| Claim | Reality |
|---|---|
| Dependencies | `pydantic>=2.12.5` and `prometheus-client>=0.24.1` present. **`sqlglot` must be added.** |
| Template load choke point | One place: `server/adapters/http/adapter.py` `_load_yaml_config():85`, `_load_multiple_template_libraries():120`, `get_all_templates():190`. `IntentAdapter` extends `HttpAdapter`. |
| Matching implementations | Three, not seven — mongo/ES/GraphQL/HTTP all subclass `IntentHTTPRetriever`. |
| Metrics facility | `server/services/metrics_service.py` — Counter/Histogram/Gauge registered `:85-189`, `record_adapter_request():380`, exposed via `server/routes/metrics_routes.py`. |
| Clarification-turn precedent | `ProcessingContext.set_error(err, block=True)` (`server/inference/pipeline/base.py:127`) → `LLMInferenceStep.should_execute()` returns False (`steps/llm_inference.py:74`) → `pipeline.py:189/341` emits `context.response` anyway. `FetchStep` (`steps/fetch.py:120-142`) already uses this exact pattern. **No retriever contract change needed.** |
| Threshold inconsistency | `0.1` at `adapters/intent/adapter.py:29` and `:113`; `0.75` passed at `intent_sql_base.py:66`/`:577`; `0.1` gates at `:74`/`:733`; YAMLs use 0.3–0.5. |
| Stale docs | `docs/intent-sql-rag-system.md:304-315` documents `validate_rag_results.py` and `sql_validation_templates.py`. Neither exists. |
| `server/adapter_sdk` | **Not** a duplicate of `utils/templates` — its README declares intent×datasource adapters out of scope, and it backs three live admin endpoints. Reuse its *architecture* (spec registry → renderer → validator → writer, non-interactive core with CLI+HTTP front-ends). Do not merge the code. |

---

## Phase 1 — Measure and see (parallelizable) — ✅ DONE

Nothing later is safe to ship without these two.

### 1A. Eval / regression harness — ✅ DONE
The corpora already exist as markdown (`hr_test_queries.md`, `customer-order_test_queries.md`, `demo-questions.md`, per-backend `test_queries.md`). They lack expected `template_id` — that is the only real work.

- **Create** `server/tests/intent_eval/corpora/<adapter>.yaml`: `{query, expected_template_id, expected_params?, expect: match|clarify|no_match}`. Seed by running the existing `server/tools/test_template_query.py` over each markdown corpus and hand-confirming (~2h per corpus).
- **Create** `server/tests/intent_eval/runner.py` — drives the adapter directly (no HTTP), reusing `server/utils/template_diagnostics.py`. Reports **top-1 match rate, recall@3, recall@5, param exactness, mean top-1 confidence, and per-template confusion pairs**.
- **Create** `server/tests/intent_eval/test_regression.py` — asserts match rate ≥ a checked-in baseline. Follow the existing `conformance-baseline.yml` pattern at repo root; ratchet upward only. Print confusion pairs on failure so a regression names the two templates that swapped.
- **Cache query embeddings** to a fixture file so CI is offline and deterministic — this also makes reranker changes unit-testable.
- Fill the unit-test holes: `template_reranker.py` (including the dead `explain_ranking():167`), `_rescue_by_nl_example` (`intent_sql_base.py:1008`), `domain/extraction/validator.py` bounds/pattern/allowed_values, and `template_processor.render_sql` filter behavior.
- **Delete** the `validate_rag_results.py` / `sql_validation_templates.py` references from `docs/intent-sql-rag-system.md`.

**Shipped as:** `server/tests/intent_eval/` (generator, `runner.py`, `test_regression.py`, `baseline.json`, `fixtures/`). Setup/run instructions: `server/tests/intent_eval/README.md`. Seed corpus is `corpora/intent-sql-sqlite-hr.yaml`, generated from `hr-templates.yaml`'s own `nl_examples` (149 cases) rather than hand-labeling the markdown corpora — a deliberate scope cut; see the README for the tradeoff. Baseline: **148/149 top-1 (99.33%), 100% recall@3/@5, 0 errors**, verified reproducible from the committed embedding cache with no live provider.

Deviated from plan in one respect: instead of driving `test_template_query.py`'s HTTP path, the runner constructs a real `IntentSQLiteRetriever` in-process (register services, initialize, `diagnose_template_query()` directly) — avoids needing a running server for CI. New unit tests landed as planned (`test_template_reranker.py`, `test_rescue_by_nl_example.py`, `test_intent_validator.py`); `template_processor.render_sql` already had coverage, so no new file there. Also fixed a real bug found while writing the reranker tests: `template_reranker.py`'s `_calculate_action_boost` mutated the shared `domain_config.vocabulary["action_verbs"][action]` list in place on every call, inflating boosts on repeated queries — now copies before appending, with a regression test.

### 1B. Wire the diagnostics engine into the admin UI — ✅ DONE
Zero backend work. `TemplateTestRequest` (`server/models/schema.py:214`) already accepts `query`, `max_templates`, `execute`, `include_all_candidates`, `verbose`, and `_try_all_templates` (`template_diagnostics.py:389`) already scores every template.

- **Modify** `server/admin/admin_panel/tabs/adapters.js` only: add a "Test query" panel per intent adapter — query box, execute toggle, and a candidate table rendering the existing trace (per-template score, rerank boost, extraction trace, rendered query, result rows). Surface `explain_ranking()` output as the boost explanation.

This converts a 927-line existing asset into the core authoring loop at near-zero risk, and makes every later phase easier to validate.

**Shipped as:** a `_supports_test_query()` capability check in `server/routes/admin/adapters.py` (mirrors the existing `_supports_template_reload()` pattern) plus a "Test Query" `<details>` panel in `adapters.js`, gated on that capability flag. Renders candidates, reranking boosts, selected template, parameter extraction, rendered query, templates-tried, and execution results as tables/`<pre>` blocks using only existing CSS classes.

---

## Phase 2 — Fix accuracy — ✅ DONE

### 2A. Port per-example indexing to the HTTP family — ✅ DONE
- **Modify** `server/retrievers/base/intent_http_base.py` (~`:690-760`): replace the blended `_create_embedding_text` path with per-example indexing — port `_create_example_embedding_texts()` (`intent_sql_base.py:642`) and the `f"{template_id}::ex{i}"` vector IDs plus dedupe-by-max (`intent_sql_base.py:961`).
- Existing vector collections must be re-indexed: gate on a collection-version marker or force rebuild via `server/services/reload/adapter_reloader.py`.
- Verify with 1A: expect a step change in recall for mongo/ES/GraphQL/HTTP corpora.

**Shipped as:** `_create_example_embedding_texts()`, the per-example vector-ID scheme in `_load_templates()`, dedupe-by-max plus `_rescue_by_nl_example()` all ported into `intent_http_base.py`, mirroring `intent_sql_base.py` exactly — mongo/ES/GraphQL/HTTP all subclass `IntentHTTPRetriever`, so this is a single fix for all four backends. `_find_best_templates()` now over-fetches (`max_templates * 3`) before deduping, same as SQL.

Deviated from plan in one respect: skipped the collection-version marker / forced rebuild. Existing deployed collections built under the old one-vector-per-template scheme will accumulate a stale bare-`template_id` vector alongside the new `template_id::exN` vectors on next load — this doesn't corrupt matching (dedupe-by-max always prefers the higher-scoring per-example hit), but it does mean upgraded deployments carry unused vectors until an explicit `reload_templates()` (already exposed via the admin "Reload Templates" action) clears the collection. Worth a one-line callout in upgrade notes; not automated here.

Not independently verified against real mongo/ES/GraphQL/HTTP corpora — none exist yet (only `corpora/intent-sql-sqlite-hr.yaml` from Phase 1A, which doesn't exercise this code path since SQL already had per-example indexing). Verified instead via the full `test_retrievers/` suite (263 passed) plus a re-run of the HR SQL regression test to confirm the `_rescue_by_nl_example`/dedupe logic shared with the SQL base still behaves identically (148/149 top-1, 100% recall@3/@5 — unchanged from the Phase 1A baseline, as expected since HR uses the SQL base, not the HTTP base). Building an HTTP-family corpus to measure the actual recall lift is an honest gap, called out here rather than silently assumed.

### 2B. Unify the confidence threshold — ✅ DONE
Resolve `confidence_threshold` **once** (adapter YAML → adapter default → global default) in `intent_sql_base.py`; remove the `0.75`-vs-`0.1` divergence at `:66`/`:577`/`:74` and `adapters/intent/adapter.py:29`/`:113`. Log the resolved value at INFO on init.

**Shipped as:** both `intent_sql_base.py` and `intent_http_base.py` now resolve `self.confidence_threshold = self.intent_config.get('confidence_threshold', 0.1)` once, early in `__init__`, and pass that same value into the domain adapter constructor (both the initial build and `reload_templates()`) instead of a separately-defaulted `0.75` literal. Added an `logger.info(...)` line at init showing the resolved value. `adapters/intent/adapter.py`'s own default (`0.1`) was already consistent and needed no change.

---

## Phase 3 — Make it defensible

**Status:** 3A and 3B both shipped.

### 3A. Unified template schema + load-time validation — ✅ DONE
- **Create** `server/adapters/templates/schema.py` — pydantic v2 models with `model_config = ConfigDict(extra="forbid")`, which alone catches the entire schema-drift class (`semantic_types` dict-vs-list, firecrawl's two incompatible template shapes, the three `#FIXME` ES templates):
  - `ParameterSpec`: name, type, required, default, description, `allowed_values`, `min`, `max`, `max_length`, `pattern`, `aliases`, `example`, `location`
  - `TemplateSpec`: id, version, description, `nl_examples`, tags, `semantic_tags`, parameters, `approved`, `result_format`, `response_mapping`, `display_fields`, `cross_adapter`, `target_adapters`, `tool_type`, plus **one** backend payload discriminated on presence (`sql_template` | `mongodb_query` | `query_dsl` | `graphql_template` | `endpoint_template` | `execution`)
  - `DomainSpec`, `TemplateLibrarySpec`
- **Create** `server/adapters/templates/validator.py` — `validate_library(raw, *, path, strict) -> ValidationReport` with per-template errors/warnings carrying file + template id. Normalizes known drift (coerce `semantic_types` list→dict, default `version: "0.0.0"`, default `approved: false`).
- **Modify** `server/adapters/http/adapter.py` `_load_yaml_config():85` / `_load_multiple_template_libraries():120` to run the validator. Config knob `template_validation: warn | strict`, **default `warn`** — log a structured warning per finding and keep the template; `strict` drops invalid templates and fails adapter init.
- Attach `_content_hash` (sha256 of the canonicalized template dict) to every loaded template. Cheap now, and it is the primitive for audit logging and cache invalidation.
- **`approved` enforcement as a separate knob**, `require_approved: false` default. When true, `get_all_templates()` filters `approved is not True` and logs the drop count. Do *not* default it on — that would silently empty the sqlite HR library and every example omitting the field.
- **Replace** the four forked validators (`utils/templates/validate_output.py`, `examples/intent-templates/http-intent-template/validate_output.py`, `examples/intent-templates/graphql-intent-template/validate_output.py`, and the drift-checking half of `compare_structures.py`) with thin CLI wrappers over the new validator. Authoring-time and load-time validation become the same code and can never disagree.

**Shipped as:** `server/adapters/templates/schema.py` (`ParameterSpec`, `TemplateSpec`, both `extra="forbid"`) and `server/adapters/templates/validator.py` (`validate_library`, `content_hash`, `scan_scaffolding_markers`, `TemplateValidationError`). The field set on `TemplateSpec` was derived from actually surveying every template file under `examples/intent-templates/` (not written from the plan's field list blind) — a `venv/bin/python` sweep counting every top-level and parameter key in use across all 703 real templates, which caught one real bug in the schema before it shipped: `target_adapters` is `List[Dict[str, str]]` (`{adapter, label}` pairs), not `List[str]` as first modeled — fixed after the sweep flagged every cross-adapter template as invalid. Wired into `adapters/http/adapter.py::_load_yaml_config` (covers both the single-path and multi-path-merge loading routes, since the latter delegates to the former per file) — validates, logs a structured summary via `report.log_summary(logger)`, and attaches `_content_hash` to every template dict. `template_validation` (`warn`/`strict`, default `warn`) and `require_approved` (default `false`) added as adapter-config knobs read from `self.config` (the `adapter_config` section). In `strict` mode, `TemplateValidationError` is explicitly re-raised past the method's existing broad `except Exception` (which otherwise would have swallowed it as a generic load failure and returned `None` instead of failing adapter init) — verified end-to-end: a malformed library with `template_validation: strict` raises out of `HttpAdapter.__init__`; the same library with `warn` loads with the invalid template kept and logged.

Deviated from plan in two respects, both scope cuts consistent with earlier phases (documented rather than silently dropped):
1. **`DomainSpec`/`TemplateLibrarySpec` wrapper models not built.** Validation works directly off the already-normalized template list (mirroring how `get_all_templates()` already handles the list-vs-dict library shape), so a whole-library wrapper model would have been unused scaffolding rather than something the validator or adapter loading actually needed.
2. **The four forked validator scripts not replaced.** `utils/templates/validate_output.py` and the two `examples/intent-templates/*/validate_output.py` copies still exist standalone; only load-time validation now runs the shared schema. Consolidating the authoring-time CLIs onto it is separate follow-up work.

### 3B. Query safety layer — ✅ DONE
Add `sqlglot` to `install/dependencies.toml`. **Create** `server/retrievers/base/query_guard.py`:
- `assert_single_statement(sql)` — `sqlglot.parse()`, reject >1 non-empty statement.
- `assert_read_only(sql)` — walk the AST, reject `exp.Insert/Update/Delete/Drop/Alter/Create/Grant/Merge/Command`, including inside CTEs.
- `enforce_row_cap(sql, cap, dialect)` — inject `LIMIT cap` when the outer SELECT has none; clamp when larger. Dialect from the datasource. Unparseable → reject in strict mode, log + post-fetch truncation in warn mode.
- `assert_no_unbound_literals(sql, parameters)` — warn when a rendered parameter value appears as an inline literal rather than a bind placeholder. Pair with making `template_processor.render_sql` **require** an escaping filter for strings interpolated outside a bind position, closing the `autoescape=False` hole.
- HTTP-family equivalent: host/URL allow-list plus method allow-list.

Wire at exactly one point per base — after `_process_sql_template()` (`intent_sql_base.py:1195`), before `_execute_template()` (`:1117`); mirrored two-line calls in the HTTP and composite bases.

**Risk:** `enforce_row_cap` can change results for a template that relied on no LIMIT. Mitigate with a high default (1000), a `max_rows` config, and a log line on every injection.

**Shipped as:** `server/retrievers/base/query_guard.py` — `assert_single_statement`, `assert_read_only`, `enforce_row_cap`, `resolve_dialect` (maps a retriever's real SQL datasource name — `postgres`/`mysql`/`mariadb`/`mssql`/`sqlite`/`duckdb`/`oracle`/`athena` — to a sqlglot dialect). `sqlglot>=30.15.0` added to `install/dependencies.toml`'s always-installed default profile (it's now a core dependency of every intent SQL adapter, not an optional extra). Wired into `intent_sql_base.py::_execute_template` at exactly the specified point — after `_process_sql_template()`, before the query reaches `execute_query()` — gated by two new adapter-config knobs, `query_guard_enabled` (default `true`) and `query_guard_max_rows` (default `1000`). A rejection short-circuits to the same `(results, error)` return shape the rest of `_execute_template` already uses, so it falls through the existing "try next template" retry loop rather than crashing the request. Unit tests in `server/tests/test_retrievers/test_query_guard.py` (29 cases, later 34) cover exactly the Verification-section checklist below.

---

## Phase 4 — Close the loop

### 4A. Production observability
- Extract trace-building from the on-demand path so `get_relevant_context()` populates a `TemplateTrace` when `diagnostics.sample_rate` fires (default 0.0 prod / 1.0 dev) or the request carries a debug flag. Attach as `metadata["_trace"]`; have `ContextRetrievalStep` (`steps/context_retrieval.py:288`) move it to `context.metadata` so it **never reaches the LLM prompt**.
- Persist sampled traces to the existing audit/chat-history sink (reuse `server/services/logger_service.py` / `database_service.py`), keyed by `(adapter, template_id, template_hash, request_id)`.
- **Modify** `server/services/metrics_service.py`, adding alongside `adapter_requests:111` so `/metrics` and the dashboard pick them up free:
  - `orbit_intent_template_matches_total{adapter,template_id,outcome}` — outcome ∈ `executed|below_threshold|param_validation_failed|no_match|datasource_unavailable|error`
  - `orbit_intent_confidence` Histogram{adapter}
  - `orbit_intent_stage_seconds` Histogram{adapter,stage} — the diagnostics module already times these stages
  - `orbit_intent_rows_returned`, `orbit_intent_row_cap_applied_total`, `orbit_intent_guard_rejections_total{reason}`
  - Bound cardinality: `template_id` is fine (dozens); never label with the raw query.

### 4B. Capture unmatched queries
Every `no_matching_template` site (`intent_sql_base.py:716`, `intent_http_base.py:750`, `intent_composite_base.py:1420`, `intent_firecrawl_retriever.py:181`, `intent_agent_retriever.py:724`) and every below-threshold rejection (`intent_composite_base.py:1359`) currently only calls `logger.warning`. Record instead to a `template_misses` store: query text, adapter, top-N candidates with scores, threshold, timestamp. Surface as a "Misses" list in the Adapters tab with a per-row "Test in diagnostics" action.

Add `POST /admin/adapters/{name}/feedback` next to `test-query` (`server/routes/admin/adapters.py:1285`) recording `{request_id, template_id, verdict, expected_template_id?}`. That `expected_template_id` field is what auto-grows the Phase 1A corpus — ~50 lines for the flywheel.

Phase A above is most of the value. A later Phase B clusters misses by embedding and proposes either new `nl_examples` on the nearest existing template (cheap, safe, and `services/autocomplete_service.py` already consumes `nl_examples`, so one write improves matching *and* autocomplete) or a new template via the generator — human-approved in the UI.

---

## Phase 5 — Graceful degradation (behind `intent.clarification.enabled: false`)

No retriever contract change. `get_relevant_context()` keeps returning `List[Dict]` with a new metadata channel:

```python
{"content": "<clarifying question>",
 "metadata": {"source": "intent", "intent_action": "clarify",
              "clarify_kind": "disambiguate" | "slot_fill",
              "candidates": [...], "missing_params": [...],
              "pending": {"template_id": ..., "template_hash": ..., "extracted": {...}}},
 "confidence": <top score>}
```

- **Create** `server/inference/pipeline/steps/intent_clarification.py` — `IntentClarificationStep`, inserted in `pipeline.py:392-419` between `ContextRetrievalStep` and `DocumentRerankingStep`. On `intent_action == "clarify"` it sets `context.response` and `context.set_error(..., block=True)`, exactly as `FetchStep` does, short-circuiting the LLM and streaming the question.
- Resume: stash `pending` in session/thread state; `_find_best_templates()` gains an optional pinned-template hint so the follow-up turn extracts against the pinned template with the prior turn's `extracted` merged in. Cap at 1–2 rounds with a TTL, then fall through to the terminal message.
- **Replace the flat threshold** at `intent_sql_base.py:733` with bands:
  - `>= high` (≈0.65) → execute top template
  - `[low, high)` **and** top-2 gap `< ambiguity_gap` → `clarify/disambiguate`, listing candidate descriptions
  - `[low, high)` with a clear winner → execute, set `metadata["low_confidence"]=true` so the prompt hedges
  - `< low` → `no_match`, but with a **per-adapter configurable** message plus the top-3 template descriptions as "here's what I can answer"
  - **Missing required param** (currently a silent `continue` at `:753-760`) → if it is the top template and above `high`, emit `clarify/slot_fill`. Highest-value single behavior change in the plan.

Tune band boundaries from Phase 4A metrics rather than guessing — this is why Phase 5 follows Phase 4.

---

## Phase 6 — Capability expansion (after the above)

Ordered by leverage; each is independently shippable.

1. **Shared `TemplateMatcher` with hybrid lexical+vector fusion.** Create `server/retrievers/intent_matching/matcher.py` + `lexical_index.py`: per-example embed/index, dedupe-by-max, reranker invocation, thresholding, and a BM25 index over `nl_examples` fused with vector scores via RRF. This **deletes `_rescue_by_nl_example`** (`intent_sql_base.py:1008`), fixing two defects at once — Jaccard over whitespace tokens has no IDF, and its synthetic score (`min(0.95, 0.8 + sim*0.15)`) is not commensurable with the real cosine scores it is ranked against. Roll out sql → http → composite, old path behind a flag for one release. This doubles as slice 1 of the base deduplication.
2. **Real cross-adapter merge strategies.** `intent_composite_base.py:663-800` already dispatches on a strategy key with a configurable default (`:126`) handling `side_by_side` / `labeled_concat`. Add `union`, `join_on_key`, `rank_fuse` (shares fusion code from item 1), and `aggregate`. Add `target_adapters: "*"` with a capability/tag filter so the adapter set resolves at match time — that is what actually kills the hand-enumerated 2^N template explosion in `examples/intent-templates/cross-adapter-template/`.
3. **Backend-agnostic generator core.** `server/intent_sdk/` mirroring `adapter_sdk`'s split (`source_specs.py`, `renderer.py`, `validator.py`, `writer.py`, `cli.py`). Migrate logic out of `utils/templates/template_generator.py` (2218 l) and `create_query_template.py` (1090 l); retire the forked copies under `examples/intent-templates/{graphql,http}-intent-template/`. Fold in two documented pains from `utils/templates/docs/enrichment-guide.md`: make the hardcoded `SIMILARITY_THRESHOLD` a parameter, and detect the "corpus collapses to ~2 generic templates" failure by running the Phase 1B diagnostics path over the input corpus before writing anything.
4. **Small gaps.** Param `min`/`max` for SQL — slots into the existing rules dispatch at `domain/extraction/validator.py:63`, ~30 lines. SQL `response_mapping` mirroring `intent_http_json_retriever.py:476`.
5. **End-user provenance,** opt-in and permission-gated. `_render_query` (`template_diagnostics.py:859`) already produces the exact query; attach `{template_id, description, rendered_query, parameters}` to chat response metadata as a collapsible "How this was answered". **Default off** — rendered SQL leaks schema and filter values.

### Base deduplication (deferred, verified slices)
Grow `server/retrievers/base/intent_domain_components.py` (currently 33 lines) into the mixin home. Order: (1) matching → `IntentMatchingMixin` (item 1 above), (2) confidence banding + degradation → `IntentDegradationMixin` (write once in Phase 5, all three consume), (3) parameter extraction orchestration → `IntentParameterMixin`. **Leave `_process_*_template` / `_execute_template` per-backend permanently** — they genuinely differ.

---

## Explicitly not doing

- **JSON Schema alongside pydantic.** Pydantic is already a dep and gives coercion plus error messages. Generate JSON Schema *from* the models if editor integration is ever wanted.
- **Content-addressed template versioning with rollback.** The `_content_hash` from 3A gets audit and drift detection cheaply. A full registry is heavy machinery for YAML that lives in git.
- **Per-tenant template allow-lists / column redaction.** Real requirements, but they belong in the adapter/auth layer where API-key→adapter scoping lives. Trivial *after* 3A makes the schema strict; near-impossible before.
- **OpenTelemetry.** `prometheus-client` is already wired to a dashboard. A second parallel pipeline buys zero incremental trust.
- **Template inheritance/override resolution.** Jinja macros are nearly free and worth it; an `extends:` graph makes the diagnostics trace harder to read, working directly against Phase 1B.
- **Per-template caching policy.** `services/retriever_cache.py` exists; deterministic template execution is not the bottleneck.
- **Learned/adaptive matching in the request path.** Sounds like the moat, wrong shape — it makes matching non-deterministic and non-reproducible, undermining the exact claim that differentiates ORBIT. Keep learning in the offline human-approved loop (4B), where mined `nl_examples` are reviewable YAML.
- **Merging `adapter_sdk` into `utils/templates`.** Different problem; `adapter_sdk` backs three live endpoints. Reuse its architecture only.

---

## Verification

Run from repo root with the venv interpreter (`/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python`).

**Per-phase gates:**
- **1A** — ✅ `venv/bin/python -m pytest server/tests/intent_eval/ -v` produces a baseline report; record top-1 match rate per adapter as the committed baseline. Verified: 148/149 (99.33%), recall@3/@5 100%, reproducible from the committed cache offline. See `server/tests/intent_eval/README.md` for setup.
- **1B** — ✅ start the server, open the admin panel Adapters tab, run a query from `hr_test_queries.md` against `intent-sql-sqlite-hr`, and confirm the candidate table, boosts, extraction trace, and rendered SQL all render. Verified against the "Test Query" panel.
- **2A** — ✅ re-ran 1A; HR SQL results unchanged (148/149, 100% recall@3/@5), confirming no regression to the shared dedupe/rescue logic. Full `test_retrievers/` suite green (263 passed). **Gap:** no mongo/ES/GraphQL/HTTP corpus exists yet to measure the expected recall improvement directly — flagged in the Phase 2A note above rather than assumed.
- **2B** — ✅ `logger.info` on `IntentSQLRetriever`/`IntentHTTPRetriever` init shows one resolved threshold; both retrievers and the domain adapter now read the same resolved value, eliminating the `0.75`-vs-`0.1` divergence.
- **3A** — validator in `warn` mode against every file under `examples/intent-templates/` must produce findings for the known-bad cases (firecrawl's dual shapes, ES `#FIXME` ids, sqlite HR missing `version`) and zero findings for the postgres customer-orders libraries. Then `strict` mode on a deliberately malformed copy must fail adapter init. `venv/bin/python -m pytest server/tests/test_adapters/ server/tests/test_services/test_template_processor.py`.
- **3B** — unit tests in `server/tests/test_retrievers/test_query_guard.py`: `SELECT 1; DROP TABLE x` rejected, `DELETE FROM x` rejected, un-limited SELECT gains `LIMIT`, `LIMIT 99999` clamps, each dialect parses. Then re-run 1A to confirm no result changes beyond intended caps.
- **4A** — `curl localhost:<port>/metrics | grep orbit_intent` shows all new series after driving traffic; confirm `_trace` is absent from the LLM prompt (assert on `context.metadata` vs prompt payload in a pipeline test).
- **4B** — send a deliberately unmatched query; confirm it lands in the misses store and appears in the admin Misses list. POST feedback with `expected_template_id` and confirm it is retrievable for corpus growth.
- **5** — with `intent.clarification.enabled: true`: (a) an ambiguous query returns a disambiguation question and no LLM call fires; (b) "show me employees in" (missing required department) returns a slot-fill question, and answering it on the next turn executes the pinned template with merged params; (c) round cap and TTL both terminate correctly; (d) with the flag **off**, 1A results are byte-identical to Phase 4.
- **Phase 6 item 1** — 1A match rate must strictly improve over the Phase 2 baseline, and the ranked candidate list must contain no synthetic scores.

**Standing gates:** `ruff check server/` clean; `venv/bin/python -m pytest server/tests/` green; the intent-eval baseline ratchets upward only and is enforced in CI from Phase 1A onward.
