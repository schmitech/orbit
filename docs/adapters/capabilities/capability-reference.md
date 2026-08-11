# Capability Reference

**Capabilities are universal — every ORBIT adapter type (passthrough, QA, intent, file, custom) uses the same `capabilities:` block to control retrieval behavior, formatting, and request parameters.** This page covers the retrieval/formatting/request-shaping fields below, plus the skill- and MCP-specific fields in [Skill & MCP Capabilities](#skill--mcp-capabilities). For the pipeline architecture behind capabilities (how they're inferred, resolved, and consumed at request time), see [Adapter Capability Architecture](adapter-capability-architecture.md).

## All Available Capabilities

| Capability | Type | Default | Description |
|------------|------|---------|-------------|
| `retrieval_behavior` | enum | `"always"` | `"none"`, `"always"`, or `"conditional"` — controls when retrieval occurs |
| `formatting_style` | enum | `"standard"` | `"standard"` (with citations/confidence), `"clean"` (no citations), or `"custom"` (adapter provides formatting) |
| `supports_file_ids` | bool | `false` | Whether the adapter can filter results by file IDs |
| `supports_session_tracking` | bool | `false` | Whether the adapter tracks and uses session IDs |
| `requires_api_key_validation` | bool | `false` | Whether API key validation is required for ownership checks |
| `supports_threading` | bool | `false` | Whether the adapter supports conversation threading on cached datasets — see [Conversation Threading](#conversation-threading-supports_threading) |
| `supports_language_filtering` | bool | `false` | Whether the adapter can filter/boost results by detected query language |
| `skip_when_no_files` | bool | `false` | For conditional retrieval: skip when `file_ids` is empty |
| `required_parameters` | list | `[]` | Parameters that MUST be provided to the retriever |
| `optional_parameters` | list | `[]` | Parameters that CAN be provided (e.g. `api_key`, `file_ids`, `session_id`) |
| `context_format` | string | `null` | Table format for intent data: `"markdown_table"`, `"toon"`, `"csv"`, or `null` (default pipe-separated) — see [Context Efficiency](#context-efficiency-context_format-context_max_tokens-numeric_precision) |
| `context_max_tokens` | int | `null` | Token budget for context trimming; drops lowest-confidence documents when exceeded |
| `numeric_precision` | object | `{}` | Numeric formatting, e.g. `{decimal_places: 2}`, for rounding unformatted floats |
| `available_skills` | list | `[]` | Skill names this adapter may invoke via `skill:` in requests. See [Skills](../skills.md) |
| `requires_authenticated_user` | bool | inherits `auth.require_authenticated_user` | Per-adapter override: require a logged-in user (not just a valid API key) to call this adapter |

## Skill & MCP Capabilities

These fields configure the two mechanisms covered in [Skills, MCP Tools, and Skill Routing](../../tutorial/skills-concepts.md): turning an adapter into a callable **skill**, and letting a conversational adapter call **MCP tools**. See that tutorial page for how the two differ; this section is the field reference for both.

| Capability | Type | Default | Applies to | Description |
|---|---|---|---|---|
| `expose_as_skill` | bool | `false` | The skill adapter | Publishes this adapter as a skill other adapters can invoke |
| `skill_name` | string | `null` | The skill adapter | The identifier clients/callers send as `skill: "<name>"` — required when `expose_as_skill: true` |
| `skill_description` | string | `null` | The skill adapter | Human-readable description shown in the `/` skill picker and used by auto-routing's confirm step |
| `routing_examples` | list | `[]` | The skill adapter | Example phrases (multilingual, if relevant) that boost the auto-routing embedding pre-filter for this skill — see `auto_skill_routing` below |
| `available_skills` | list | `[]` | The calling adapter | Skill names this adapter is allowed to invoke via an explicit `skill: "<name>"` field or the `/` picker |
| `auto_skill_routing` | bool | `false` | The calling adapter | Enables inferring a skill from plain language, with no `skill` field sent — requires the global `skill_routing.auto_detect: true` gate in `config/config.yaml` |
| `auto_routable_skills` | list | `[]` | The calling adapter | Skill names this adapter may auto-route to. A skill can be listed here and in `available_skills` (reachable both ways), or only here (auto-only — not reachable via an explicit `skill=` field or the `/` picker) |
| `mcp_tools` | bool | `false` | The calling adapter | Lets the model call MCP tools opportunistically, on any turn, with no `skill` field or adapter swap |
| `mcp_servers` | list | `[]` | The calling adapter | Allowlist of MCP server names (declared in `config/mcp_clients.yaml`) this adapter may call tools from |
| `web_search` | bool | `false` | Passthrough adapters | Enables the LLM provider's native web search for this adapter's calls — only `gemini`, `openai`, `xai`, and `anthropic` support it |

```yaml
# Exposing an adapter as a skill (config/adapters/image-generator.yaml)
capabilities:
  expose_as_skill: true
  skill_name: "Image"
  skill_description: "Generate images from text descriptions using AI"
  routing_examples:
    - "generate an image of"
    - "draw me a picture of"
```

```yaml
# Allowing a chat adapter to invoke skills explicitly and/or auto-route to them
# (config/adapters/passthrough.yaml)
capabilities:
  available_skills:
    - "mcp-agent"          # explicit-only: skill="mcp-agent" or the / picker
    - "Image"              # also explicit: skill="Image" or the / picker
  auto_routable_skills:
    - "Image"              # same skill can ALSO be inferred from plain language
    - "Audio"              # auto-only here: not listed in available_skills above,
                            # so it's reachable only via auto-routing, not skill=
  auto_skill_routing: true
```

`available_skills` and `auto_routable_skills` aren't mutually exclusive — a skill can appear in both (explicit *and* inferred, like `Image` above) or in only one (auto-only, like `Audio` above, which stays out of `available_skills` so it can't be invoked directly).

```yaml
# Letting a chat adapter call MCP tools opportunistically
# (config/adapters/passthrough.yaml)
capabilities:
  mcp_tools: true
  mcp_servers:
    - "business-sample"
```

### Conversation Threading (`supports_threading`)

Threading lets users ask follow-up questions about retrieved data without re-querying the datasource: the retrieved dataset is cached (Redis with TTL, or database) after the initial query, and follow-up messages use the cache instead of hitting the datasource again.

- Use `true` for **Intent adapters** — they return complex datasets (SQL results, API responses, aggregations) that users often want to explore further.
- Use `false` for **QA adapters, passthrough, and file adapters** — each query is independent and doesn't benefit from a cached follow-up window.

```yaml
# Intent adapter — enable threading for follow-up questions
capabilities:
  supports_threading: true

# QA adapter — disable threading for simple Q&A
capabilities:
  supports_threading: false
```

### Context Efficiency (`context_format`, `context_max_tokens`, `numeric_precision`)

These control how context is formatted and sized before being sent to the LLM, reducing token usage and improving parsing reliability — mainly relevant to intent adapters returning tabular data.

| Value (`context_format`) | Description |
|---|---|
| `null` (default) | Pipe-separated: `col1 \| col2 \| col3` |
| `"markdown_table"` | Standard markdown table with `---` separator — parses best for most LLMs |
| `"toon"` | Compact format via `py_toon_format` (falls back to pipe-separated if not installed) |
| `"csv"` | CSV format |

`context_max_tokens` estimates tokens as `len(text) // 4` and drops documents from the end (lowest confidence) until the budget is met. `numeric_precision.decimal_places` rounds unformatted floats (e.g. `3.141592653589793` → `3.14`); it only applies to floats without an explicit `display_format` in the domain config.

```yaml
capabilities:
  context_format: "markdown_table"
  context_max_tokens: 8000
  numeric_precision:
    decimal_places: 2
```

## Capability Templates by Adapter Type

| Adapter Type | `retrieval_behavior` | `formatting_style` | `supports_threading` | Example adapters |
|---|---|---|---|---|
| Passthrough — conversational | `"none"` | `"standard"` | `false` | `simple-chat` |
| Passthrough — multimodal | `"conditional"` | `"clean"` | `false` | `simple-chat-with-files` |
| QA — SQL or vector | `"always"` | `"standard"` | `false` | `qa-sql`, `qa-vector-chroma`, `qa-vector-qdrant` |
| Intent — SQL, NoSQL, or HTTP | `"always"` | `"standard"` | `true` | `intent-sql-postgres`, `intent-mongodb-mflix`, `intent-http-jsonplaceholder` |
| File — document Q&A | `"always"` | `"clean"` | `false` | `file-document-qa` |

```yaml
# Passthrough — Conversational
capabilities:
  retrieval_behavior: "none"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  requires_api_key_validation: false
```

```yaml
# Passthrough — Multimodal
capabilities:
  retrieval_behavior: "conditional"
  formatting_style: "clean"
  supports_file_ids: true
  supports_session_tracking: true
  requires_api_key_validation: true
  skip_when_no_files: true
  optional_parameters:
    - "file_ids"
    - "api_key"
    - "session_id"
```

```yaml
# QA — SQL or Vector Store
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: false        # simple Q&A, no follow-up threading
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

```yaml
# Intent — SQL, NoSQL, or HTTP/API
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_session_tracking: false
  supports_threading: true         # supports follow-up on cached datasets
  requires_api_key_validation: false
  optional_parameters:
    - "api_key"
```

```yaml
# File — Document Q&A
capabilities:
  retrieval_behavior: "always"
  formatting_style: "clean"
  supports_file_ids: true
  supports_session_tracking: false
  requires_api_key_validation: true
  optional_parameters:
    - "file_ids"
    - "api_key"
```

## Common Customizations

| Goal | Change |
|---|---|
| Remove citations on any adapter | `formatting_style: "clean"` |
| Add file filtering to any retriever | `supports_file_ids: true` + `optional_parameters: ["file_ids"]` |
| Add session tracking | `supports_session_tracking: true` + `optional_parameters: ["session_id"]` |
| Make retrieval conditional | `retrieval_behavior: "conditional"` + `skip_when_no_files: true` (or a custom condition) |
| Enable follow-up questions (Intent adapters) | `supports_threading: true` |
| Disable follow-up questions (QA/passthrough) | `supports_threading: false` |
| Boost/filter by language | `supports_language_filtering: true` |
| Switch table format (Intent adapters) | `context_format: "markdown_table" \| "toon" \| "csv"` |
| Cap context size | `context_max_tokens: 8000` |
| Round noisy floats | `numeric_precision: {decimal_places: 2}` |

## Decision Tree

```
What type of adapter do you have?

├─ Passthrough?
│  ├─ Pure chat?  → "Passthrough — Conversational" template
│  └─ With files? → "Passthrough — Multimodal" template
│
├─ QA?            → "QA — SQL or Vector Store" template
│
├─ Intent?        → "Intent — SQL, NoSQL, or HTTP/API" template
│
├─ File?          → "File — Document Q&A" template
│
└─ Custom?        → Choose the closest template above and customize
```

## Optional vs. Recommended

Capabilities are optional — auto-inference fills in sensible defaults when a `capabilities:` block is omitted:

- `type: "passthrough"` + `adapter: "conversational"` → no retrieval
- `type: "passthrough"` + `adapter: "multimodal"` → conditional retrieval (files)
- `adapter: "file"` → always retrieve, clean formatting
- All other retrievers → always retrieve, standard formatting

Explicit declaration is recommended for production/enabled adapters — it self-documents behavior and makes future changes a one-line config edit instead of a code change. Leave disabled/example adapters on auto-inference.

## FAQs

**Do I need to add capabilities to every adapter?** No — auto-inference covers all adapter types. Explicit is recommended for production adapters.

**Can I use capabilities with any adapter type, including custom ones?** Yes. The system is universal — passthrough, QA, intent, file, and custom adapters all use the same fields.

**What's the difference between `required_parameters` and `optional_parameters`?** `required_parameters` are mandatory — retrieval fails without them. `optional_parameters` are passed through if provided but aren't required. Common optional parameters: `api_key`, `file_ids`, `session_id`.

**What table format should I use for `context_format`?** Default (omit/`null`) preserves the original pipe-separated format. `"markdown_table"` parses best for most LLMs. `"toon"` is the most compact. `"csv"` is plain CSV. All are backward-compatible.

## Quick Copy-Paste

```yaml
# QA adapter (simple Q&A, no threading)
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_threading: false
```

```yaml
# Intent adapter (complex datasets, with threading)
capabilities:
  retrieval_behavior: "always"
  formatting_style: "standard"
  supports_file_ids: false
  supports_threading: true
  # context_format: "markdown_table"  # Optional: markdown_table, toon, csv
  # context_max_tokens: 8000          # Optional: token budget for context
  # numeric_precision:                # Optional: round unformatted floats
  #   decimal_places: 2
```

```yaml
# File/multimodal adapter (clean formatting)
capabilities:
  retrieval_behavior: "always"
  formatting_style: "clean"
  supports_file_ids: true
  requires_api_key_validation: true
```

```yaml
# Passthrough adapter (no retrieval)
capabilities:
  retrieval_behavior: "none"
  formatting_style: "standard"
  supports_file_ids: false
```
