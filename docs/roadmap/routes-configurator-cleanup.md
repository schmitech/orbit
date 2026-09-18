# Route Configurator Cleanup — Implementation Plan

## Summary

`server/routes/routes_configurator.py` accumulated duplication and indirection
that a `/simplify` pass (reuse, simplification, efficiency, altitude review)
partially addressed in place — collapsing the lazy service-dependency closures
and the optional-router registration blocks. The remaining findings were
skipped from that pass because each requires a cross-cutting or
behavior-adjacent change wider than a single-file cleanup diff. This plan
picks those up as a phased, standalone change.

Out of scope (already fixed, not part of this plan): the four
lazy-init-on-`app.state` service dependencies (health, thread, feedback,
autocomplete) and the five optional-router `try/except` blocks in
`_include_admin_routes`.

## Phase 1 — Consolidate API key resolution (bearer-fallback opt-in only) — COMPLETE

Implemented: `resolve_api_key(request, config, allow_bearer_fallback)` added to
`routes/auth_helpers.py`; `RouteConfigurator._resolve_api_key` and the inline
extraction in `get_api_key` now delegate to it with the same bearer-fallback
condition each enforced before. `auth_dependencies.permission_or_api_key`,
`file_routes.py`, and `discovery_routes.py` were left unmigrated per the
"leave unchanged" option below — their required/optional `X-API-Key`-only
`Header(...)` contracts are untouched. Covered by
`server/tests/test_routes/test_resolve_api_key.py`; full `test_routes/` suite
(378 tests) passes unchanged.

**Problem.** `_resolve_api_key` (routes_configurator.py) re-derives "X-API-Key
header, else `Authorization: Bearer`" and duplicates the equivalent inline
logic already living in `_create_api_key_validator.get_api_key`
(routes_configurator.py:370-375). The `Header(None, alias="X-API-Key")` /
`Header(..., alias="X-API-Key")` dependencies in `routes/auth_dependencies.py`
(`permission_or_api_key`), `routes/file_routes.py`, and
`routes/discovery_routes.py` look similar but are **not** equivalent: those
call sites only ever read `X-API-Key` and never fall back to
`Authorization: Bearer`. A shared resolver that always applies bearer
fallback would silently let `Authorization: Bearer <token>` be accepted as an
API key on routes that currently reject it — a behavior expansion, not a
cleanup.

**Change.**

- Add one shared resolver in `routes/auth_helpers.py` (which already owns
  `resolve_authenticated_user`/`resolve_authenticated_user_id`):
  `resolve_api_key(request, config, allow_bearer_fallback: bool = True) -> Optional[str]`.
- Replace `RouteConfigurator._resolve_api_key` and the inline extraction in
  `get_api_key` with calls to the shared helper (`allow_bearer_fallback=True`,
  further gated by strict-mode as today — see below). These are the only two
  call sites that currently support bearer fallback, so behavior there is
  unchanged.
- For `auth_dependencies.permission_or_api_key`, `file_routes.py`, and
  `discovery_routes.py`: either leave those `Header(alias="X-API-Key")`
  dependencies unchanged (no consolidation), or migrate them to the shared
  helper called explicitly with `allow_bearer_fallback=False`. Do not migrate
  a call site without confirming, with a test, that it still rejects a
  bearer-only request the same way it does today.
- Several `discovery_routes.py` endpoints use `Header(..., alias="X-API-Key")`
  (required, no default) — FastAPI rejects a request missing that header at
  dependency-validation time with a 422 and the header listed in the route's
  OpenAPI schema, before the handler body ever runs. `resolve_api_key`
  returns `Optional[str]`, so a naive migration to `x_api_key: Optional[str]
  = Depends(resolve_api_key)` would turn that into a handler-level check
  (e.g. raising 400/403 on `None`), silently changing the status code and
  dropping the header from the endpoint's OpenAPI contract. Any endpoint
  currently using the required (`...`) form must keep a required
  `Header(..., alias="X-API-Key")` parameter feeding into the resolver (or
  stay unmigrated) — the migration must preserve the 422/OpenAPI-required
  contract, not just the end result of "request without a key is rejected."
- Preserve strict-mode semantics: in `get_api_key`,
  `Authorization: Bearer` must still be withheld from API-key resolution when
  `auth.require_authenticated_user` is true — pass that flag into the shared
  helper rather than re-deriving it ad hoc per call site.

**Verify.** Existing auth/API-key tests continue to pass unmodified; add
unit tests for the shared helper covering: header present, bearer fallback
enabled vs. disabled, strict mode suppressing bearer fallback, and neither
present. Add a regression test per migrated non-bearer call site asserting a
request with only `Authorization: Bearer <token>` (no `X-API-Key`) is still
rejected exactly as before. For endpoints with a required `X-API-Key`
(`Header(...)`), add a test asserting a request with no `X-API-Key` header at
all still gets FastAPI's 422 dependency-validation response with the header
named in the OpenAPI schema — not a handler-level 400/403 — confirming the
migration preserved the required-header contract, not just the reject
outcome.

## Phase 2 — Extract the low-level session-ownership check only (or drop)

**Problem, corrected.** `_authorized_thread` and `authorize_feedback_session`
are not two copies of the same flow. The thread path
(routes_configurator.py:976-1032) authorizes primarily by comparing
`owner_api_key_hash` directly against the caller's key — it only calls
`chat_history_service.authorize_session` as a fallback for legacy threads
created before that hash existed. The feedback path
(routes_configurator.py:1072-1091) has no hash to compare and always
authorizes through `authorize_session`. The two also deliberately disagree on
status codes for a missing/failing `chat_history_service`: the thread path
treats it as **403** (fail-closed — a legacy thread carries no proof of
ownership of its own, so an unverifiable check is a denial), while the
feedback path treats it as **503** (the service being down is an
infrastructure fault, not evidence the caller lacks access). A shared helper
that owns end-to-end failure translation cannot reproduce both status
policies from one code path — collapsing them would have to pick one and
break the other's contract.

**Change (narrowed scope).** Do not extract a helper that owns error
translation. Instead, extract only the shared low-level primitive both paths
already call identically:

```python
async def _check_session_authorized(chat_history_service, session_id, api_key) -> bool:
    """Return whether api_key owns session_id, or raise on a lookup failure."""
    return await chat_history_service.authorize_session(session_id, api_key)
```

Each caller keeps its own `chat_history_service` availability check, its own
try/except around the call, and its own status-code mapping (403 for the
thread path's fail-closed legacy branch, 503 for feedback's
service-unavailable branch). This removes the one line of genuinely
duplicated logic (`await chat_history_service.authorize_session(...)`)
without merging incompatible error semantics.

**Alternative: drop this phase.** Given how little is actually shared once
the error-mapping difference is accounted for, this phase is low value
relative to Phase 1 and Phase 4. It is reasonable to skip it entirely and
leave `_authorized_thread` and `authorize_feedback_session` as independently
maintained functions.

**Verify (if implemented).** Existing thread and feedback authorization
tests pass unchanged — status codes (403 for thread-legacy-unverifiable, 503
for feedback-service-unavailable) must be identical before and after. No new
shared-helper test should assert a single status code for both callers.

## Phase 3 — Reduce the dependency dict-of-closures indirection

**Problem.** `_create_dependencies` (routes_configurator.py:103-117) builds a
flat `dict[str, Callable]` threaded through every `_configure_*_endpoint`
method as `dependencies['get_x']`. Nothing selects keys dynamically — it is a
string-keyed lookup layer with no behavioral purpose beyond what direct
attribute access would give.

**Change.**

- Replace the dict with named attributes set once in `configure_routes` (e.g.
  `self.get_chat_service = self._create_chat_service_dependency()`), and
  update each `_configure_*_endpoint` signature to receive `self` implicitly
  (already the case) instead of a `dependencies` parameter.
- This is a larger mechanical diff touching every route decorator in the
  file, so land it as its own PR, not bundled with Phases 1–2, to keep the
  diff reviewable and revertible independently.

**Verify.** No behavior change is intended — rely on existing route/contract
tests (chat, stop, autocomplete, health, threads, feedback endpoints) passing
unmodified. Diff review should confirm every `dependencies['get_x']` call
site was mechanically replaced with `self.get_x`, with no dropped or
reordered dependencies.

## Phase 4 — Streaming serialize/reparse round trip: defer, reframed as a pipeline refactor

**Problem, corrected.** `openai_stream_generator`
(routes_configurator.py:626-703) `json.loads`s each SSE chunk emitted by
`chat_service.process_chat_stream`. The original framing of this as "add a
structured event source and switch one call site to it" is wrong: there is
no structured dict sitting behind that SSE string one layer down.
`PipelineChatService.process_chat_stream`
(server/services/pipeline_chat_service.py:1008+) and the pipeline/
post-processing helpers it delegates to construct and `yield` SSE-formatted
strings directly (e.g.
`yield f"data: {json.dumps({'error': ..., 'done': True})}\n\n"`) at every
yield point throughout the method, not just at a final serialization step. A
`process_chat_stream_events` variant would either have to parse those same
strings itself (moving the cost from `routes_configurator.py` into a new
location, not removing it) or the entire pipeline streaming path would need
to be refactored to build and yield structured dicts, with SSE framing moved
to a thin wrapper at the edge (`process_chat_stream` becoming
`format_sse(process_chat_stream_events(...))`).

**Change.** Do not attempt this as a routes-layer cleanup. If pursued, scope
it as its own roadmap item: a pipeline-wide streaming-contract refactor
covering every yield point in `PipelineChatService.process_chat_stream` and
whatever pipeline steps/formatters feed it, converting them to yield
structured events with SSE-string construction pushed to one place at the
boundary. That is a materially larger change than anything else in this
document, with its own risk surface (every internal yield site, not just the
two route handlers that consume the output).

**Recommendation.** Defer. Do not schedule this phase until the pipeline
owner scopes the broader refactor separately; the per-chunk `json.loads` in
`openai_stream_generator` is a real but small hot-path cost (one parse per
streamed token/chunk) that does not justify restructuring the streaming
pipeline on its own.

## Assumptions

- No public API, request/response shape, or client-visible behavior changes
  in any phase — this is an internal-structure cleanup only.
- Phases are independent and can land in any order or be skipped
  individually. Phase 3 is the safest, mechanical, independently landable
  one. Phase 2 is optional/low-value as scoped and may be dropped. Phase 4
  is not scoped for execution here — it is deferred pending a separate
  pipeline-wide decision.
- Skipped items not carried into this plan (assessed as not worth a phase):
  the double `.strip()` in `_create_session_validator`, and folding the
  `api_key_service` availability guard into its dependency factory — both
  are trivial, low-value, and better left as-is per the original `/simplify`
  review.

## Known gaps

- Phase 1 touches authentication-adjacent code in three files beyond
  `routes_configurator.py` and, if any call site is migrated, changes what a
  request is allowed to authenticate with. It must get security review, not
  just a standard code review, and any migrated call site needs an explicit
  regression test proving bearer-only requests are still rejected exactly as
  before (see Phase 1 "Verify").
- Phase 2's value is marginal once the two callers' incompatible status-code
  policies are respected — treat "drop this phase" as the default unless a
  reviewer sees value the corrected write-up above doesn't capture.
- Phase 4 is not a routes-layer change. It requires
  `PipelineChatService.process_chat_stream` and its pipeline/post-processing
  helpers to be refactored to yield structured events instead of
  pre-formatted SSE strings at every yield point — a decision for whoever
  owns that streaming pipeline, tracked separately rather than scheduled
  here.
