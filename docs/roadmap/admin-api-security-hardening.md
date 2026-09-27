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

## Phase 1 — Rate-limit sensitive admin actions independent of the general toggle

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

## Phase 2 — Hash the raw key in `uploaded_files`

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

## Phase 3 — Broaden and unify the SSRF denylist

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

## Phase 4 — Push audit free-text search into the datastore

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
