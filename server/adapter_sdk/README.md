# Adapter SDK

Generates ORBIT adapter config files (`config/adapters/*.yaml`) from a deterministic
spec registry. Generation is fully deterministic — no LLM calls are involved.

**Scope (v1):** the template-like families — document generators (pdf/word/excel/csv/
markdown/pptx), media generators (image/video/audio), passthrough/conversational,
fetch, mcp-agent, and web-search (provider-native + external). Intent × datasource
adapters are intentionally out of scope.

## Design

The tuple `type` + `datasource` + `adapter` + `implementation` is interdependent, so it
is never asked of the user — each family hard-codes it in a spec, so a plausible but
invalid combination can never be produced.

| Module | Role |
|---|---|
| `specs.py` | `AdapterSpec` + `SPEC_REGISTRY` — the source of truth (tuple, capability shape, wizard questions). |
| `renderer.py` | Jinja2 templates → idiomatic, commented YAML. |
| `validator.py` | Mirrors the real loader; reuses `adapters.capabilities.AdapterCapabilities.from_config`. |
| `writer.py` | Atomic write to `config/adapters/<name>.yaml` + registers it in `config/adapters.yaml` imports. |
| `cli.py` | Thin `click` wizard driving the library. |

The core (specs/renderer/validator/writer) is non-interactive: it takes an `answers`
dict and returns/writes YAML. The CLI and any future admin UI are just front-ends that
produce that dict.

> Lives under `server/` (not `utils/`) because it reuses server internals that import a
> bare `utils` package (`server/utils`); a top-level `utils.adapter_sdk` would shadow-clash
> with it. server/ is also where the admin routes that will reuse this library live.

## Usage

Use the launcher — it works from any directory (resolves the repo root and venv itself):

```bash
bin/adapter-sdk.sh --list                                   # list families
bin/adapter-sdk.sh                                           # interactive wizard
bin/adapter-sdk.sh --spec doc-generator --dry-run           # preview, don't write
bin/adapter-sdk.sh --spec fetch --from-json answers.json --yes   # non-interactive
bin/adapter-sdk.sh --help
```

On Windows, use the `.bat` wrapper (same flags):

```bat
bin\adapter-sdk.bat --list
```

Equivalently, run the module directly with `server/` as the import root:

```bash
cd server && ../venv/bin/python -m adapter_sdk.cli --list
# or, from the repo root:
PYTHONPATH=server venv/bin/python -m adapter_sdk.cli --list
```

Flags: `--spec`, `--from-json`, `--dry-run`, `--no-register`, `--overwrite`, `--yes`,
`--list --json` (the full spec registry as JSON), `--config` (write next to a specific
`config.yaml` instead of the repo's — use this when the server runs with its own `--config`).

After writing, reload without a restart: `orbit admin reload-adapters`.

## Admin panel / REST

The same library backs the **Create Adapter** form in the admin panel's Adapters tab.
All endpoints are gated by the `adapters.manage` permission and live in
`server/routes/admin_routes.py`:

| Endpoint | Purpose |
|---|---|
| `GET /admin/adapters/specs` | Spec registry as JSON — the form is generated from this. Each question carries `variant_defaults` so the client can re-default fields when the variant changes without another round-trip. |
| `POST /admin/adapters/preview` | `{spec, answers}` → `{yaml, errors}`. Always 200; validation problems come back in `errors`. |
| `POST /admin/adapters` | `{spec, answers, register, overwrite}` → renders, validates, writes, registers the import, and hot-reloads the adapter. 409 on a name/file collision. |

The routes always pass `adapters_dir`/`adapters_yaml` derived from the running
`config_path`, since the writer's module constants are repo-root relative.

## Tests

```bash
venv/bin/python -m pytest server/tests/test_adapters/test_adapter_sdk.py
```
