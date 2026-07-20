# Adapter SDK

Generates ORBIT adapter config files (`config/adapters/*.yaml`) from a deterministic
spec registry, with optional AI enrichment of "soft" fields.

**Scope (v1):** the template-like families — document generators (pdf/word/excel/csv/
markdown/pptx), media generators (image/video/audio), passthrough/conversational,
fetch, mcp-agent, and web-search (provider-native + external). Intent × datasource
adapters are intentionally out of scope.

## Design

The tuple `type` + `datasource` + `adapter` + `implementation` is interdependent, so it
is never asked of the user or the AI — each family hard-codes it in a spec. AI is scoped
to soft fields only (`skill_description`, `routing_examples`).

| Module | Role |
|---|---|
| `specs.py` | `AdapterSpec` + `SPEC_REGISTRY` — the source of truth (tuple, capability shape, wizard questions). |
| `renderer.py` | Jinja2 templates → idiomatic, commented YAML. |
| `validator.py` | Mirrors the real loader; reuses `adapters.capabilities.AdapterCapabilities.from_config`. |
| `writer.py` | Atomic write to `config/adapters/<name>.yaml` + registers it in `config/adapters.yaml` imports. |
| `enricher.py` | Optional AI fill of soft fields via `UnifiedProviderFactory` (same plumbing as the template generator). |
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

Flags: `--spec`, `--from-json`, `--dry-run`, `--no-register`, `--overwrite`, `--yes`.

After writing, reload without a restart: `orbit admin reload-adapters`.

## Tests

```bash
venv/bin/python -m pytest server/tests/test_adapter_sdk.py
```
