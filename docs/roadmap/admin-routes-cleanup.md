# Admin Routes Cleanup — Phased Follow-ups

## Summary

A `/simplify` pass over `server/routes/admin/` applied the safe, localized
fixes directly (pagination-clamp dedup, config-path helper, adapter-block
locator helper, a few sequential-await-to-gather efficiency fixes — see git
history for `server/routes/admin/_shared.py`, `_yaml_config.py`, `adapters.py`,
`api_keys.py`, `audit.py`, `config.py`, `prompts.py`, `skills.py`). The items
below were flagged by that review but deliberately **not** applied, because
each touches shared services or changes behavior/API surface beyond a
same-session cleanup pass. This doc phases them so they can be picked up
independently, ordered by value vs. risk.

Reference: review findings were produced by four parallel passes (reuse,
simplification, efficiency, altitude) over `server/routes/admin/`
(`adapters.py` and `mcp.py` are the largest files, ~1500 lines each, and the
source of most of this list).

---

## Phase 1 — Low-risk, single-file extractions

Safe to do without touching shared services; each is contained to the route
file(s) named. Good first bites.

- [ ] **Collapse `reload_adapters_async`/`reload_templates_async`.**
      `server/routes/admin/adapters.py` (~1289-1320, ~1412-1443) — identical
      "create job → await an async reload handler inside `asyncio.create_task`
      → map `HTTPException`/`Exception` to failed status" boilerplate, differing
      only in job type/message strings and which handler to await
      (`reload_adapters`/`reload_templates`, both `async def`). Extract one
      `_run_admin_job_async(request, job_type, running_message, handler)` that
      accepts an async callable, awaits it, and maps the same two exception
      branches to job status — preserving each endpoint's existing response
      shape (`result.model_dump()` when available) and failure behavior
      exactly, just de-duplicating the wrapper around it.
- [ ] **Factor the reload-generation-propagation tail.**
      `adapters.py` already has `_propagate_adapter_generation` (~line 453) for
      this exact pattern, but `reload_adapters` (~1245-1256) and
      `reload_templates` (~1374-1383) each re-inline the raw
      `os.environ.get("ORBIT_SUPERVISOR_PID")` / `adapter_reload_state.bump_generation`
      / `last_seen` sequence instead of reusing it. Extend the existing helper
      to take a `kind` key and call it from both reload paths.
- [ ] **api_keys.py `activate`/`deactivate` handlers.** ~404-431 — structurally
      identical (`{action}_api_key_by_id`, same 404/log/response shape).
      Collapse into one parameterized internal handler if it doesn't complicate
      the route signatures.
- [ ] **Audit source queries.** Already fixed to run concurrently
      (`asyncio.gather`) as part of this session's cleanup — no further action,
      listed here only as a dependency note for Phase 2's shared-infra item
      below (both queries still hit different backends directly from the
      route; moving that concurrency into a service method is a Phase 2 item,
      not required now).

## Phase 2 — Shared-infrastructure generalization

These require adding or extending a shared helper/service method, then
updating multiple call sites together. Each is a single coherent change, but
touches more than one file and deserves its own PR + test pass.

- [ ] **Spike: find genuinely shared primitives across the comment-preserving
      YAML editors before committing to one editor.** `_yaml_config.py`
      (`_find_adapter_block` — locates a `- name:` list entry and replaces the
      whole block), `mcp.py` (~958-1258: `_last_key_line`,
      `_patch_yaml_scalars`, `_find_block_header`, `_patch_yaml_map`,
      `_patch_yaml_auth`, `_patch_yaml_list`, `_insert_mcp_server`,
      `_remove_mcp_server` — patches individual scalar/map/list *fields inside*
      a server entry, in place), and `config.py`
      (`_split_config_sections`/`_load_config_sections` — replaces an entire
      top-level config section wholesale) are not the same problem solved
      three times: `config.py` operates at whole-section granularity,
      `mcp.py` at field granularity within an entry, `_yaml_config.py` at
      whole-entry granularity. Don't assume one shared editor covers all
      three — first spike what's actually common (e.g. "find a block's start/
      end line range by key", "re-indent a replacement block to match") vs.
      what's genuinely field-patching-specific to `mcp.py`, and only then
      decide whether a shared primitive is worth extracting, and for which
      subset. Any extraction still needs round-trip tests against real
      `config/adapters/*.yaml` and `config/mcp_clients.yaml` content, since
      comment-preservation must stay byte-identical.
      - Alternative considered: replace the hand-rolled line-splicing with
        `ruamel.yaml` (comment-preserving by design) instead of a bespoke
        unification. Worth comparing output fidelity against the current
        approach as part of the same spike.
- [ ] **Deduplicate repeated adapters-directory scans.** `_find_adapter_file`
      (`_yaml_config.py`), `_find_adapter_referrers`, and
      `_find_skill_name_owner` (`adapters.py`) each independently glob and
      `yaml.safe_load` every file in `adapters_dir`. A single
      `create`/`delete`/`import` request re-reads and re-parses the whole
      directory 2-3 times. Parse once into `(path, content, parsed)` tuples and
      pass that into the referrer/skill-owner/file-lookup checks. Compounds
      with the next item (adapter config is also reloaded 3+ times end to end
      via `reload_adapters_config`) — worth scoping both together since
      they share the same request paths (`create_adapter`, `import_adapter`,
      `delete_adapter`).
- [ ] **Offload blocking directory scans to a thread.** The same
      scan-and-parse helpers above use synchronous `Path.read_text()`/
      `yaml.safe_load()` inside `async def` route handlers with no
      `asyncio.to_thread`. Blocks the event loop on every adapter CRUD request
      when the adapters directory is large. Wrap in `asyncio.to_thread(...)`
      once the scan is consolidated (previous item) rather than wrapping each
      of the three duplicate call sites separately.
- [ ] **Push adapter-reference-field knowledge into the adapter/config layer.**
      `adapters.py`'s `_adapter_reference_kinds`/`_ADAPTER_REF_LIST_KEYS`/
      `_ADAPTER_REF_SCALAR_KEYS` (~1006-1024) hand-maintain which config keys
      let one adapter reference another, purely so `delete_adapter` can warn
      about referrers. Expose `find_references(adapters_config, name)` from the
      adapter manager/config schema module instead, so a new reference-style
      field is a schema change, not a second place in the route file to
      remember to update.
- [ ] **Promote adapter capability checks out of the route layer.**
      `_supports_template_reload`/`_supports_test_query` (`adapters.py`
      ~44-91) reach into `retrievers.base.*` with `isinstance`/`hasattr`
      checks, duplicated again inline in `test_adapter_query` (~line 1475).
      Add `supports_template_reload`/`supports_test_query` as declared
      capabilities in `AdapterCapabilities`/`AdapterCapabilityRegistry`
      (`server/adapters/capabilities.py`), computed once at registration, and
      have routes query capabilities instead of re-deriving them from class
      hierarchy in multiple places.
- [ ] **Label API-key groups by targeted lookup, not full-collection scan.**
      `observability.py`'s `_label_api_key_groups` (~35-49) pages through the
      entire `active: True` api_keys collection to build both an id→name map
      *and* a masked-suffix→names map (the latter preserving collision
      detection — the same suffix can belong to multiple keys, so a group can
      resolve to several candidate names), even though it only needs to label
      the ≤100 group keys actually present. A group's `key` is either an
      exact `_id` or a masked `key_suffix`, so a plain
      `_id: {"$in": [...]}` query alone would correctly label id-keyed groups
      but silently drop labels for every suffix-keyed group. Narrow the scan
      to a targeted query that still returns both the ids and the suffixes
      present in `groups` (e.g. `{"$or": [{"_id": {"$in": [...]}}, {"key_suffix":
      {"$in": [...]}}]}`), and keep building both lookup maps — including the
      suffix collision list — from that narrowed result set rather than
      dropping the collision handling.

## Phase 3 — Opportunistic / low-urgency

Smaller wins, fine to fold into unrelated future PRs touching the same files
rather than scheduling dedicated work.

- [ ] **MCP OAuth status batching.** `mcp.py`'s `list_mcp_servers` (~663-769)
      awaits `_compute_oauth_status` sequentially per HTTP-transport server;
      each call does its own file-backed token/fingerprint/error reads.
      `asyncio.gather` across servers before building the response list.
- [ ] **MCP config write lock serializes unrelated concurrent saves.**
      `_mcp_config_lock` (mcp.py ~line 203) serializes the whole
      read-validate-write critical section across *all* concurrent requests,
      even when they touch different servers. Only worth revisiting if MCP
      admin writes become frequent/bulk (e.g. an import flow) — no action
      needed at current usage levels.
- [ ] **Cache resolved adapter capability tuples.** Related to the Phase 2
      capability-registry item above — once capabilities are computed at
      registration time this becomes moot; listed separately in case the
      registry work is deferred and a cheaper interim fix (cache
      `(supports_template_reload, supports_test_query)` per `implementation`
      path) is wanted first.
- [ ] **`config.py` section load/parse redundancy within a single write.**
      `update_config_section` effectively parses the config file 3 times in
      one call (`_split_config_sections`'s regex pass + two `yaml.safe_load`
      calls on overlapping content). Only matters if the frontend's
      section-by-section editor calls this in a tight loop; otherwise
      acceptable for a single admin write.

---

## Out of scope / accepted as-is

Noted by the review and explicitly judged not worth fixing:

- `jobs.py`'s in-memory job store is bounded to 100 entries — no leak.
- `logs.py`'s `tail_log_file`/`list_log_files` use blocking file I/O but are
  plain `def` routes, so FastAPI already runs them in its threadpool.
- `observability.py`/`audit.py` service-availability checks look similar to
  `check_service_availability` (`routes/auth_helpers.py`) but encode different
  enablement semantics (audit admin/chat toggles vs. a plain None-check) —
  treating them as duplication would be a false positive.
