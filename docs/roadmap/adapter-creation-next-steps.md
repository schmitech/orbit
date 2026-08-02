# Adapter Creation — Next Implementation Steps

## Summary

The admin panel can now create adapters from the SDK spec registry: `GET
/admin/adapters/specs` drives a generated form, `POST /admin/adapters/preview`
renders the YAML, and `POST /admin/adapters` writes `config/adapters/<name>.yaml`,
registers it in `config/adapters.yaml`, and hot-reloads it. The path is fully
deterministic — no LLM calls are involved in creating an adapter.

That closes the *create* half of the SDK roadmap's Phase 3. The lifecycle is still
one-directional: an adapter can be created and edited, but not removed, exported, or
moved between environments from the panel. This document describes the work to close
that gap, ordered by value.

Reference: `server/adapter_sdk/ROADMAP.md` (SDK-side phases),
`server/adapter_sdk/README.md` (current REST surface).

---

## 1. Adapter deletion (the main gap)

**Goal:** `DELETE /admin/adapters/{name}` — remove the adapter's YAML block, drop its
import line, and evict it from the running server.

**The runtime side is already solved.** `AdapterReloader.reload_all_adapters`
(`server/services/reload/adapter_reloader.py:222-238`) has a complete removal branch:
for any adapter present in `config_manager` but absent from the new config it clears
dependencies, removes it from the adapter cache, removes it from `config_manager`, and
invalidates the autocomplete cache. So deletion needs no new eviction machinery — it
needs the *file* work plus a full reload.

**This is the one asymmetry to design around:** creation hot-applies with
`reload_adapter_configs(new_config, name)` (scoped, cheap), but deletion **cannot** use
the scoped path. `reload_single_adapter` (`:77-78`) raises
`ValueError("Adapter '<name>' not found in configuration file")` when the name is gone
— which is exactly the post-delete state. Deletion must call
`reload_adapter_configs(new_config)` with `adapter_name=None`. That is heavier (it
re-diffs every adapter) but it is the only path that runs the removal branch.

**Tasks:**

- [ ] `writer.unregister_import(import_path, adapters_yaml)` — the inverse of
      `register_import` (`server/adapter_sdk/writer.py:53`). Same text-insertion
      discipline: delete the matching line via the existing `is_registered` regex,
      preserving surrounding comments, then `_atomic_write`. Idempotent, returns
      whether a line was removed.
- [ ] `writer.delete_adapter(name, *, adapters_dir, adapters_yaml, unregister=True)` —
      `validate_adapter_name`, unlink the file, unregister. Raise `FileNotFoundError`
      when absent.
- [ ] Route `DELETE /admin/adapters/{name}`, gated on `adapters_auth`, mirroring the
      create route's structure in `server/routes/admin_routes.py`.
- [ ] **Multi-adapter files must be rejected, not silently mangled.** The writer is
      one-file-per-adapter, but `config/adapters/` ships files declaring several
      adapters (`web-search-providers.yaml`, `multimodal.yaml`). Use the existing
      `_find_adapter_file` + `_find_adapter_block` helpers: if the file holds more than
      one adapter, either splice out just that block and keep the file (preferred — the
      helpers already do this for the PUT/toggle routes) or return `409` telling the
      operator to edit the file directly. Never unlink a file that owns other adapters.
- [ ] **Referential integrity check before deleting.** An adapter name can be
      referenced by an API key (`adapter_name` on the key record) and by other adapters'
      `available_skills` / `auto_routable_skills` lists. Deleting one out from under a
      live API key breaks that key's requests at runtime with no warning. Look for
      references first and return `409` with the referrers listed, or require an
      explicit `force: true`.
- [ ] Frontend: a Delete button in the Adapters detail panel, using the existing
      `requireTypedConfirmation` helper (`server/admin/admin_panel.js:878`) — deletion
      is destructive and irreversible from the panel, so type-to-confirm matches how
      other destructive admin actions behave. On success clear `selectedAdapterEntry`,
      re-render, and surface `reload_summary.removed_names`.
- [ ] Tests: file + import line both gone; multi-adapter file keeps its siblings;
      referenced adapter returns 409; deleting a non-existent adapter returns 404;
      permission guard.

## 2. Export and import

**Goal:** move an adapter between environments without hand-copying YAML.

- [ ] `GET /admin/adapters/{name}/export` — the adapter's YAML block, served as a file
      download. Largely a thin wrapper over the existing
      `GET /admin/adapters/config/entry/{name}`.
- [ ] `POST /admin/adapters/import` — accept a YAML document, run it through
      `validate_yaml_text`, apply the same collision rules as create (target filename
      waivable by `overwrite`; a name owned by a *different* file never waivable), then
      write + register + reload.
- [ ] Decide whether import accepts multi-adapter bundles. If yes, the writer needs a
      multi-entry path; if no, reject with a clear message. Do not let a bundle write
      partially and leave `adapters.yaml` half-registered.
- [ ] Secrets: exported YAML contains `${ENV_VAR}` references, not values — verify this
      holds for every spec before advertising export as safe to share.

## 3. Round-trip editing (YAML → answers)

Today the create form is write-only: once an adapter exists, the only way to change it
is raw YAML in the Ace editor. A "Edit in form" action would need to parse an existing
adapter back into an `answers` dict.

- [ ] Spec detection: given an adapter entry, identify which `AdapterSpec` produced it
      (match on the fixed `type`/`datasource`/`adapter`/`implementation` tuple, plus
      the variant field). Adapters not produced by a spec — hand-written or intent
      adapters — must degrade to the YAML editor rather than guessing.
- [ ] Answer extraction per question field, then re-render and diff against the file to
      confirm the round trip is lossless before offering it. If the re-render doesn't
      match, the form would silently drop hand-edits (comments, extra keys) — refuse
      rather than lose them.
- [ ] Consider `ruamel.yaml` for comment-preserving round trips.

## 4. Hardening the existing create path

Small, independent items — none blocking, all noted during implementation.

- [ ] **Wire up `validate_providers`.** `server/adapter_sdk/validator.py` exposes
      `validate_providers(entry, enabled_providers)` but nothing calls it. The create
      route has `request.app.state.config` in hand and can pass the set of enabled
      inference providers, catching "adapter references a provider that isn't
      configured" at creation instead of at first request.
- [ ] **Skill-name collisions.** Two adapters can declare the same `skill_name`, which
      makes skill routing ambiguous. Check against existing adapters at create time and
      warn (or 409).
- [ ] **Concurrency.** `adapters.yaml` writes are atomic per-write but unlocked, so two
      simultaneous creates can lose an import line. Acceptable for an admin panel today;
      revisit if adapter creation ever becomes automated.
- [ ] **Multi-worker propagation.** Under `performance.workers > 1`, the create route's
      hot reload only applies in the worker that served the request — the same gap
      documented for MCP in `docs/roadmap/mcp-hot-reload-multi-worker.md`. The fix is
      shared: `server/services/adapter_reload_state.py` already has a generation-bump
      mechanism for adapters; confirm the create/delete paths bump it.
- [ ] **Pydantic request models.** The create endpoints take plain `dict` bodies to
      match the neighbouring adapter routes. Typed models in
      `server/models/schema.py` would give free 422s and OpenAPI docs.

## 5. Intent × datasource families (SDK Phase 2)

The create form covers the seven template-like families only. The parameter-heavy
intent adapters (SQL/Mongo/Elasticsearch/HTTP/GraphQL) are out of scope for the SDK
itself, so the panel inherits that limit — a spec registry entry is the prerequisite
for a form. See `server/adapter_sdk/ROADMAP.md` Phase 2; no panel work is possible
until the specs exist.

Worth surfacing in the UI meanwhile: the create panel currently offers seven families
with no indication that intent adapters exist and must be hand-written. A one-line note
pointing at the YAML editor would set expectations.
