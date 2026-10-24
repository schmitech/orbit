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

- [x] **Collapse `reload_adapters_async`/`reload_templates_async`.**
      `server/routes/admin/jobs.py` now has `run_admin_job_async(request,
      job_type, target, running_message, handler, failure_log_message)`,
      taking an async callable; both wrappers in `adapters.py` call it with
      their respective `async def` reload handler instead of each hand-rolling
      the create-job/await/map-exceptions-to-status sequence.
- [x] **Factor the reload-generation-propagation tail.**
      `_propagate_adapter_generation` now delegates to a new
      `_propagate_reload_generation(request, kind, action)`; `reload_adapters`
      and `reload_templates` call it directly with `"adapter_config"`/
      `"templates"` instead of re-inlining the `ORBIT_SUPERVISOR_PID`/
      `bump_generation`/`last_seen` sequence.
- [x] **api_keys.py `activate`/`deactivate` handlers.** Both routes now
      delegate to a shared `_set_api_key_active_state(api_key_id,
      api_key_service, active=bool)`; the two public endpoints, their
      docstrings, and response shapes are unchanged.
- [x] **Audit source queries.** Already fixed to run concurrently
      (`asyncio.gather`) as part of this session's cleanup — no further action,
      listed here only as a dependency note for Phase 2's shared-infra item
      below (both queries still hit different backends directly from the
      route; moving that concurrency into a service method is a Phase 2 item,
      not required now).

## Phase 2 — Shared-infrastructure generalization

These require adding or extending a shared helper/service method, then
updating multiple call sites together. Each is a single coherent change, but
touches more than one file and deserves its own PR + test pass.

- [x] **Spike: find genuinely shared primitives across the comment-preserving
      YAML editors before committing to one editor.** Findings — no code
      change made; this was explicitly scoped as investigation-only:
      - The one primitive genuinely shared across files — "find a `- name:`
        list entry's start/end line range by key" — is already factored out
        as `_find_adapter_block` (`_yaml_config.py`) and already reused by
        `mcp.py`'s `_remove_mcp_server` and by `create_mcp_server`'s block
        lookups. Nothing further to extract here.
      - `config.py`'s `_split_config_sections` solves a different problem at
        a different granularity (regex-matched top-level keys at column 0,
        whole-section replacement) and shares no logic with the list-entry
        finder — confirmed by reading both; not a duplication, as the
        original finding already suspected.
      - `mcp.py`'s field-patching helpers (`_patch_yaml_scalars`,
        `_find_block_header`, `_patch_yaml_map`, `_patch_yaml_auth`,
        `_patch_yaml_list`, `_last_key_line`) patch individual scalar/map/
        list fields *inside* an already-located entry. `_yaml_config.py` has
        no equivalent — it only ever replaces a whole entry — so there's
        nothing on the other side to unify these with.
      - Conclusion: the three files are not the same problem solved three
        times; they're one shared primitive (already shared) plus two
        genuinely different patching strategies. No further unification is
        warranted. The `ruamel.yaml` alternative wasn't evaluated, since
        there's no longer an unification decision it would be weighed
        against — revisit only if a fourth comment-preserving editor
        appears and the duplication becomes real.
- [x] **Deduplicate repeated adapters-directory scans.** Added
      `_scan_adapter_dir(adapters_dir)` (`_yaml_config.py`), parsing every
      `*.yaml` file once into `(path, content, parsed)` tuples.
      `_find_adapter_file`, `_find_skill_name_owner`, and
      `_find_adapter_referrers` now take an optional `scanned` param and reuse
      it instead of re-globbing/re-parsing when a caller passes one.
      `create_adapter`, `import_adapter`, and `delete_adapter` each scan the
      directory once and pass the result to both checks they need (existing-file
      + skill-owner, or file-lookup + referrers), instead of two independent
      scans per request. `reload_adapters_config`'s own end-to-end reload is
      unrelated to this (it reloads already-committed config, not a directory
      scan) and is left as-is.
- [x] **Offload blocking directory scans to a thread.** The consolidated
      `_scan_adapter_dir` call in each of the three hot paths above is now
      wrapped in `asyncio.to_thread(...)` — one offload per request instead of
      per duplicate scan.
- [x] **Push adapter-reference-field knowledge into the adapter/config layer.**
      Added `ADAPTER_REF_LIST_KEYS`/`ADAPTER_REF_SCALAR_KEYS`/
      `_adapter_reference_kinds`/`find_references(entries, name)` to
      `services/config/adapter_config_manager.py` (the adapter-config schema
      module). `adapters.py`'s `_find_adapter_referrers` now calls
      `find_references(parsed.get("adapters", []), name)` per scanned file
      instead of hand-maintaining the key lists and kind-detection logic
      itself; a new reference-style field is now a one-place schema change.
- [x] **Promote adapter capability checks out of the route layer.** Moved
      `_supports_template_reload`/`_supports_test_query` to
      `server/adapters/capabilities.py` as `supports_template_reload`/
      `supports_test_query`, sharing a new `_resolve_implementation_class`
      helper; `test_adapter_query`'s inline duplicate of the same isinstance
      check now calls `supports_test_query(adapter_instance=adapter)` too.
      Decision recorded here since it diverges from the original wording:
      **not** cached on `AdapterCapabilities`/computed at registration, after
      checking how the registry is actually populated — `register_from_config`
      only runs lazily, the first time `context_retrieval.py`'s pipeline step
      handles a chat request for that adapter (`inference/pipeline/steps/
      context_retrieval.py`). The admin `/adapters/capabilities` endpoint this
      code serves is specifically designed to answer for adapters that
      haven't been registered yet (it already branches on a cached vs.
      uncached instance) — tying it to the registry would mean either forcing
      registration as a side effect of a read endpoint, or still falling back
      to the from-config resolution path for every uncached adapter, which is
      most of what the registry would have saved. So: deduplicated as plain
      functions in the capabilities module, not folded into the
      registration-time-cached capability model. The Phase 3 "cache resolved
      adapter capability tuples" item is the right place to revisit caching,
      if the resolve-from-implementation-path cost (one `importlib.
      import_module` per uncached adapter per request) ever shows up as a
      real cost.
- [x] **Label API-key groups by targeted lookup, not full-collection scan.**
      `observability.py`'s `_label_api_key_groups` now splits the group keys
      present into `_id` candidates and masked-`key_suffix` candidates and
      runs two separate targeted queries (`{"active": True, "_id": {"$in":
      [...]}}` and `{"active": True, "key_suffix": {"$in": [...]}}}`), each
      fully paginated, instead of paging through the whole collection. Two
      queries rather than one `$or` of both: `MongoDBService.
      _convert_string_ids_to_objectid` only converts `_id` string candidates
      to ObjectId when `_id` is a top-level query key, not nested inside an
      `$or` list, so a single `$or` query silently failed to match any
      id-keyed group on MongoDB. Pagination matters because a suffix can
      match more active keys than there are suffix candidates. Both lookup
      maps — including the suffix collision list (`masked_to_names`,
      `ambiguous` flag) — are still built from the full matched result set,
      deduplicated by `_id` (a key present in both the id and suffix query
      results is counted once, not as a spurious second match), so collision
      handling is unchanged.

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
