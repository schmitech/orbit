# MCP Client Service Cleanup — Phased Plan

## Summary

A `/simplify` pass over `server/services/mcp_client_service.py` (reuse,
simplification, efficiency, altitude review) found several real but
lower-priority issues that were deliberately not applied inline because each
either touches a file outside `mcp_client_service.py`, changes a deliberately
built feature, or trades real complexity for a minor gain. This doc tracks
them as independent, phased follow-ups. Two related fixes (merging the
duplicated `session.initialize()` call in `_create_connection`, and
consolidating the `input_schema`/`inputSchema` and annotation snake/camel
shims into one `_compat_attr` helper) already shipped directly and are not
tracked here.

Phases 2 and 3 are independent of everything else and of each other. Phase 1
is complete (see below); Phase 4, if pursued, should call the Phase-1
`mask_api_key(..., show_both=True)` helper for header redaction rather than
reintroducing a separate masking implementation.

---

## Phase 1 — Move secret masking into `text_utils.mask_api_key` (✅ Complete)

**Shipped:** `mask_api_key()` gained a `show_both` mode reproducing
`_mask_secret`'s exact format, including the empty-string edge case
(masks to `""`, not `"None"` — a review pass caught this before it shipped
incorrectly). `_header_display_value` now calls
`mask_api_key(str(value), show_both=True)`; `_mask_secret` is deleted. Tests
added to `test_api_key_masking.py`'s `TestMaskApiKeyShowBoth` class. Non-string
header values are coerced to `str()` before masking. All `text_utils` and
`mcp_client_service` tests pass with no output-format change.

**Finding (reuse):** `_mask_secret` (lines ~695-703) reimplements secret
masking that `server/utils/text_utils.py`'s `mask_api_key(api_key,
show_last=..., num_chars=..., prefix=...)` already provides. The two produce
different output formats today (`mask_api_key` shows one boundary slice;
`_mask_secret` shows first+last 4 chars plus length, e.g.
`Bear...k123 (len=41)`), so this isn't a drop-in swap — it needs a small
extension to the shared helper first.

**Why deferred:** changing `text_utils.py`'s public API/output format could
affect other callers of `mask_api_key`; out of scope for a same-file cleanup
pass.

**Tasks:**
- [x] Add an optional mode to `mask_api_key` (e.g. `show_both=True` or a
      `style="boundary+length"` param) that reproduces `_mask_secret`'s
      `first4...last4 (len=N)` format without changing the default behavior
      for existing callers.
- [x] Add unit tests for the new mode in `text_utils`'s existing test file.
- [x] Replace `MCPClientManager._mask_secret` with a call to the extended
      `mask_api_key`, and delete `_mask_secret`.
- [x] Cover the same edge cases `_mask_secret` currently handles (and that
      the new `mask_api_key` mode must preserve):
      - value length ≤ 10 → fully masked (`"*" * len(value)`)
      - value length exactly 11 → first boundary case where the
        `first4...last4 (len=N)` form kicks in
      - empty string → masks to `""`, not `"None"` (caught and fixed in
        review — `show_both` now checks for `None` specifically rather
        than falling through the generic falsy-value fallback)
      - non-string header values reaching `_header_display_value` — coerced
        to `str()` before masking
- [x] Re-run `server/tests/` for both `text_utils` and
      `mcp_client_service` to confirm output format is unchanged for the
      HTTP debug-log path (`_header_display_value` / `_log_http_request`).

## Phase 2 — Encapsulate breaker "is this server retryable" checks (✅ Complete)

**Shipped:** `ServerConnectionPool.is_reachable()` and
`should_retry_discovery()` added per the exact contract below —
`should_retry_discovery()` reproduces the full `state != "closed" and not
is_open` expression, not just `not is_open`. All three call sites in
`mcp_client_service.py` (`is_reachable`, `_any_server_marked_failed`,
`_ensure_cache_populated`) now call the pool methods; no direct
`.breaker.state`/`.breaker.is_open` reads remain outside
`mcp_connection_pool.py` itself. `TestServerConnectionPoolReachability`
added to `test_mcp_client_service.py`, covering `closed`, `open` before/
after the recovery timeout, the `open`→`half_open` transition (and that
`is_reachable()` never triggers it), and both `half_open`→`closed` and
`half_open`→`open` transitions. Audit confirmed no other MCP-related
caller reads breaker internals directly; `cache_backends`' own unrelated
`CircuitBreaker` usage was left untouched.

**Finding (altitude):** breaker internals leak into `MCPClientManager` at
three call sites, each re-deriving retry/reachability semantics with
different nuance:
- `is_reachable` (`pool.breaker.state == "closed"`)
- `_any_server_marked_failed` (`p.breaker.state != "closed"`)
- `_ensure_cache_populated` (`breaker.state != "closed" and not
  breaker.is_open` — a third, more elaborate re-derivation distinguishing
  "open but recoverable" from "open and not yet eligible for retry")

**Why deferred:** the correct fix lives in `server/services/
mcp_connection_pool.py` (the `ServerConnectionPool`/breaker implementation),
outside the file the cleanup pass was scoped to.

**The breaker in play:** `ServerConnectionPool.breaker` is a
`services.cache_backends.base.CircuitBreaker` (shared with the cache-backend
code, not a private MCP class). Its relevant semantics:
- `state` is one of `"closed"`, `"open"`, `"half_open"`.
- `is_open` is **not** a pure getter — reading it while `state == "open"`
  and the recovery timeout has elapsed *mutates* `_state` to `"half_open"`
  and returns `False`. Reading `is_open` is itself a state transition.
- `record_success()` closes the breaker from any state;
  `record_failure()` reopens it once the failure threshold is hit.

**Exact contract for the two new methods:**
- `is_reachable()` → `self.breaker.state == "closed"`. Pure read, no
  mutation, matches today's `is_reachable` behavior exactly.
- `should_retry_discovery()` → **must reproduce the full current
  expression**, `self.breaker.state != "closed" and not
  self.breaker.is_open` — both conjuncts matter. `not self.breaker.is_open`
  alone is wrong: for a `closed` breaker, `is_open` is `False`, so
  `not is_open` is `True`, and a bare `not is_open` implementation would
  make `should_retry_discovery()` return `True` for every healthy server —
  causing `_ensure_cache_populated` to redial already-healthy servers on
  every cache check instead of skipping them (its current logic explicitly
  excludes `closed` via the first conjunct). Implement it as:
  ```python
  def should_retry_discovery(self) -> bool:
      return self.breaker.state != "closed" and not self.breaker.is_open
  ```
  The `state != "closed"` check must run first (or independently) so a
  `closed` breaker short-circuits to `False` without depending on
  `is_open`'s mutating side effect; the `not is_open` conjunct is what
  actually triggers the `open` → `half_open` transition (and returns
  `True`) once the recovery timeout has elapsed for a non-closed breaker.

**Tasks:**
- [x] In `mcp_connection_pool.py`, add `ServerConnectionPool.is_reachable()`
      and `ServerConnectionPool.should_retry_discovery()` per the contract
      above, as the single source of truth for these two questions.
- [x] Update `mcp_client_service.py`'s three call sites
      (`is_reachable`, `_any_server_marked_failed`,
      `_ensure_cache_populated`) to call the new pool methods instead of
      inspecting `.breaker.state`/`.breaker.is_open` directly.
- [x] Add/extend `mcp_connection_pool` unit tests covering the full state
      machine both methods must report correctly: `closed` →
      (failure) → `open` → (time elapses, `should_retry_discovery()`
      called) → `half_open` → (success) → `closed`, and separately
      `half_open` → (failure) → `open` again. Assert `is_reachable()`
      stays `False` for both `open` and `half_open`, and that calling
      `is_reachable()` itself never mutates `half_open`/`open` state
      (only `should_retry_discovery()` may).
- [x] Confirm no other **MCP-related** caller reads `.breaker.state`/
      `.breaker.is_open` directly and migrate any found. Scope the audit to
      `server/services/mcp_client_service.py`,
      `server/services/mcp_connection_pool.py`, and their tests —
      `CircuitBreaker` is shared with `server/services/cache_backends/`,
      so a bare grep for `breaker.state`/`.is_open` across `server/` will
      also surface unrelated cache-backend usage; leave that alone.

## Phase 3 — Cache the flattened tool list and per-tool schema lookup

**Finding (efficiency):**
- `get_all_tools` (lines ~279-293) rebuilds the merged tool list from
  `_tools_cache` on every call, even though the cache only changes on
  discovery/refresh/`update_server`. Likely called once per chat request.
- `_validate_arguments` (lines ~347-363) does a linear scan over a server's
  cached tool list on every `call_tool` invocation, repeated per iteration
  in a multi-tool-call loop.

**Why deferred:** tool lists per server are typically small, so the
absolute cost today is minor; added invalidation logic is real complexity
for a currently-unmeasured gain. Revisit only if profiling or a
larger-toolset deployment shows this on a hot path.

**Tasks:**
- [ ] Add a lightweight benchmark or logging-based measurement of
      `get_all_tools`/`_validate_arguments` cost under a realistic tool
      count (e.g. 5 servers × 20 tools) to confirm whether this is worth
      doing before implementing.
- [ ] If justified: build `namespaced_name -> tool_schema` dict alongside
      `_tools_cache` in `_discover_server`, invalidated in the same places
      `_tools_cache` itself is invalidated (`_discover_server`,
      `refresh_tool_cache`, `update_server`). Use it in
      `_validate_arguments` for O(1) lookup.
- [ ] If justified: cache the flattened `get_all_tools` result. Callers pass
      `allowed_servers` as a `list[str]`, which is unhashable and mutable —
      do **not** use it directly as a cache key. Either:
      - normalize it to `tuple(sorted(allowed_servers))` (plus
        `opportunistic_only`) before using it as a key, accepting one
        small allocation per call in exchange for avoiding a rebuild of
        the full per-server tool dicts, or
      - simpler and preferred: cache only the single unfiltered flattened
        list (all servers, no `opportunistic_only` filter), and have
        `get_all_tools` filter *that* cached list by `allowed_servers`/
        `opportunistic_only` on each call. This keeps the expensive part
        (flattening every server's tool dicts) cached while keeping the
        filter — which is cheap relative to the flatten — uncached and
        key-free.
- [ ] **Concurrency requirement:** `get_all_tools()` can run concurrently
      with `refresh_tool_cache()` / `update_server()` (no request-level
      serialization exists between them today beyond `_cache_lock`, which
      `get_all_tools` doesn't currently take). Whatever caching is added
      must ensure a reader never observes a partially-rebuilt flattened
      list or a flattened list mixing tool dicts from before and after a
      refresh:
      - Build the new flattened list as one complete new object, then
        publish it with a single atomic reference assignment (Python
        attribute assignment is atomic under the GIL) — never mutate a
        cached list/dict in place while a reader might be iterating it.
      - Invalidate/rebuild the flattened cache inside the same
        `_cache_lock` critical sections that already touch `_tools_cache`
        in `_discover_server`, `refresh_tool_cache`, and `update_server`,
        so a "flatten" never reads `_tools_cache` mid-mutation.
      - `get_all_tools()` itself must also take `_cache_lock` when it
        snapshots/reads the flattened cache (or the raw `_tools_cache` if
        no flattened cache exists yet). Atomic publication of the new
        object prevents a reader from seeing a *partially built* object,
        but without the reader also holding the lock, a refresh happening
        mid-iteration can still swap `_tools_cache` out from under a
        `get_all_tools()` call that reads server-by-server, producing a
        result mixing pre- and post-refresh servers. Take the lock for the
        read (it's already held for writes), or — if lock contention on
        every `get_all_tools()` call is a concern — read the flattened
        cache's object reference exactly once into a local variable under
        the lock and iterate that local copy afterward, never touching the
        live attribute again during the call.
      - Add a test that starts `get_all_tools()` concurrently with
        `refresh_tool_cache()` (e.g. via `asyncio.gather`) and asserts the
        result is always either the fully-old or fully-new tool set, never
        a mix.
- [ ] Add tests asserting cache invalidation on `refresh_tool_cache` and
      `update_server` (stale schema/tool-list must never be served after a
      server's tools change).

## Phase 4 — Trim the HTTP debug-logging machinery (optional, low priority)

**Finding (simplification):** `_mask_secret`, `_header_display_value`,
`_build_curl_repro`, `_log_http_request`, `_log_http_response` (~100 lines)
exist to produce two log lines (DEBUG request, WARNING non-2xx response) for
the HTTP transport. The curl-repro generator in particular (header escaping,
body truncation, shell quoting) is a lot of machinery for a debug
convenience used in exactly one place.

**Why deferred:** this was a deliberately built diagnostic feature (see the
file's own docstrings — it exists specifically to let admins diff a working
`curl` call against what ORBIT actually sent for hard-to-diagnose 401/500
failures), not incidental complexity. Trimming it removes real
functionality, so it should be a deliberate decision, not a drive-by
simplification.

**Tasks (only if the team decides the curl-repro feature isn't worth
keeping):**
- [ ] Confirm with whoever added the curl-repro feature (or check its
      originating PR/issue) whether it has been used in practice for a
      real MCP HTTP debugging incident.
- [ ] If not valuable: replace `_build_curl_repro` + `_log_http_request` +
      `_log_http_response` with a single `_log_http_exchange(server_name,
      request, response)` that logs method/URL/status/truncated body
      without reconstructing a shell command. Keep `_mask_secret`/
      `_header_display_value` (or their Phase 1 replacement) for header
      redaction only.
- [ ] If valuable: close this phase as "keep as-is" and remove it from
      this roadmap doc.

## Assumptions

- None of these phases change `MCPClientManager`'s public API
  (`get_mcp_client_manager`, `reload_mcp_client_manager`,
  `get_current_mcp_client_manager`, or any method on `MCPClientManager`
  itself) — all are internal implementation changes.
- Phases 1-3 are pure follow-ups with no behavior change for a correctly
  functioning MCP server; Phase 4 is the only phase that could remove
  observable behavior (the curl-repro debug line) and needs an explicit
  decision first.
