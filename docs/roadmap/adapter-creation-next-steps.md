# Adapter Creation — Next Implementation Steps

## Summary

The admin panel can now create adapters from the SDK spec registry: `GET
/admin/adapters/specs` drives a generated form, `POST /admin/adapters/preview`
renders the YAML, and `POST /admin/adapters` writes `config/adapters/<name>.yaml`,
registers it in `config/adapters.yaml`, and hot-reloads it. The path is fully
deterministic — no LLM calls are involved in creating an adapter.

Deletion has since landed too (section 1 below), so create/edit/delete are all covered.
What remains is moving adapters *between environments* — export and import — plus
round-trip editing and the spec families the SDK does not yet model. This document
describes that work, ordered by value, and consolidates the deferred SDK-side phases
(previously tracked in `docs/roadmap/adapter-sdk.md`).

Reference: `server/adapter_sdk/README.md` (current REST surface).

v1 of the SDK (shipped) covers the *template-like* families through a Python library +
`click` wizard: document/media generators, passthrough, fetch, mcp-agent, and
web-search. See `server/adapter_sdk/README.md`.

---

## 1. Adapter deletion — **done**

**Goal:** `DELETE /admin/adapters/{name}` — remove the adapter's YAML block, drop its
import line, and evict it from the running server.

Shipped: `writer.unregister_import` / `writer.delete_adapter`
(`server/adapter_sdk/writer.py`), `DELETE /adapters/{adapter_name}`
(`server/routes/admin/adapters.py`), and a type-to-confirm Delete button in the Adapters
detail panel (`server/admin/admin_panel/tabs/adapters.js`). Referrers (API keys, other
adapters' skill lists) produce a 409 that `force=true` waives; API keys are never
cascaded. See [Creating Adapters](../adapters/adapter-creation.md#deleting-an-adapter).

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

- [x] `writer.unregister_import(import_path, adapters_yaml)` — the inverse of
      `register_import` (`server/adapter_sdk/writer.py:53`). Same text-insertion
      discipline: delete the matching line via the existing `is_registered` regex,
      preserving surrounding comments, then `_atomic_write`. Idempotent, returns
      whether a line was removed.
- [x] `writer.delete_adapter(name, *, adapters_dir, adapters_yaml, unregister=True)` —
      `validate_adapter_name`, unlink the file, unregister. Raise `FileNotFoundError`
      when absent.
- [x] Route `DELETE /admin/adapters/{name}`, gated on `adapters_auth`, mirroring the
      create route's structure in `server/routes/admin_routes.py`.
- [x] **Multi-adapter files must be rejected, not silently mangled.** The writer is
      one-file-per-adapter, but `config/adapters/` ships files declaring several
      adapters (`web-search-providers.yaml`, `multimodal.yaml`). Use the existing
      `_find_adapter_file` + `_find_adapter_block` helpers: if the file holds more than
      one adapter, either splice out just that block and keep the file (preferred — the
      helpers already do this for the PUT/toggle routes) or return `409` telling the
      operator to edit the file directly. Never unlink a file that owns other adapters.
- [x] **Referential integrity check before deleting.** An adapter name can be
      referenced by an API key (`adapter_name` on the key record) and by other adapters'
      `available_skills` / `auto_routable_skills` lists. Deleting one out from under a
      live API key breaks that key's requests at runtime with no warning. Look for
      references first and return `409` with the referrers listed, or require an
      explicit `force: true`.
- [x] Frontend: a Delete button in the Adapters detail panel, using the existing
      `requireTypedConfirmation` helper (`server/admin/admin_panel.js:878`) — deletion
      is destructive and irreversible from the panel, so type-to-confirm matches how
      other destructive admin actions behave. On success clear `selectedAdapterEntry`,
      re-render, and surface `reload_summary.removed_names`.
- [x] Tests: file + import line both gone; multi-adapter file keeps its siblings;
      referenced adapter returns 409; deleting a non-existent adapter returns 404;
      permission guard.

## 2. Multimodal file-retrieval family (SDK gap)

**Goal:** support creating file-based-retrieval multimodal adapters like those in
`config/adapters/multimodal.yaml` (e.g. `simple-chat-with-files`) from the create form.

**Current gap (verified):** `SPEC_REGISTRY` in `server/adapter_sdk/specs.py:408-419`
has exactly 7 keys — `passthrough`, `doc-generator`, `media-generator`, `fetch`,
`mcp-agent`, `web-search-native`, `web-search-external`. The `_MULTIMODAL_IMPL`
constant (`specs.py:20`,
`implementations.passthrough.multimodal.MultimodalImplementation`) is reused only by
`DOC_GENERATOR` and `MEDIA_GENERATOR`, which are output-*generation* specs — neither
exposes fields for storage/chunking/vector_store config or file-retrieval capabilities
(`supports_file_ids`, `skip_when_no_files`, `requires_api_key_validation`, etc.). There
is no `multimodal`/file-retrieval-RAG family registered anywhere. `admin_panel.js` has
no client-side special-casing for multimodal either — it builds the form purely from
whatever `GET /admin/adapters/specs` returns, so this is a server-side spec gap, not a
frontend one.

**Why prioritize this:** compared to Phase 2 (intent × datasource, below) or full
export/round-trip editing, this is a much smaller lift — it reuses an existing
implementation class and mirrors the `doc-generator`/`media-generator` pattern already
in `specs.py`, with no new orchestration (template generation, referential-integrity
checks, etc.) required.

**Tasks:**
- [x] Add a `multimodal` (or `file-retrieval`) entry to `SPEC_REGISTRY` covering the
      `simple-chat-with-files` shape: `type: passthrough`, `datasource: none`,
      `implementation: implementations.passthrough.multimodal.MultimodalImplementation`,
      plus questions for `vision_provider`/`stt_provider`/`tts_provider`,
      storage (`storage_backend`, `storage_root`, `max_file_size`), chunking
      (`chunking_strategy`, `chunk_size`, `chunk_overlap`), and vector store
      (`vector_store`, `collection_prefix`).
- [x] Model the file-retrieval `capabilities` block (`retrieval_behavior: conditional`,
      `supports_file_ids`, `skip_when_no_files`, `requires_api_key_validation`,
      `requires_encryption`, `optional_parameters: [file_ids, api_key, session_id]`) as
      spec defaults/questions, distinct from the generation-only capabilities used by
      `DOC_GENERATOR`/`MEDIA_GENERATOR`.
- [x] Decide how `available_skills`/`auto_routable_skills` are populated for this family
      — likely reuse whatever skill-listing mechanism the wizard already has, rather than
      free-text entry. (Decided: reused the same free-text list mechanism `PASSTHROUGH`
      already uses — there is no other skill-listing mechanism in the wizard to reuse.)
- [x] Optional audio-transcription variant (`enable_audio_transcription`,
      `audio_transcription_language`, `supported_types`) as a toggle/sub-question, mirroring
      `simple-chat-with-files-audio`.
- [x] Tests: render+validate against both existing `multimodal.yaml` entries; loader
      integration. (`test_roundtrip_multimodal_simple_chat_with_files` and
      `test_roundtrip_multimodal_audio_variant` in `test_adapter_sdk.py`; loader
      integration covered via `validate_yaml_text` → `AdapterCapabilities.from_config`,
      the same real capability parser the server uses at load time.)

## 3. Export and import

**Goal:** move an adapter between environments without hand-copying YAML.

- [x] `GET /admin/adapters/{name}/export` — the adapter's YAML block, served as a file
      download. Largely a thin wrapper over the existing
      `GET /admin/adapters/config/entry/{name}`.
- [x] `POST /admin/adapters/import` — accept a YAML document, run it through
      `validate_yaml_text`, apply the same collision rules as create (target filename
      waivable by `overwrite`; a name owned by a *different* file never waivable), then
      write + register + reload.
- [x] Decide whether import accepts multi-adapter bundles. If yes, the writer needs a
      multi-entry path; if no, reject with a clear message. Do not let a bundle write
      partially and leave `adapters.yaml` half-registered. (Decided: reject — the writer
      is one-file-per-adapter, so a bundle with more than one entry is a 422 telling the
      operator to split it and import each adapter separately. No partial-write path.)
- [x] Secrets: exported YAML contains `${ENV_VAR}` references, not values — verify this
      holds for every spec before advertising export as safe to share. (Verified: every
      spec's `AdapterSpec.fixed`/template output only ever embeds an answer value or a
      literal `${VAR}` string — e.g. `WEB_SEARCH_EXTERNAL`'s `api_key` defaults —
      never a resolved secret. Export also serves the file verbatim from disk, so
      whatever is committed there is exactly what downloads.)

## 4. Round-trip editing (YAML → answers)

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

## 5. Hardening the existing create path

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

## 6. Intent × datasource families (SDK Phase 2)

The create form covers the seven template-like families only. The parameter-heavy
intent adapters (SQL/Mongo/Elasticsearch/HTTP/GraphQL/Firecrawl/Agent) are out of scope
for the SDK itself, so the panel inherits that limit — a spec registry entry is the
prerequisite for a form. No panel work is possible until the specs exist.

**Goal:** generate intent retriever adapters and their supporting domain-config +
template files, not just the adapter YAML.

**Why it's hard:** the `config` block branches heavily by backend (Postgres pooling vs.
DuckDB `read_only` vs. ES `index_pattern` vs. HTTP `base_url`+`auth` vs. Firecrawl
chunking), and a working intent adapter also needs a `domain_config_path` +
`template_library_path` that don't exist yet.

**Tasks:**
- [ ] Extend `specs.py` with an intent-family spec model keyed by `(family, backend)` →
      implementation class + per-backend `config` sub-schema. Reuse the tuple table
      already documented in the plan.
- [ ] Add per-backend Jinja templates (or one parameterized template + backend
      fragments) for the `config` and `fault_tolerance` blocks.
- [ ] Orchestrate `utils/templates/template_generator.py` from the SDK: given a schema +
      NL queries, produce the domain config + template library, then wire their paths
      into the generated adapter. Do NOT reimplement template generation — call the
      existing tool.
- [ ] Extend the wizard: pick backend → collect connection/config answers → optionally
      run template generation inline → render adapter + register.
- [ ] Validation: verify `store_name` exists in `stores.yaml`, `datasource` exists in
      `datasources.yaml`, and referenced template/domain files exist on disk.
- [ ] Tests: render+validate each backend; round-trip against a committed intent adapter
      (e.g. `customer-orders.yaml`); loader integration.

Worth surfacing in the UI meanwhile: the create panel currently offers seven families
with no indication that intent adapters exist and must be hand-written. A one-line note
pointing at the YAML editor would set expectations.

## 7. Cross-cutting / smaller follow-ups

- [ ] Multi-adapter files: support appending to an existing file (e.g.
      `web-search-providers.yaml`) instead of always one-file-per-adapter. `writer`
      currently writes `<name>.yaml` only.
- [ ] Skill-graph checks: warn when a generated `skill_name` collides, or when
      `available_skills` references a skill no adapter exposes.
- [ ] CLI subcommands: `delete`, `export`, `import` (promote `cli.py` to a `click`
      group); wire `orbit adapter ...` into `bin/orbit.py` so the CLI is reachable via
      the main entrypoint. (Standalone launchers `bin/adapter-sdk.sh` /
      `bin/adapter-sdk.bat` already exist; this would fold them into the main CLI.)
- [ ] Autocomplete for provider/model/store/datasource answers, sourced from the
      relevant config files.
