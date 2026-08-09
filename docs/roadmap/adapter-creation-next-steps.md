# Adapter Creation — Next Implementation Steps

## Summary

The admin panel's adapter SDK path is now feature-complete for the seven
template-like families: create, preview, delete, export/import, round-trip
editing, and creation hardening have all shipped (see "Shipped" below for
where each lives). What remains is the harder, higher-value work the SDK has
deferred since v1 — intent × datasource families, the config/query surface
those adapters need beyond the adapter YAML itself — plus a handful of
smaller, independent follow-ups noted during that work but not acted on.

Reference: `server/adapter_sdk/README.md` (current REST surface).

---

## Shipped (for reference — no longer tracked here)

- **Create / preview**: `GET /admin/adapters/specs`, `POST /admin/adapters/preview`,
  `POST /admin/adapters` — spec registry in `server/adapter_sdk/specs.py`,
  Jinja templates in `server/adapter_sdk/templates/`.
- **Delete**: `DELETE /admin/adapters/{name}` — `server/adapter_sdk/writer.py`
  (`unregister_import`, `delete_adapter`), referrer/multi-adapter-file checks in
  `server/routes/admin/adapters.py`.
- **Multimodal (file-retrieval) family**: `MULTIMODAL` spec in `specs.py`, covering
  `simple-chat-with-files`/`-audio` — vision/STT/TTS providers, storage/chunking/
  vector-store config, optional audio-transcription toggle.
- **Export / import**: `GET /admin/adapters/{name}/export`,
  `POST /admin/adapters/import`, `POST /admin/adapters/import/format` — one adapter
  per call, secrets stay as `${ENV_VAR}` refs, accepts a full document or a bare
  list/mapping entry.
- **Round-trip editing**: `GET /admin/adapters/{name}/edit-form` +
  `server/adapter_sdk/detector.py` (`detect_spec_and_variant`, `extract_answers`,
  `detect_editable_spec`) — detects which spec produced an existing adapter,
  recovers its answers, and refuses (rather than guesses) when the round trip
  isn't lossless. "Edit in Form" in `server/admin/admin_panel/tabs/adapters.js`
  saves back through the block-splice endpoint (`PUT
  /adapters/config/entry/{name}`) so adapters in shared, multi-adapter files
  save correctly.
- **Creation hardening**: disabled-provider and skill-name-collision checks on
  create/import (`_enabled_inference_providers`, `_find_skill_name_owner` in
  `server/routes/admin/adapters.py`), multi-worker generation propagation
  (`_propagate_adapter_generation`, shared by create/import/delete), and
  non-mapping-YAML-file crash guards in `_find_adapter_file` /
  `_find_adapter_referrers` (`server/routes/admin/_yaml_config.py`,
  `server/routes/admin/adapters.py`).

---

## 1. Intent × datasource families (SDK Phase 2)

The create form covers the seven template-like families only. The parameter-heavy
intent adapters (SQL/Mongo/Elasticsearch/HTTP/GraphQL/Firecrawl/Agent) are out of
scope for the SDK itself, so the panel inherits that limit — a spec registry entry
is the prerequisite for a form. No panel work is possible until the specs exist.
This is the biggest remaining piece of value and the reason the SDK hasn't
replaced hand-written adapter YAML for most of `config/adapters/*.yaml` yet.

**Why it's hard:** unlike the template-like families (one Jinja template, fixed
`type`/`datasource`/`adapter`/`implementation` tuple, a flat list of questions),
an intent adapter's `config` block branches heavily by backend — Postgres
connection pooling vs. DuckDB `read_only` vs. Elasticsearch `index_pattern` vs.
HTTP `base_url`+`auth` vs. Firecrawl chunking — and a working intent adapter also
needs a `domain_config_path` + `template_library_path` pointing at files that
don't exist yet (produced today only by
`server/utils/templates/template_generator.py`, run by hand). Round-trip editing
(now shipped for the template-like families) explicitly does not cover this
family either — `detector.py`'s spec-detection tuple-matching has nothing to
match an intent adapter against, so those always fall back to the YAML editor,
which is correct today but becomes a real gap once intent specs exist.

**Tasks:**
- [ ] Extend `server/adapter_sdk/specs.py` with an intent-family spec model keyed
      by `(family, backend)` → implementation class + per-backend `config`
      sub-schema. `AdapterSpec` as it exists (flat `questions` list, one
      `variant_field`) may not fit a two-axis family/backend selection — decide
      whether that needs a new dataclass shape or nested variants before writing
      the first backend.
- [ ] Add per-backend Jinja templates (or one parameterized template + backend
      fragments) for the `config` and `fault_tolerance` blocks. Look at the
      existing hand-written intent adapters (`config/adapters/customer-orders.yaml`
      for SQL, `intent.yaml` for HTTP/GraphQL/Firecrawl/Agent,
      `elasticsearch-logs.yaml`, `mongodb-mflix.yaml`,
      `business-analytics.yaml`/`ev.yaml` for DuckDB) as the ground truth for what
      each backend's `config` block actually needs.
- [ ] Orchestrate `server/utils/templates/template_generator.py` from the SDK:
      given a schema + NL queries, produce the domain config + template library,
      then wire their paths into the generated adapter. Do NOT reimplement
      template generation — call the existing tool.
- [ ] Extend the create-form flow (backend or frontend): pick backend → collect
      connection/config answers → optionally run template generation inline →
      render adapter + register. Decide whether the "run template generation
      inline" step is synchronous (the create route already does a bounded
      amount of I/O) or needs the async-job pattern used elsewhere in
      `server/routes/admin/jobs.py`.
- [ ] Validation: verify `store_name` exists in `stores.yaml`, `datasource` exists
      in `datasources.yaml`, and referenced template/domain files exist on disk,
      before writing the adapter — a dangling reference here fails at first query,
      not at creation.
- [ ] Tests: render+validate each backend; round-trip against a committed intent
      adapter (e.g. `customer-orders.yaml`); loader integration
      (`AdapterCapabilities.from_config`, same as the template-like families'
      tests).
- [ ] Once specs exist, extend `detect_spec_and_variant`/`extract_answers` in
      `detector.py` to cover them too, so round-trip editing isn't permanently
      template-family-only.

Worth surfacing in the UI meanwhile: the create panel currently offers seven
families with no indication that intent adapters exist and must be hand-written.
A one-line note pointing at the YAML editor would set expectations until this
lands.

## 2. Autocomplete for provider/model/store/datasource answers

Several create-form questions are free-text today where the valid values are
actually enumerable from config already loaded into `app.state.config` —
`inference_provider` (`PASSTHROUGH`/`MULTIMODAL`/etc.), `vector_store`
(`MULTIMODAL`), and any future intent-family `datasource`/`store_name` answers
(section 1). A typo in any of these is invisible at creation time and only
surfaces as a runtime error on first query — the same class of gap
`validate_providers` (shipped) already closes for `inference_provider`, just
not yet exposed as *guidance* in the form, only as a rejection after the fact.

**Why raise this now:** `_enabled_inference_providers(config)`
(`server/routes/admin/adapters.py`, shipped in the hardening pass) already
extracts exactly the provider-name set this needs — the hard part (reading
`app.state.config["inference"]` correctly, matching `ai_services.registry`'s
enabled/disabled semantics) is done. Datasources and vector stores are the same
shape: `config["datasources"]` and `config["vector_stores"]` (merged at startup
from `datasources.yaml`/`stores.yaml` via `config_manager.py`'s import
processing) are dicts keyed by name, already present in the same
`app.state.config` object. This is now mostly plumbing, not new discovery.

**Tasks:**
- [ ] `GET /admin/adapters/answer-options` (or fold into `GET /admin/adapters/specs`)
      returning `{"inference_providers": [...], "vector_stores": [...],
      "datasources": [...]}` from `app.state.config`, reusing
      `_enabled_inference_providers` for the first and simple `.keys()` reads for
      the other two. Decide whether disabled providers/stores are omitted or
      included-but-flagged — omitting matches `validate_providers`' current
      strictness, but a flagged/greyed-out option is more discoverable than a
      value that silently doesn't appear.
- [ ] Extend `serialize_spec`/`Question` (`server/adapter_sdk/specs.py`) with an
      optional `options_source: str` field (e.g. `"inference_providers"`) so the
      admin panel knows which answer-options key feeds which question, instead
      of hardcoding field-name-to-source mapping in the frontend.
- [ ] Frontend (`server/admin/admin_panel/tabs/adapters.js`,
      `buildAdapterCreateForm`/`makeQuestionInput`): render an `options_source`
      question as a `<select>` (or a free-text input with a `<datalist>`, if "let
      me type a value not in the list yet" needs to stay possible — e.g. a store
      defined after the panel loaded its cache) instead of a plain text box.
      `cachedAdapterSpecs`/`cachedAdapterCapabilities`'s existing lazy-load-and-cache
      pattern is the model to follow for caching the new options endpoint.
- [ ] Decide read staleness: the options list is a point-in-time snapshot like
      `cachedAdapterSpecs` already is — reloading it on every panel open (cheap,
      it's an in-memory config read) is simpler than adding cache-invalidation
      hooks, and avoids a stale list surviving a config reload.
- [ ] Tests: options endpoint reflects `app.state.config` correctly (enabled vs.
      disabled providers, empty section skipped rather than erroring); permission
      guard alongside the other `/adapters/*` routes.

## 3. Remaining hardening items

Two items noted during the creation-hardening pass were deliberately deferred as
lower-value/non-blocking rather than left as oversights:

- [ ] **Concurrency.** `adapters.yaml` writes are atomic per-write
      (`adapter_sdk/writer.py`'s `_atomic_write`, temp file + `os.replace`) but
      unlocked — two simultaneous creates can race and one's import-line
      registration can be lost. Acceptable for an admin panel driven by one
      operator at a time today; revisit with a file lock (or moving registration
      through a single-writer queue) if adapter creation is ever automated
      (e.g. bulk-provisioned via API/CLI).
- [ ] **Pydantic request models.** `create_adapter`/`import_adapter`/`preview_adapter`
      take plain `dict` bodies via `Body(...)`, matching the neighbouring adapter
      routes but losing free 422s and OpenAPI schema docs. `models/schema.py`'s
      `ApiKeyCreate` is the pattern to mirror. Lower priority than the correctness
      fixes already shipped, and a wider surface change (touches three routes'
      request handling) — worth doing opportunistically, not urgently.

## 4. Cross-cutting / smaller follow-ups

- [ ] **Multi-adapter files: append instead of always one-file-per-adapter.**
      `writer.write_adapter` always writes `<name>.yaml`; there's no path to add
      a new adapter into an existing shared file like
      `config/adapters/web-search-providers.yaml`. Round-trip *editing* an
      adapter already in a shared file works today (saves splice the block in
      place via `PUT /adapters/config/entry/{name}`) — this item is specifically
      about *creating a new* adapter directly into an existing file instead of
      always getting its own.
- [ ] **Skill-graph reference check.** The collision half of this
      (`_find_skill_name_owner`, two adapters can't claim the same `skill_name`)
      shipped in the hardening pass. Still missing: warning/rejecting when an
      adapter's `available_skills`/`auto_routable_skills` names a skill *no*
      adapter actually exposes — a silent dangling reference today, only visible
      at runtime when the router can't find the skill.
- [ ] **CLI subcommands: `delete`, `export`, `import`.** `server/adapter_sdk/cli.py`
      only wraps create/list; promote it to a `click` group and wire
      `orbit adapter ...` into `bin/orbit.py` so the CLI reaches the same
      operations the admin panel now has. Standalone launchers
      (`bin/adapter-sdk.sh` / `bin/adapter-sdk.bat`) already exist and would fold
      into the main entrypoint.
