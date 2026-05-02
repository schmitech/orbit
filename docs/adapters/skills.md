# Skills — Cross-Adapter Capabilities

## Overview

**Skills** are specialized adapters that any other adapter can invoke on-demand, within the context of an ongoing conversation. Rather than switching adapters entirely, a client sends a `skill` field with a request and ORBIT transparently routes that single message to the skill adapter, returning its result instead of the normal response.

The first built-in skill is **image generation** (`image-generation`), backed by the `image-generator` adapter which supports DALL-E 3 and Google Imagen.

Key properties of the skills system:

- **Skill result replaces the normal response.** When a skill is invoked, the original adapter's LLM and retrieval pipeline are bypassed entirely. Only the skill's output is returned.
- **Explicit allowlist per adapter.** Each adapter declares which skills it may use via `available_skills` in its capabilities config. An adapter cannot invoke a skill it hasn't listed.
- **No separate authentication.** The client uses the same API key as usual; ORBIT validates internally that the authenticated adapter permits the requested skill.
- **Extensible.** Any adapter can be promoted to a skill by adding three fields to its YAML config. Future skills (video generation, code execution, translation, etc.) follow the exact same pattern.

---

## How It Works

```
Client: POST /v1/chat
  { "messages": [...], "skill": "image-generation" }
  X-API-Key: <key for "intent-sql-sqlite-hr">

   1. API key authenticates → adapter = "intent-sql-sqlite-hr"
   2. RequestContextBuilder detects skill="image-generation"
   3. Checks: "image-generation" ∈ hr adapter's available_skills  ✓
   4. Looks up: skill_name "image-generation" → adapter "image-generator"
   5. Swaps: context.adapter_name = "image-generator"
             context.original_adapter_name = "intent-sql-sqlite-hr"
   6. Pipeline runs as "image-generator":
        ImageGenerationStep executes (adapter type = image_generation)
        LLMInferenceStep is skipped
   7. Response: { "image": "<base64>", "image_format": "png" }
```

The conversation messages are still passed to the skill adapter, giving it full context of what the user was asking. The skill adapter decides how to use that context — image generation uses the last user message as the prompt.

---

## Configuration

### Exposing an Adapter as a Skill

Add three fields at the top level of the adapter entry:

```yaml
- name: "image-generator"
  enabled: true
  expose_as_skill: true                          # marks this adapter as a skill
  skill_name: "image-generation"                 # identifier used in requests
  skill_description: "Generate images from text descriptions using AI"
  type: "image_generation"
  datasource: "none"
  adapter: "multimodal"
  image_provider: "gemini"                       # openai or gemini (see config/image.yaml)
  capabilities:
    retrieval_behavior: "none"
    formatting_style: "clean"
    requires_api_key_validation: false           # no separate key needed for skill invocation
```

| Field | Required | Description |
|-------|----------|-------------|
| `expose_as_skill` | yes | Set to `true` to register this adapter as a skill |
| `skill_name` | yes | The identifier clients send in `skill:` — must be unique across all adapters |
| `skill_description` | no | Human-readable description shown in `GET /admin/skills` |

> **Note:** `requires_api_key_validation: false` on a skill adapter means ORBIT does not enforce a separate API key for the skill itself. The caller's existing API key is used for authentication; ORBIT only checks that the caller's adapter permits the skill.

### Allowing Skills in a Consumer Adapter

Add `available_skills` under the adapter's `capabilities` section:

```yaml
- name: "intent-sql-sqlite-hr"
  ...
  capabilities:
    retrieval_behavior: "always"
    supports_threading: true
    ...
    available_skills:
      - "image-generation"
```

An adapter can list multiple skills:

```yaml
available_skills:
  - "image-generation"
  - "video-generation"   # a future skill
```

If `available_skills` is omitted or empty, the adapter cannot invoke any skills.

---

## Request Format

Add a `skill` field to any normal chat request. Everything else stays the same — the conversation messages, streaming flag, and other fields are unchanged.

### Non-streaming

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "messages": [
      {"role": "user", "content": "Paint me a sunset over the Rocky Mountains"}
    ],
    "skill": "image-generation"
  }'
```

**Response:**

```json
{
  "response": "Paint me a sunset over the Rocky Mountains",
  "image": "<base64-encoded PNG>",
  "image_format": "png",
  "image_revised_prompt": "A breathtaking sunset casting warm golden hues over..."
}
```

### Streaming

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "messages": [
      {"role": "user", "content": "A futuristic city skyline at dusk"}
    ],
    "skill": "image-generation",
    "stream": true
  }'
```

**SSE stream:**

```
data: {"request_id": "abc123"}

data: {"done": true, "image": "<base64>", "image_format": "png"}
```

### Error — skill not allowed

If the authenticated adapter does not list the requested skill in `available_skills`, the server returns HTTP 500 with an error detail:

```json
{
  "error": "Skill 'image-generation' is not available for adapter 'simple-chat'. Available skills: []"
}
```

### Error — skill not registered

If `skill_name` does not match any adapter with `expose_as_skill: true`:

```json
{
  "error": "No adapter is registered for skill 'image-generation'"
}
```

---

## Admin API

### List all registered skills

```
GET /admin/skills
```

No authentication required beyond the standard admin check.

**Response:**

```json
{
  "skills": [
    {
      "name": "image-generation",
      "description": "Generate images from text descriptions using AI (DALL-E 3 or Imagen)",
      "adapter_name": "image-generator",
      "enabled": true
    }
  ]
}
```

Use this endpoint to build a skill picker in the UI (`/skills` autocomplete).

### List skills available to an adapter

```
GET /admin/adapters/{adapter_name}/skills
X-API-Key: <key>
```

Returns the `available_skills` list from the adapter's capabilities config. The adapter name is resolved from the API key (same behaviour as `/admin/adapters/{name}/models`).

**Response:**

```json
{
  "adapter_name": "intent-sql-sqlite-hr",
  "available_skills": ["image-generation"]
}
```

Use this endpoint to determine which skills to show in the UI for the current user's adapter.

---

## UI Integration (`/skills`)

The intended flow for a chat client:

1. On load (or on `/skills` typed), call `GET /admin/adapters/{name}/skills` to fetch skills available to the current adapter.
2. Render a list/autocomplete — the `name` and `description` from `GET /admin/skills` give you display text.
3. When the user selects a skill and submits a message, send the request with `skill: "<skill-name>"`.
4. The response will contain `image` / `image_format` instead of a text `response`. Render accordingly.

---

## Adding a New Skill

To add a second skill (e.g., video generation):

**1. Create or configure the skill adapter** (e.g., `config/adapters/video.yaml`):

```yaml
adapters:
  - name: "video-generator"
    enabled: true
    expose_as_skill: true
    skill_name: "video-generation"
    skill_description: "Generate short videos from text prompts"
    type: "video_generation"          # a future adapter type
    datasource: "none"
    adapter: "conversational"
    capabilities:
      retrieval_behavior: "none"
      formatting_style: "clean"
      requires_api_key_validation: false
```

**2. Register the skill in the adapter registry** (`config/adapters.yaml`):

```yaml
import:
  - "adapters/video.yaml"
```

**3. Allow the skill in consumer adapters:**

```yaml
capabilities:
  available_skills:
    - "image-generation"
    - "video-generation"
```

No server code changes are required. ORBIT discovers skill adapters at startup by scanning for `expose_as_skill: true` in all loaded adapter configs.

---

## Implementation Reference

| Component | File | Role |
|-----------|------|------|
| Skill field on request | `server/routes/routes_configurator.py` | `ChatRequest.skill` |
| Skill validation + routing | `server/services/chat_handlers/request_context_builder.py` | `build_context(skill=...)` |
| Skill registry lookups | `server/services/config/adapter_config_manager.py` | `get_skill_adapter()`, `get_all_skills()` |
| Skill tracking in pipeline | `server/inference/pipeline/base.py` | `ProcessingContext.requested_skill`, `.original_adapter_name` |
| Capability declaration | `server/adapters/capabilities.py` | `AdapterCapabilities.available_skills` |
| Admin endpoints | `server/routes/admin_routes.py` | `GET /admin/skills`, `GET /admin/adapters/{name}/skills` |
| Response schemas | `server/models/schema.py` | `SkillInfo`, `SkillsResponse`, `AdapterSkillsResponse` |
| Image skill adapter config | `config/adapters/image.yaml` | `image-generator` |
| Example consumer adapter | `config/adapters/hr.yaml` | `intent-sql-sqlite-hr` |

### ProcessingContext fields

| Field | Type | Description |
|-------|------|-------------|
| `requested_skill` | `Optional[str]` | The skill name from the request (`None` if no skill) |
| `original_adapter_name` | `Optional[str]` | Adapter authenticated by the API key before skill routing |

These fields are available to all pipeline steps and can be used for logging, audit trails, or conditional logic.

---

## Testing

```bash
# From repo root — run the skill-specific unit tests
/path/to/venv/bin/python -m pytest \
  server/tests/test_adapters/test_adapter_capabilities.py::TestAvailableSkills \
  server/tests/chat_handlers/test_request_context_builder.py::TestSkillRouting \
  server/tests/test_config/test_config_management.py::TestSkillRegistry \
  -v
```

### End-to-end verification checklist

1. Server starts with `image-generator` enabled and `image-generation` in HR adapter's `available_skills`.
2. `GET /admin/skills` returns `image-generation`.
3. `GET /admin/adapters/intent-sql-sqlite-hr/skills` (with HR API key) returns `["image-generation"]`.
4. `POST /v1/chat` with HR API key and `skill: "image-generation"` returns `image` + `image_format` with no LLM text.
5. Same request without `skill` field returns normal HR retrieval response — pipeline unchanged.
6. `POST /v1/chat` with `skill: "image-generation"` on an adapter that has no `available_skills` → error response.
7. `POST /v1/chat` with `skill: "nonexistent-skill"` → error response.
