# Creating Adapters

## Overview

Adapters can be created from the admin panel or the CLI, without hand-writing a YAML
file and adding it to the import list. Both surfaces are front-ends over the same
generator (`server/adapter_sdk/`): you pick an adapter *family*, answer a short set of
questions, preview the generated YAML, and confirm. The result is written to
`config/adapters/<name>.yaml`, registered in `config/adapters.yaml`, and hot-reloaded —
no server restart.

Creating an adapter makes **no LLM calls** — generation is entirely deterministic,
driven by the spec registry and Jinja templates.

Looking for the field-by-field schema of an adapter entry? See the
[Adapter Configuration Reference](../tutorial/adapter-configuration-reference.md).
For editing adapters that already exist, see
[Adapter Configuration](adapter-configuration.md).

## What can be created

Seven *template-like* families:

| Family | Produces |
|---|---|
| Passthrough / conversational | Pure conversational adapter, no retrieval; optional skill routing and MCP tools |
| Document generator | PDF / Word / Excel / CSV / Markdown / PowerPoint generation |
| Media generator | Image, video, or audio generation |
| Fetch | Fetch web page content from a URL (no LLM step) |
| MCP agent | Exposes configured MCP servers as an agentic tool-calling skill |
| Web search (provider-native) | Delegates search to the LLM provider's built-in tool |
| Web search (external provider) | Calls a dedicated search API (Brave, Tavily, SearXNG, …) |

**Intent × datasource adapters (SQL/Mongo/Elasticsearch/HTTP/GraphQL) cannot be created
this way.** Their config branches heavily by backend and they need domain-config and
template-library files that don't exist yet at creation time. Write those by hand or
with `utils/templates/template_generator.py`, then edit them in the Adapters tab.

## Why a spec registry

The fields `type`, `datasource`, `adapter`, and `implementation` are *interdependent* —
a plausible-looking combination that isn't one of the valid tuples produces an adapter
that loads and then misbehaves. So they are never asked and never generated. Each family
hard-codes its tuple in `server/adapter_sdk/specs.py`, and only the remaining questions
are put to you.

This is also why the admin form contains no adapter knowledge of its own: it is rendered
entirely from `GET /admin/adapters/specs`. Adding a family to the registry adds it to the
panel, the CLI, and the API at once.

## Using the admin panel

Adapters tab → **Create Adapter**.

1. **Adapter family** — picks the spec. Changing it rebuilds the form.
2. **Variant** (some families only) — e.g. document format, media type, search provider.
   Switching the variant re-defaults the other fields, but only the ones you have not
   edited yourself.
3. **Fill the fields.** Every field has a default and a stated limit.
4. **Preview YAML** — renders exactly what will be written, read-only. Validation
   problems are listed above it rather than replacing it.
5. **Create Adapter** — writes, registers, hot-reloads, and opens the new adapter in the
   detail editor.

Requires the `adapters.manage` permission (roles: `admin`, `operator`).

### Field limits

Every answer is bounded — an adapter config is a small YAML document, and these values
reach both the config file and the prompt the adapter builds at runtime. Defaults are
200 characters per string (25 per list); the notable overrides:

| Field | Limit |
|---|---|
| `name` | 64 characters (it becomes a filename) |
| `skill_name` | 64 characters |
| `skill_description` | 500 characters |
| `routing_examples` | 200 characters per entry, 50 entries |
| `fetch_timeout` | 1–600 seconds |
| `result_count` | 1–50 |

Limits are declared once per question in the spec registry and enforced in three places:
the form controls, the REST endpoint, and the CLI — so no route around the form bypasses
them. The form shows each limit in the field hint and a live counter on the longer ones.

## Using the CLI

`bin/adapter-sdk.sh` works from any directory and resolves the repo root and venv itself.

```bash
bin/adapter-sdk.sh --list                          # list families
bin/adapter-sdk.sh --list --json                   # full spec registry as JSON
bin/adapter-sdk.sh                                 # interactive wizard
bin/adapter-sdk.sh --spec fetch --dry-run          # render + validate, write nothing
bin/adapter-sdk.sh --spec fetch --from-json answers.json --yes
```

Useful flags: `--dry-run`, `--no-register`, `--overwrite`, `--yes`, and `--config`.

> **`--config` matters when the server runs with its own config.** By default the CLI
> writes to the repo's `config/`. If your server was started with
> `--config /etc/orbit/config.yaml`, pass the same path so the CLI writes to the
> directory the server actually reads.

`--spec <family> --dry-run` prints a valid example you can copy into a `--from-json`
answers file; the JSON keys are the family's question fields.

After writing from the CLI, apply it with `orbit admin reload-adapters` (the admin panel
does this for you).

## REST API

All endpoints require the `adapters.manage` permission.

| Endpoint | Purpose |
|---|---|
| `GET /admin/adapters/specs` | Spec registry as JSON — families, questions, limits, per-variant defaults. The form is generated from this. |
| `POST /admin/adapters/preview` | `{spec, answers}` → `{yaml, errors}`. Always 200; validation problems come back in `errors`. |
| `POST /admin/adapters` | `{spec, answers, register, overwrite}` → renders, validates, writes, registers, hot-reloads. |

Notable responses: **404** unknown family, **422** invalid answers or a bad variant,
**409** name collision.

### Name collisions

Two checks, deliberately different:

- **Target file already exists** → 409. `overwrite: true` waives this — you are replacing
  a file you own.
- **The adapter *name* is already defined in a different file** → 409, **never waivable**.
  Two files declaring the same adapter name means one silently shadows the other at load
  time, so `overwrite` is not allowed to create that state.

## What gets written

Two files change:

1. **`config/adapters/<name>.yaml`** — the adapter definition, written atomically.
2. **`config/adapters.yaml`** — one line appended to the `import:` list. This is what
   *activates* the adapter; ORBIT only loads adapters whose file is imported, and the
   admin panel only lists them.

Then `reload_adapter_configs` applies the change to the running server.

> **Multi-worker deployments:** with `performance.workers > 1` the hot reload applies in
> the worker that served the request. Restart to guarantee every worker picks it up.
> Same caveat as [MCP hot reload](../roadmap/mcp-hot-reload-multi-worker.md).

## Limitations

- **No deletion or export from the panel** yet — remove the file and its import line by
  hand. Planned in [adapter-creation-next-steps](../roadmap/adapter-creation-next-steps.md).
- **No round-trip editing.** Once created, an adapter is edited as raw YAML in the
  Adapters tab; there is no "reopen in the form".
- **One adapter per file** for generated adapters, though hand-written files may declare
  several.
- **Concurrent creates are unlocked.** Two simultaneous creates can lose an import line.
  Fine for interactive admin use.

## Reference

| Path | Role |
|---|---|
| `server/adapter_sdk/specs.py` | Spec registry — tuples, questions, limits, variants |
| `server/adapter_sdk/renderer.py` | Jinja2 templates → commented YAML |
| `server/adapter_sdk/validator.py` | Structure, answer-limit, and capability validation |
| `server/adapter_sdk/writer.py` | Atomic write + import registration |
| `server/routes/admin_routes.py` | REST endpoints |
| `server/admin/admin_panel.js` | Create form in the Adapters tab |
