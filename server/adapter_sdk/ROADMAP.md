# Adapter SDK — Roadmap

v1 (shipped) covers the *template-like* families through a Python library + `click` wizard:
document/media generators, passthrough, fetch, mcp-agent, and web-search. See `README.md`.

This roadmap describes the phases deferred from the original plan. Each phase is scoped so it
can be picked up independently; the ordering reflects value-vs-effort.

---

## Phase 2 — Intent × datasource generation (the parameter-heavy families)

**Goal:** generate intent retriever adapters (SQL/Mongo/Elasticsearch/HTTP/GraphQL/Firecrawl/Agent)
and their supporting domain-config + template files, not just the adapter YAML.

**Why it's hard:** the `config` block branches heavily by backend (Postgres pooling vs. DuckDB
`read_only` vs. ES `index_pattern` vs. HTTP `base_url`+`auth` vs. Firecrawl chunking), and a working
intent adapter also needs a `domain_config_path` + `template_library_path` that don't exist yet.

**High-level tasks:**
- [ ] Extend `specs.py` with an intent-family spec model keyed by `(family, backend)` → implementation
      class + per-backend `config` sub-schema. Reuse the tuple table already documented in the plan.
- [ ] Add per-backend Jinja templates (or one parameterized template + backend fragments) for the
      `config` and `fault_tolerance` blocks.
- [ ] Orchestrate `utils/templates/template_generator.py` from the SDK: given a schema + NL queries,
      produce the domain config + template library, then wire their paths into the generated adapter.
      Do NOT reimplement template generation — call the existing tool.
- [ ] Extend the wizard: pick backend → collect connection/config answers → optionally run template
      generation inline → render adapter + register.
- [ ] Validation: verify `store_name` exists in `stores.yaml`, `datasource` exists in
      `datasources.yaml`, and referenced template/domain files exist on disk.
- [ ] Tests: render+validate each backend; round-trip against a committed intent adapter
      (e.g. `customer-orders.yaml`); loader integration.

## Phase 3 — Admin-UI wizard + REST endpoints

**Goal:** drive the same library from the admin dashboard, filling the create/delete/export gap in
`server/routes/admin_routes.py` (which today only reads/updates/toggles/reloads).

**High-level tasks:**
- [ ] New endpoints (gated by the existing `adapters.manage` permission):
      `GET /adapters/specs` (spec registry + questions for form rendering),
      `POST /adapters` (create from an `answers` dict → render → validate → write → register),
      `DELETE /adapters/{name}` (remove file + de-register from imports),
      `GET /adapters/{name}/export` and `POST /adapters/import`.
- [ ] Pydantic request/response models in `server/models/schema.py`.
- [ ] The endpoints call the library directly — the `answers` dict is the shared contract, so no
      generation logic is duplicated in the route layer.
- [ ] Frontend: render the wizard from `GET /adapters/specs` (a form per question type), preview the
      generated YAML, POST on confirm, then hot-reload.
- [ ] Reconcile with the DB-backed adapter storage path (`internal_services.adapter_storage.mode`)
      so file-generated and DB-managed adapters coexist coherently.

## Phase 4 — Delete / export / round-trip editing

**Goal:** full lifecycle from the library + CLI, not just create.

**High-level tasks:**
- [ ] `writer.delete_adapter(name)` — remove `config/adapters/<name>.yaml` and its import entry
      (comment-preserving, mirror of `register_import`).
- [ ] `writer.export_adapter(name)` / bulk export to a portable bundle.
- [ ] Import: read a bundle, validate, write + register with conflict handling.
- [ ] CLI subcommands: `delete`, `export`, `import` (promote `cli.py` to a `click` group).
- [ ] "Edit" flow: parse an existing adapter back into an `answers` dict, re-run the wizard, re-render.
      Consider `ruamel.yaml` (not currently a dep) if in-place comment-preserving edits are required.

## Cross-cutting / smaller follow-ups

- [ ] Multi-adapter files: support appending to an existing file (e.g. `web-search-providers.yaml`)
      instead of always one-file-per-adapter. `writer` currently writes `<name>.yaml` only.
- [ ] Provider validation in the wizard: load enabled providers and use `validator.validate_providers`
      to warn before writing (currently the hook exists but the CLI passes `None`).
- [ ] Skill-graph checks: warn when a generated `skill_name` collides, or when `available_skills`
      references a skill no adapter exposes.
- [ ] Wire `orbit adapter ...` into `bin/orbit.py` so the CLI is reachable via the main entrypoint.
      (Standalone launchers `bin/adapter-sdk.sh` / `bin/adapter-sdk.bat` already exist; this would fold them into the main CLI.)
- [ ] Autocomplete for provider/model/store/datasource answers, sourced from the relevant config files.
