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

The conversation messages are still passed to the skill adapter, giving it full context of what the user was asking. The skill adapter decides how to use that context — image generation enriches the user's request into a detailed image prompt using conversation history and any thread-cached data (see [Image Generation Prompt Rewriting](#image-generation-prompt-rewriting) below).

---

## Configuration

### Exposing an Adapter as a Skill

Add three fields under the adapter's `capabilities` section:

```yaml
- name: "image-generator"
  enabled: true
  type: "image_generation"
  datasource: "none"
  adapter: "multimodal"
  image_provider: "gemini"                       # openai or gemini (see config/image.yaml)
  capabilities:
    expose_as_skill: true                        # marks this adapter as a skill
    skill_name: "image-generation"               # identifier used in requests
    skill_description: "Generate images from text descriptions using AI"
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

> **Note:** these three fields must live under `capabilities`. The earlier top-level form has been removed and is no longer recognized.

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

Use this endpoint to build a skill picker in the UI (see [UI Integration](#ui-integration)).

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

## UI Integration

### OrbitChat skill picker

OrbitChat implements a built-in skill picker:

1. **On load**, call `GET /admin/adapters/{name}/skills` and `GET /admin/skills` to fetch available skills for the current adapter.
2. **Trigger**: typing `/` as the first character of a message opens the skill picker. Continuing to type (e.g. `/ima`) filters by skill name or description in real time.
3. **Select**: clicking or pressing Enter on a skill closes the picker, attaches a skill badge to the message input, and clears the text field.
4. **Send**: submitting the message sends `skill: "<skill-name>"` in the request body alongside the user's message.
5. **Response rendering**: if the response includes `image` + `image_format`, the client renders the image inline instead of text.

### Threading adapters

For adapters that have `supports_threading: true` (e.g. intent-SQL adapters), the skill picker is **suppressed in the main conversation**. Skills require retrieved data to be useful, and that data only exists inside a thread. Once the user opens a thread (branched from a retrieval response), skills become available again within that thread context.

This behaviour is driven by the `supportsThreading` field returned in `GET /admin/adapters/info` (see below). The front-end `useSkills` hook reads this field and sets `isActive = false` when it is `true`, preventing skill fetch and picker display.

### Adapter info endpoint

`GET /admin/adapters/info` now includes a `supportsThreading` field in its response:

```json
{
  "client_name": "HR Assistant",
  "adapter_name": "intent-sql-sqlite-hr",
  "model": null,
  "isFileSupported": false,
  "supportsThreading": true
}
```

The UI reads this to decide whether to show the skill picker.

### Generic integration flow

1. Call `GET /admin/adapters/{name}/skills` to get the allowlist for the current adapter.
2. Call `GET /admin/skills` to get display metadata (`name`, `description`) for each skill.
3. Merge the two responses to build your picker UI.
4. When the user selects a skill and submits a message, send `skill: "<skill-name>"` in the request body.
5. The response will contain `image` / `image_format` instead of a text `response`. Render accordingly.

---

## Image Generation Prompt Rewriting

When an image-generation skill request arrives, `ImageGenerationStep` does not send the user's raw message directly to the image model. Instead, if conversation history or thread-cached data is available, it first calls an auxiliary LLM to rewrite the message into a richer, more descriptive image prompt.

**When rewriting is triggered:** `context.context_messages` is non-empty (there is conversation history) **or** `context.formatted_context` is non-empty (a thread's cached dataset was loaded).

**What the rewriter does:**

1. Takes up to the last 6 conversation turns as history context (capped to avoid blowing the context window).
2. Strips the current user message from the history tail if it appears there to avoid duplication.
3. Includes any thread-cached retrieval data (`formatted_context`) as additional context for the LLM.
4. Asks the LLM to produce a single, standalone, richly descriptive image prompt — resolving vague references like "draw it" or "visualize this chart" using the history/context.
5. Always enriches the prompt with visual details (subjects, setting, art style, lighting, mood, composition) even when the user already wrote a descriptive prompt.

**Fallback:** if the rewriter call fails, or the rewritten string is shorter than 10 characters, the original user message is used unchanged.

The rewritten prompt is what gets sent to the image provider (DALL-E 3 / Imagen). The provider may further revise it (e.g. DALL-E 3 content policy rewrites), which is returned as `image_revised_prompt` in the response.

---

## Adding a New Skill

To add a second skill (e.g., video generation):

**1. Create or configure the skill adapter** (e.g., `config/adapters/video.yaml`):

```yaml
adapters:
  - name: "video-generator"
    enabled: true
    type: "video_generation"          # a future adapter type
    datasource: "none"
    adapter: "conversational"
    capabilities:
      expose_as_skill: true
      skill_name: "video-generation"
      skill_description: "Generate short videos from text prompts"
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

No server code changes are required. ORBIT discovers skill adapters at startup by scanning for `expose_as_skill: true` under each adapter's `capabilities`.

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
| `supportsThreading` in adapter info | `server/services/api_key_service.py` | `get_adapter_info` returns `supportsThreading` from capabilities |
| Image skill adapter config | `config/adapters/image.yaml` | `image-generator` |
| Example consumer adapter | `config/adapters/hr.yaml` | `intent-sql-sqlite-hr` |
| UI skill picker component | `clients/orbitchat/src/components/SkillPicker.tsx` | Filtered dropdown, icon mapping, selected state |
| UI skill hook | `clients/orbitchat/src/hooks/useSkills.ts` | Fetches skills, caches 60 s, gates on `supportsThreading` |
| UI skills service | `clients/orbitchat/src/services/skillsService.ts` | Thin API wrapper for skills endpoints |
| UI API client | `clients/orbitchat/src/apiClient.ts` | `skill` param in `streamChat`, `getAdapterSkills`, `getAllSkills` |

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
