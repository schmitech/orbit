# Admin & API-Key Security Hardening — Phased Implementation Plan

## Summary

Follow-up items from the `server/routes/admin/` security assessment and the
API-key plaintext-storage fix (see `docs/security/api-key-pepper-setup.md`,
`docs/sqlite-schema.md#api_keys` v1.22, and the `2.17.15` bearer-RBAC fix).
That work closed the critical finding (API keys stored in plaintext) and a
handful of high/medium items (mixed auth-dependency wiring, unredacted log
tail, path-traversal defense-in-depth, a narrow MCP metadata-SSRF check,
reverse-tabnabbing on the markdown preview). This plan tracks what's left,
in priority order, as independently shippable phases.

None of these are exploitable by an unauthenticated caller — every route
discussed here already sits behind bearer-token RBAC. The risk model
throughout is **compromised or overly-broad admin credentials**, **a
misconfigured deployment** (rate limiting off, weak/default pepper), and
**defense-in-depth** against a bug introduced later.

## Confirmed starting gaps

| Finding | Current behavior | Target behavior |
|---|---|---|
| No rate limiting on sensitive admin actions by default | `RateLimitMiddleware` covers `/admin/*` already, but `security.rate_limiting.enabled` defaults to `false`; a fresh install has no throttle on key creation, audit/log export, or MCP connection tests | Sensitive admin actions are rate-limited out of the box, independent of the general-purpose toggle |
| Raw API keys stored outside `api_keys` | `uploaded_files.api_key` (SQLite/Postgres) and its Mongo equivalent store the *raw* key as a foreign-key-like ownership field — the same class of at-rest exposure the `api_keys` collection fix addressed | File ownership is keyed by the same HMAC hash as `api_keys.api_key_hash`, never the raw key |
| Metadata SSRF guard is narrow | `_reject_cloud_metadata_host()` (added in the security-audit fix) blocks only `169.254.0.0/16` for the one-off MCP `test-connection` probe; saved MCP server configs have no equivalent check at all | A configurable denylist (loopback/link-local/RFC1918, metadata range always included) applies consistently to both the live probe and, optionally, saved config validation |
| No tenant/ownership scoping on API keys | Any admin holding the single global `apikeys.manage` permission can list/read/rotate/delete every key in the system; there is no per-adapter or per-owner restriction | Documented as accepted for a single-tenant deployment; scoped roles tracked as a follow-up if/when multi-tenant admin roles are needed |
| Unbounded admin audit-log free-text search | `GET /admin/audit/events?q=...` fetches up to 5,000 rows per request into Python for substring filtering rather than pushing `q` down to an indexed query | `q` filtering happens at the datastore layer (indexed `LIKE`/full-text), with a hard cap on `offset` |
| No pepper-rotation tooling | Rotating `ORBIT_API_KEY_PEPPER` silently invalidates every existing key with no warning or guided recovery path | `orbit key rotate-pepper --dry-run` (or equivalent) reports how many keys would be invalidated and requires explicit confirmation |
| Cosmetic: `hash_api_key()` name collision | `services/api_key_service.py:hash_api_key(key, config)` (peppered HMAC, for storage) and `utils/text_utils.py:hash_api_key(key)` (unsalted SHA-256, for chat-history ownership fingerprints) share a name but do different things | Rename one (`hash_api_key` → `hash_api_key_for_storage` in `api_key_service.py` is the smaller diff) to remove the ambiguity |

## Delivery and test rules

Implement phases in order; each is independently shippable and does not
depend on a later phase. Every phase ships with its own tests in the same
change — no phase is "complete" with failing or skipped tests.

Run the existing suites relevant to the phase, plus:

```bash
venv/bin/python -m pytest server/tests/test_admin/ server/tests/test_auth/ server/tests/test_services/test_quota_service.py server/tests/test_middleware/test_throttle_middleware.py server/tests/test_routes/test_admin_mcp_connection.py -q
```

No phase here changes an existing authenticated route's success-path
response shape; a behavior change is either additive (a new 429/422) or an
internal storage/lookup detail.

## Phase 1 — Rate-limit sensitive admin actions independent of the general toggle ✅ DONE

**Why first:** lowest implementation risk, highest abuse-reduction value —
today a compromised or over-broadly-scoped bearer token can mass-create API
keys or scrape the full audit ledger with zero throttling unless an operator
has separately opted into `security.rate_limiting.enabled`.

**Changes**

- Add a small, dedicated limiter (reusing `InMemoryRateLimiter` /
  `RateLimitMiddleware`'s cache-backed limiter, not a new implementation)
  scoped to a short allowlist of routes, active regardless of
  `security.rate_limiting.enabled`:
  - `POST /admin/api-keys` (key creation)
  - `GET /admin/audit/events`, `GET /admin/logs/tail` (bulk export/read)
  - `POST /mcp/test-connection` (outbound network probe)
- Default limits generous enough not to interfere with normal admin/CI usage
  (e.g. 20/minute for key creation, 60/minute for the read/export routes);
  configurable under a new `security.admin_rate_limiting` block, `enabled:
  true` by default (unlike the general-purpose limiter, this one guards
  actions expensive or sensitive enough to always throttle).
- Document the new config block in `config/config.yaml` and
  `docs/server.md`.

**Tests**

- A burst past the configured limit on each of the three routes returns 429
  with the existing `X-RateLimit-*` headers.
- The limiter does not activate below the threshold, and is unaffected by
  `security.rate_limiting.enabled: false`.
- Existing `test_admin_permission_guards.py`/`test_admin_mcp_connection.py`
  suites still pass unmodified (no change to auth behavior, only an
  additional 429 path).

**Exit gate:** the three routes above 429 under sustained abuse in a fresh
install with no config changes; existing admin/mcp test suites pass
unmodified.

**Status: shipped.** Implemented as `AdminRateLimitMiddleware` in
`server/middleware/rate_limit_middleware.py` (reuses `InMemoryRateLimiter`
and the cache-backed fixed-window technique), registered unconditionally in
`server/config/middleware_configurator.py`, with the
`security.admin_rate_limiting` block added to `config/config.yaml` and
`install/default-config/config.yaml`, and documented in
`docs/rate-limiting-architecture.md`. The actual MCP probe path is
`POST /admin/mcp/test-connection` (the plan text above said `/mcp/`), which
the implementation and its route-limit default use. Callers are keyed by
their parsed bearer credential (scheme-casing-insensitive, matching
`HTTPBearer`), falling back to IP for unauthenticated/non-bearer requests.
Tests: `server/tests/test_middleware/test_admin_rate_limit_middleware.py`
(8 cases). Full exit-gate suite passes; see commit for details.

## Phase 2 — Hash the raw key in `uploaded_files` ✅ DONE

**Why:** the exact class of exposure the `api_keys.api_key_hash` migration
fixed still exists one collection over. `services/file_metadata/metadata_store.py`
stores the *raw* API key in `uploaded_files.api_key` (SQLite/Postgres column,
Mongo field) purely as an ownership/filter key for `list_files()` and
`get_generated_file_ids_for_session()`.

**Changes**

- Add `uploaded_files.api_key_hash` (nullable, matching the `api_keys` v1.22
  pattern) alongside the existing `api_key` column; write both on insert
  going forward using `ApiKeyService.hash_api_key()`/the storage layer's
  hashing helper, keyed the same way `api_key_hash` is everywhere else.
- Update `list_files()`/`get_generated_file_ids_for_session()`/any other
  `{'api_key': ...}` query in `metadata_store.py` to filter by hash instead.
  This is a smaller-blast-radius version of the `_find_by_raw_key()` pattern
  used for `api_keys` — there's no "validate an existing raw value against
  storage" path here, only "write the hash of the caller's key, read back by
  hash of the caller's key," so no legacy-migration branch is needed: existing
  rows simply keep their (already-written) raw `api_key` value and are never
  matched by the new hash-based queries until a follow-up backfill (out of
  scope here; document as a known gap, matching the `api_keys` precedent
  where legacy rows migrate lazily rather than via a bulk script).
- Leave the legacy `api_key` column in place (do not attempt to null it out
  for existing rows in this phase) — this phase only changes what *new*
  uploads write and how *new* queries filter, avoiding a destructive
  migration on user file metadata.

**Tests**

- New upload writes `api_key_hash`; `list_files()`/`get_generated_file_ids_for_session()`
  filter correctly by the new field for a fresh upload.
- A pre-existing row (raw `api_key` only, no hash) is simply excluded from a
  hash-filtered query — document this as the expected, bounded gap for this
  phase (a full backfill is out of scope; see gap note above).

**Exit gate:** no new upload ever writes a raw key to a column intended for
long-term storage; existing `test_services/test_*file*` suites pass.

**Status: shipped.** Added `uploaded_files.api_key_hash` to the SQLite and
Postgres schemas (`server/services/sqlite_service.py`,
`server/services/postgres_service.py`) plus its index, picked up by the
existing additive startup migration — no manual migration step. MongoDB
needs no schema change. `FileMetadataStore.record_file_upload()` now writes
`api_key_hash` (via `services.api_key_service.hash_api_key()`) alongside the
legacy `api_key` column; `list_files()` and `get_generated_file_ids_for_session()`
filter by `api_key_hash` instead of the raw key. Documented as SQLite v1.23 /
Postgres v1.13 in `docs/sqlite-schema.md`/`docs/postgres-schema.md`, including
the known gap (pre-existing rows have no hash and are excluded from
hash-filtered queries until rewritten; no bulk backfill). Tests: new cases in
`server/tests/file-adapter/test_metadata_store.py` covering hash-on-write,
hash-filtered reads for a fresh upload, and the legacy-row exclusion gap.
Full `server/tests/file-adapter/` suite passes (one pre-existing, unrelated
failure in `test_file_types_full_pipeline.py::test_html_file_full_pipeline`
reproduces identically on `main` before this change).

## Phase 3 — Broaden and unify the SSRF denylist ✅ DONE

**Why:** `_reject_cloud_metadata_host()` only blocks the metadata range for
one endpoint (`POST /mcp/test-connection`); a saved MCP server config
(`PUT /admin/mcp/servers/{name}` or equivalent) has no equivalent check, so
an admin (or a compromised `config.manage` token) can point a *persisted*
server at the metadata address just as easily as the one-off probe — the
probe fix didn't close the config-write path.

**Changes**

- Extract the existing `_reject_cloud_metadata_host()` logic (IP-literal
  normalization, DNS resolution, IPv4-mapped IPv6 unwrapping) into a shared
  helper usable from both the probe endpoint and the config-write validators
  in `_yaml_config.py`/`mcp.py`.
- Make the denylist configurable (`security.ssrf_denylist: ["169.254.0.0/16"]`
  by default) rather than hardcoding just the metadata range, so an operator
  who wants to also block RFC1918/loopback for their deployment can opt in
  without a code change — many deployments legitimately point MCP servers at
  private-network hosts, so RFC1918/loopback stay **allowed by default**,
  matching the existing design note in the current code.
- Apply the shared check to the saved-config write path as well as the
  probe, so both surfaces enforce the same (configurable) policy.

**Tests**

- Both the probe and the saved-config write path reject a metadata-range
  literal, decimal/hex-encoded form, and a DNS name resolving to the
  metadata range.
- With an operator-configured broader denylist, a private-network literal is
  rejected on both surfaces; with the default config, it's still allowed
  (no regression for legitimate internal-MCP-server deployments).

**Exit gate:** one shared implementation backs both surfaces; existing
`test_admin_mcp_connection.py` and any MCP-config-write tests pass with the
default (metadata-only) denylist.

**Status: shipped.** `_reject_cloud_metadata_host()` was renamed to
`_reject_denylisted_host(url, denylist)` in `server/routes/admin/mcp.py` and
now checks a caller-supplied list of networks instead of the hardcoded
metadata range, still handling IP-literal forms, DNS resolution, and IPv4-
mapped IPv6 unwrapping exactly as before. A new `_parse_ssrf_denylist(config)`
reads `security.ssrf_denylist` (default: `["169.254.0.0/16"]` — RFC1918/
loopback stay allowed unless an operator opts in) and is called from all
three write/probe surfaces: `POST /admin/mcp/test-connection`,
`POST /admin/mcp/servers` (via `_validate_new_mcp_server`), and
`PATCH /admin/mcp/servers/{name}` (via `_validate_mcp_connection`), so a
saved config can no longer point at the metadata range just because the
one-off probe already checked something else. Documented in
`config/config.yaml` and `install/default-config/config.yaml` with the same
worked-example convention as `admin_rate_limiting`. `_parse_ssrf_denylist()`
always includes the metadata range alongside whatever is configured
(additive, not a replacement — a configured denylist can no longer
accidentally remove the default protection), and `_reject_denylisted_host()`
checks both an IPv6 address and its unwrapped IPv4-mapped form against the
denylist, so an IPv6-specific entry still matches a mapped literal and vice
versa. The create/update config-write endpoints now serialize their
read-validate-write section behind `_mcp_config_lock` (an `asyncio.Lock`),
since the SSRF check's DNS-resolution `await` sits between reading
`mcp_clients.yaml` and writing it back — without the lock, two concurrent
saves could interleave and one would silently overwrite the other. Tests:
`TestSsrfDenylist` class in
`server/tests/test_routes/test_admin_mcp_connection.py` (17 cases, including
the additive-denylist, IPv4-mapped/IPv6-specific matching, and concurrent-
create regressions); full file (152 cases) passes.

## Phase 4 — Push audit free-text search into the datastore ✅ DONE

**Why:** `GET /admin/audit/events?q=...` currently oversamples up to 5,000
rows per request and filters in Python — a DoS-adjacent, unindexed scan that
gets worse as the audit table grows, independent of Phase 1's rate limit
(which caps request *frequency*, not the cost of one request).

**Changes**

- Push `q` filtering into `query_admin_events()`/`query_audit_logs()` at the
  datastore layer for each backend (SQLite/Postgres `LIKE`/`ILIKE` on an
  indexed or trigram-indexed column set; Mongo `$text`/regex; Elasticsearch
  already supports this natively — verify its `q` path already does this
  and isn't part of the finding).
- Cap `offset` at a fixed maximum (e.g. 50,000) independent of `limit`,
  returning 422 rather than silently scanning further.

**Tests**

- `q` matches the same rows before/after for each backend (behavior parity).
- A large `offset` beyond the cap returns 422 instead of a large scan.
- Query plan/row-scan count (where inspectable, e.g. SQLite `EXPLAIN QUERY
  PLAN`) confirms the indexed path is used, not a full scan.

**Exit gate:** existing audit-search tests pass unmodified in behavior;
new tests confirm the indexed path and the offset cap.

**Status: shipped.** `q` filtering is now pushed into each storage
strategy's `query()` via a new `search` parameter (`AuditStorageStrategy`/
`AdminAuditStorageStrategy` base classes, `AuditService.query_audit_logs`/
`query_admin_events`), instead of `routes/admin/audit.py` oversampling up to
5,000 rows per source and substring-filtering in Python:
- **SQLite/Postgres**: a new generic `$or` operator in both services'
  `_convert_query_to_sql()` lets a `search` term become an OR'd `LIKE`/`ILIKE`
  (via the existing `$regex` operator) across each record type's text
  columns, ANDed with any other active filters.
- **MongoDB**: `search` becomes a native `$or`/`$regex` (`$options: "i"`)
  clause, passed straight through the existing query-passthrough `find_many`.
- **Elasticsearch**: admin events (all fields mapped `keyword`) use a
  case-insensitive `wildcard` query per field; chat records combine a
  `multi_match` over the analyzed `query`/`response` text fields with
  `wildcard` over the keyword fields — the plan's assumption that ES already
  pushed `q` down was wrong; neither query() had any free-text support
  before this phase.
- `offset` is capped at 50,000 via `Query(..., le=50000)` on
  `GET /admin/audit/events`, returning FastAPI's standard 422 beyond it.

The route's `search_text` field and Python substring filter are removed
entirely — `q` is now passed as `search=q` to both backend queries and no
longer touched after that. Tests: a new `test_search_pushes_down_to_an_indexed_or_query`
(verifies AND-with-filters, not just OR-across-fields), `test_or_operator` in
`test_sqlite_service.py` (the new generic `$or`), and route-level
`test_free_text_search_matches_chat_query_and_response_text`/
`test_offset_beyond_cap_returns_422`/`test_offset_at_cap_is_allowed`; the
existing `test_free_text_search` continues to pass against the datastore-level
implementation unmodified. Full `tests/test_services/`, `tests/test_routes/`,
`tests/test_middleware/`, and `tests/test_datasources/test_sqlite_service.py`
suites pass (1,646 passed). Postgres backend changes are structurally
identical to SQLite's but, per the Phase 2 note, untested against a live
Postgres in this sandbox — verified by AST/import checks only.

**Follow-up fixes (post-review, two rounds):** review of the above surfaced
four correctness/completeness gaps and one performance gap. All five are
fixed; the compressed-response gap took two attempts (see below) before
landing on a fully correct fix rather than a bounded-but-incomplete one.

- **Literal-substring semantics**: `search` is now matched as a literal
  string, not a pattern. SQLite/Postgres gained a new `$contains` operator
  (alongside the existing pattern-based `$regex`) that escapes `%`/`_`/`\`
  before building the `LIKE`/`ILIKE` predicate; MongoDB escapes the term with
  `re.escape()` before building `$regex` (previously a term like `[` was
  invalid regex syntax and silently matched nothing); Elasticsearch escapes
  Lucene wildcard metacharacters (`*`, `?`, `\`) before building a `wildcard`
  pattern.
- **ES text-field substring matching**: chat `query`/`response` search
  switched from `match` (tokenized, OR-across-words) to the same `wildcard`
  query used for keyword fields, so `search="refun"` matches `"refund"`
  again — `match` against an analyzed field tokenizes and would not. (A
  wildcard against an analyzed field matches within a single indexed token;
  a search term spanning a multi-word phrase with the original spacing is a
  known, accepted ES-specific gap, documented in code.)
- **Compressed-response search — corrected fix**: the first attempt added a
  second query bounded by `limit` that decompressed and substring-checked
  compressed rows — bounded cost, but incomplete: a compressed match sitting
  past the first `limit` compressed rows (by sort order) was silently missed,
  so results could differ from the old Python-filtering behavior. Replaced
  with `AuditRecord` always writing an additional `response_plain` column —
  an always-plaintext copy of `response`, populated **only** when the
  response is actually compressed (so it costs nothing in the default,
  uncompressed-responses configuration). `response_plain` is one of the
  fields `search` matches against (indexed exactly like any other search
  field — no decompression at query time, no secondary query, no row cap),
  and is stripped from every strategy's returned rows so it's never surfaced
  to the API. Schema: `audit_logs.response_plain` (SQLite/Postgres, additive
  migration, nullable) and an additive Elasticsearch mapping backfill;
  MongoDB needs no schema change. Pre-existing rows written before this
  column existed have no `response_plain` and are simply not response-text
  searchable until rewritten — the same documented, bounded gap pattern used
  for `uploaded_files.api_key_hash` in Phase 2 (no bulk backfill).
- **Unindexed scan (P1)**: `LIKE`/`ILIKE '%term%'` cannot use an ordinary
  B-tree index regardless of escaping. SQLite now maintains an FTS5 virtual
  table (trigram tokenizer, kept in sync via insert/update/delete triggers)
  over both `audit_logs` and `audit_admin_logs`; `search` resolves to
  matching row ids through it first (verified via `EXPLAIN QUERY PLAN` in
  tests: `SCAN ... VIRTUAL TABLE`, not a table scan). Postgres gained a
  best-effort `pg_trgm` GIN index per search column (no query-syntax change
  needed — the planner uses it automatically for `ILIKE '%term%'`).
  **Fallback now has a real performance safeguard, not just a disclosed
  trade-off**: when FTS5/the trigram tokenizer is unavailable, `search` is
  under 3 characters (below the tokenizer's minimum), or Postgres's
  `pg_trgm` extension couldn't be created (no superuser privilege, e.g. on a
  managed instance), `$contains`/`ILIKE` is no longer run against the whole
  table. Instead, a new `_bounded_contains_search()` (SQLite and Postgres,
  both chat and admin strategies) wraps it in `SELECT * FROM (SELECT * FROM
  <table> ORDER BY timestamp DESC LIMIT <cap>) recent WHERE ...`, using the
  pre-existing `idx_{table}_timestamp` index to bound the inner subquery to
  a fixed `_FALLBACK_SCAN_CAP` (20,000) most-recent rows — verified via
  `EXPLAIN QUERY PLAN` (`SCAN ... USING INDEX idx_..._timestamp`, not a full
  table scan) and via a test that shrinks the cap and confirms a match
  older than the window is genuinely not found, then found again once the
  cap is raised back above the dataset. This is now an explicit, enforced,
  and tested cost ceiling rather than an unbounded scan left as a
  documented-but-unmitigated risk: a match older than the cap's window is
  not found via this path, by design, instead of the query's cost scaling
  with total ledger size. MongoDB/Elasticsearch were left as-is: MongoDB has
  no equivalent trigram-style index for unanchored regex, and
  Elasticsearch's `wildcard` already runs against an inverted index's term
  dictionary rather than scanning stored documents, so neither has this
  plan's SQL-specific gap.

**Follow-up fixes, third round:** a further review found three remaining
gaps in the second round's fixes, all corrected:

- **[P1] Postgres short terms bypassed the cap**: `query()` routed to the
  indexed `$contains`/ILIKE path whenever `_trgm_available` was true,
  without checking the search term's length. pg_trgm [can't extract a
  trigram from (and therefore can't index) a term under 3
  characters](https://www.postgresql.org/docs/current/pgtrgm.html#PGTRGM-INDEX),
  so `search="ab"` silently ran an *uncapped* `ILIKE '%ab%'` against the
  whole table even with the index present — the exact unbounded-scan risk
  Phase 4 set out to close, just reached through a different gap. Both
  Postgres strategies now also check `len(search) >=
  _PG_TRGM_MIN_SEARCH_LENGTH` (3) before taking the indexed path, routing a
  shorter term through `_bounded_contains_search` instead, same as an
  unavailable index. Verified with mocked-client tests asserting which
  method (`_bounded_contains_search` vs `find_many`) gets called for a short
  vs. long term.
- **[P2] SQLite FTS corrupted pagination/filtering**: `_fts_search_ids()`
  applied `LIMIT <page size>` *inside* the FTS query, before the caller's
  other filters, sort order, and offset were ever applied — so a 3-match
  dataset with `limit=1` could return the oldest row instead of the newest,
  combining `search` with another filter could come back empty despite a
  real match, and a second page could come back empty despite more matches
  existing. Fixed by having `_fts_search_ids()` return *all* matching ids
  (up to a generous, independent `_FTS_CANDIDATE_CAP` of 50,000 — a safety
  valve against an extremely common term, not a page-size proxy) and letting
  the follow-up `find_many()` call — which already combines the id list with
  the caller's other filters and applies the real sort/limit/offset — do
  what it was already designed to do. Verified with a 3-row fixture
  reproducing the exact reported symptoms (page 1 returns the newest match,
  page 2 returns the next one, an added equality filter still ANDs
  correctly) on both the chat and admin tables.
- **[P2] Elasticsearch still couldn't match a multi-word substring**: even
  after switching from `match` to `wildcard`, `query`/`response`/
  `response_plain` were still mapped as analyzed `text` — a `wildcard`
  query's terms are the *indexed tokens*, so `*refund message*` can never
  match, since no single token contains a space
  ([Elasticsearch wildcard query docs](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-wildcard-query)).
  Added a `.raw` keyword multi-field (`ignore_above: 32766`, the standard ES
  keyword length ceiling) to all three fields via the same additive
  `_usage_mapping_properties()` mechanism already used for pre-existing
  indices, and `_SEARCH_TEXT_FIELDS` now targets `query.raw`/`response.raw`/
  `response_plain.raw` — a wildcard against `.raw` matches the whole stored
  value verbatim, including across word boundaries. Verified via a mapping
  assertion and a mocked-client test asserting the actual query sent to
  Elasticsearch references `response.raw`, not bare `response`.

Tests: 11 further new cases (6 SQLite/Postgres routing and pagination
regressions, 3 Elasticsearch mapping/query-construction, docstring/constant
updates elsewhere) on top of the 19 from the second round.

**Follow-up fixes, fourth round:** review of the third round found the
length/availability heuristics in both remaining fixes were themselves not
reliable enough to call the findings closed. Both corrected:

- **[P1] Postgres length check wasn't a real guarantee**: checking
  `len(search) >= 3` before trusting the pg_trgm-indexed path assumed a
  3+ character term always produces a usable index scan. It doesn't —
  whether Postgres's planner actually *uses* a GIN trigram index for a given
  `ILIKE '%term%'` is a cost-based decision driven by the pattern's
  selectivity, not just its length (a low-selectivity term like `"..."` or
  any pattern matching a large fraction of rows can make the planner prefer
  a full scan even with the index present and the term well over 3
  characters). No check performed in application code can reliably predict
  a query planner's cost-based choice. Rather than add a better heuristic,
  both Postgres strategies' `query()` now call `_bounded_contains_search()`
  for *every* search, unconditionally — the bounded-recent-window query is
  the only search path Postgres has left. `_ensure_trigram_indexes()` still
  runs (harmless, and may still help in scenarios where the planner can push
  the predicate into the bounded window), but `_trgm_available` is no longer
  read anywhere to choose a different, unbounded query shape. Verified with
  tests asserting `_bounded_contains_search` is called for every case in a
  short/long term × trgm-available/unavailable matrix, with `find_many()`
  (the old, no-longer-reachable unbounded path) never called.
- **[P2] SQLite FTS candidate cap still preceded filtering**: resolving
  matching ids via FTS with *any* `LIMIT` — whether set to the page size (the
  original bug) or to a larger safety cap (the second-round "fix") — still
  truncates the candidate set before the caller's other filters, sort order,
  and pagination are applied, reproducing the identical symptom class at
  whatever scale exceeds that cap. The two-step design (resolve ids, then a
  separate `find_many()` call) is what made a cap necessary in the first
  place. Replaced with a single query: `_fts_search()` now joins the FTS
  virtual table directly against the main table (`SELECT t.* FROM
  {table}_fts JOIN {table} t ON t.rowid = {table}_fts.rowid WHERE {table}_fts
  MATCH ? AND <other filters, reusing the same _convert_query_to_sql the rest
  of the codebase uses, qualified with the table alias to avoid ambiguity
  against the FTS table's identically-named columns> ORDER BY ... LIMIT ...
  OFFSET ...`), so FTS match resolution, filtering, ordering, and pagination
  all happen in one pass with no intermediate truncation point — there is no
  cap left to exceed. Verified by reproducing the exact three-row scenario
  from the original report (newest-first with `limit=1`, pagination to a
  second page, an added equality filter) on both tables, plus a new test
  paging through 15 matches in fixed-size pages and confirming every one is
  visited exactly once in the correct order — demonstrating the fix holds at
  a scale well past any cap a capped design could have used.

Tests: 5 further new/rewritten cases on top of the prior 30 (one Postgres
routing matrix per strategy, replacing the now-obsolete length-based routing
tests; one SQLite EXPLAIN QUERY PLAN update per table reflecting the joined
query shape; one exhaustive-pagination test). Full `tests/test_services/`,
`tests/test_routes/`, `tests/test_middleware/`, and
`tests/test_datasources/test_sqlite_service.py` suites pass (1,670 passed).
Postgres trigram indexing, the bounded-fallback SQL, and the
`response_plain`/schema/mapping changes remain unverified against a live
Postgres or Elasticsearch in this sandbox (AST/import checks and mocked
clients only, same limitation as elsewhere in this plan).

## Phase 5 — Pepper rotation tooling

**Why:** rotating `ORBIT_API_KEY_PEPPER` (recommended periodically, per
`docs/security/api-key-pepper-setup.md`) is currently an unguided,
all-at-once break: every existing key silently stops authenticating with no
warning, count, or dry-run.

**Changes**

- Add `orbit key rotate-pepper --dry-run` (CLI, `bin/orbit.py`): reports how
  many active keys exist and would need reissuing, without changing
  anything.
- Add a startup check: if `ORBIT_API_KEY_PEPPER` changes between restarts in
  a way `ApiKeyService` can detect (e.g. a stored fingerprint of the
  previously-active pepper, not the pepper itself), log a clear warning
  naming the number of keys that will fail to validate, rather than each key
  failing silently one at a time in production traffic.
- Document the rotation runbook (generate new keys first, distribute to
  clients, then rotate, or accept the break window) in
  `docs/security/api-key-pepper-setup.md`.

**Tests**

- `--dry-run` reports the correct count against a seeded set of keys and
  makes no writes.
- The startup pepper-change warning fires when the fingerprint differs and
  is silent on an unchanged pepper.

**Exit gate:** an operator can find out the blast radius of a pepper
rotation before performing it; existing `test_api_key_service*.py` suites
pass unmodified.

## Phase 6 — Housekeeping

Low-risk, low-value-individually items bundled together since none justify
their own phase:

- Rename `services/api_key_service.py`'s `hash_api_key()` to
  `hash_api_key_for_storage()` (or similar) to remove the naming collision
  with `utils/text_utils.py:hash_api_key()` (a different, unsalted
  algorithm used for chat-history ownership fingerprints) — purely a
  clarity fix, no behavior change.
- Stop calling `mask_api_key()` on record `_id` values in
  `routes/admin/api_keys.py` (`mask_api_key(api_key_id, ...)` where
  `api_key_id` is sometimes a non-secret Mongo/SQL id, not a key) — masking
  a non-secret value is harmless but misleading in logs.
- Split `system.manage` into a read (`system.read`) vs. destructive
  (`system.control`) permission for `lifecycle.py`'s shutdown/restart/pause
  vs. `config.py`'s read-only `/admin/info`, if finer-grained admin roles
  become a goal (`docs/authentication.md` tracks the broader RBAC role
  story — cross-reference there rather than duplicating).

**Tests:** existing test suites pass unmodified (pure rename/permission-
split, no behavior change to any currently-passing test given the renamed
symbol is updated at every call site).

**Exit gate:** `grep -rn "hash_api_key" server/` shows exactly one
definition per module with no ambiguity; `ruff check` clean.

## Out of scope for this plan

- **Full multi-tenant admin scoping** (per-adapter/per-owner API-key
  permissions) — noted in the gaps table as accepted for a single-tenant
  deployment; would need a broader RBAC redesign tracked separately if it
  becomes a real requirement.
- **Re-encrypting/backfilling every legacy `uploaded_files.api_key` row** —
  Phase 2 only changes new writes; a bulk backfill (if ever needed) is a
  separate, explicitly-scoped follow-up given it touches user file metadata
  at rest.
- **Replacing the in-memory rate limiter with a distributed one** for
  multi-worker/multi-host deployments — the existing `RateLimitMiddleware`
  already supports a cache-backed (Redis) mode; Phase 1 reuses whichever
  backend is already configured rather than introducing a new one.
