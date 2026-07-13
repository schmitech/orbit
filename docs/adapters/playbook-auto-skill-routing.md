# Manual/Integration Check: Automatic Skill Intent Detection

Steps to verify the hybrid skill-intent router end-to-end, first with `curl`
and then in OrbitChat. Run them in order. See
[`auto-skill-intent-detection.md`](auto-skill-intent-detection.md) for the design
and [`skills.md`](skills.md#automatic-intent-detection) for the feature docs.

The feature is **off by default** (two-switch gate). These steps turn it on for
the `simple-chat-with-files` adapter.

## 1. Enable the global gate

In `config/config.yaml`, flip the `skill_routing` gate on:

```yaml
skill_routing:
  auto_detect: true               # ← set to true
  embedding_threshold: 0.35
  router_provider: "cohere"       # small/fast confirm LLM (must have an API key configured)
  router_model: "command-r7b-12-2024"
```

The confirm step needs a working LLM. `cohere`/`command-r7b-12-2024` is the
default; if you don't have a Cohere key, either set `router_provider` to a
provider you do have (e.g. `openai`, `gemini`), or **delete** `router_provider`
entirely to reuse the adapter's own `inference_provider`.

The embedding pre-filter uses the consumer adapter's `embedding_provider` when
set (for `simple-chat-with-files` that is `openai` / `text-embedding-3-small`),
otherwise the global `embedding.provider` in `config/embeddings.yaml` — make
sure that provider has a key too.

## 2. Confirm the adapter opt-in

`config/adapters/multimodal.yaml`'s `simple-chat-with-files` already ships with
the flag set and the in-scope skills listed:

```yaml
- name: "simple-chat-with-files"
  capabilities:
    auto_skill_routing: true          # ← per-adapter opt-in (already set)
    available_skills:
      - "Image"
      - "Video"
      - "Audio"
      - "PDF"
      - "Word"
      - "Excel"
      - "PowerPoint"
      - "web-search"
      - "Fetch"
      - "Markdown"
      # (HR / business-analytics also listed — but retrieval skills are NOT auto-routed)
```

## 3. Start the server and create an API key

```bash
python3 server/main.py
# in another shell:
./bin/orbit.sh key create --adapter simple-chat-with-files --name "Auto-routing test"
```

Export the returned key for convenience:

```bash
export ORBIT_KEY=<the-key-just-created>
export SID=auto-route-1
```

## 4. Positive case — plain message auto-routes to a skill

No `skill` field. The router should infer **PDF** and return a document:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"Can you create a PDF about the solar system?"}]}' | jq 'keys'
```

**Expected:** the JSON contains `document` and `document_format: "pdf"` (not a
plain text `response` only). Server log shows:

```
DEBUG - Auto-detected skill 'PDF' for adapter 'simple-chat-with-files'
```

Try the other in-scope skills (fresh session id each time so history doesn't skew it):

| Message | Expected skill / field |
|---------|------------------------|
| "draw a picture of a red bicycle" | `Image` → `image` + `image_format` |
| "read this out loud: hello world" | `Audio` → `generated_audio` / audio url |
| "put these numbers in a spreadsheet: 1,2,3" | `Excel` → `document_format: "xlsx"` |
| "make a slide deck about our roadmap" | `PowerPoint` → `document_format: "pptx"` |
| "search the web for today's headlines" | `web-search` → text `response` with citations |

## 5. Negative case — ordinary question stays conversational

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: auto-route-neg" \
  -d '{"messages":[{"role":"user","content":"What is retrieval-augmented generation?"}]}' | jq 'keys'
```

**Expected:** a normal text `response`, **no** `document`/`image` field. Because
the embedding pre-filter finds no candidate, the confirm LLM is **not** called
(no `Auto-detected skill` log line). This is the fast path.

## 6. Disambiguation

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: auto-route-dis" \
  -d '{"messages":[{"role":"user","content":"turn this into a spreadsheet"}]}' | jq '.document_format'
```

**Expected:** `"xlsx"` (Excel), not `"pdf"` — the confirm LLM disambiguates
between the similar document skills that both survive the pre-filter.

## 7. Delegate to ORBIT only (no explicit user invocation)

To let ORBIT auto-route while forbidding users from calling skills themselves,
move the skills from `available_skills` into `auto_routable_skills`:

```yaml
capabilities:
  auto_skill_routing: true
  available_skills: []            # / picker shows nothing; explicit skill= is rejected
  auto_routable_skills:
    - "PDF"
    - "Image"
    - "web-search"
```

Verify:

```bash
# Auto-routing still works (no skill field):
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: auto-only-1" \
  -d '{"messages":[{"role":"user","content":"make a pdf of this"}]}' | jq '.document_format'
# => "pdf"

# But an EXPLICIT skill request is now rejected:
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: auto-only-2" \
  -d '{"messages":[{"role":"user","content":"make a pdf"}],"skill":"PDF"}' | jq
# => error: "Skill 'PDF' is not available for adapter ..."
```

### Variant: one adapter, mixed access (`config/adapters/passthrough.yaml` → `simple-chat`)

`simple-chat` shows the two lists side by side: generation + web skills are
ORBIT-only (`auto_routable_skills`), while the retrieval skills and `mcp-agent`
stay explicitly invokable (`available_skills`). It also ships `mcp_tools: true`
(business-sample), so it exercises coexistence with opportunistic MCP too.

```bash
./bin/orbit.sh key create --adapter simple-chat --name "Auto-routing test (passthrough)"
export PT_KEY=<the-key-just-created>
```

1. **Auto-route an ORBIT-only skill** (no `skill` field):
   ```bash
   curl -s -X POST http://localhost:3000/v1/chat \
     -H "Content-Type: application/json" -H "X-API-Key: $PT_KEY" \
     -H "X-Session-ID: pt-1" \
     -d '{"messages":[{"role":"user","content":"make a pdf about the water cycle"}]}' | jq '.document_format'
   # => "pdf"
   ```
2. **Explicit call to an ORBIT-only skill is rejected** (it's not in `available_skills`):
   ```bash
   curl -s -X POST http://localhost:3000/v1/chat \
     -H "Content-Type: application/json" -H "X-API-Key: $PT_KEY" \
     -H "X-Session-ID: pt-2" \
     -d '{"messages":[{"role":"user","content":"x"}],"skill":"PDF"}' | jq
   # => error: "Skill 'PDF' is not available for adapter ..."
   ```
3. **Explicit call to a still-allowed skill works** (stayed in `available_skills`):
   ```bash
   curl -s -X POST http://localhost:3000/v1/chat \
     -H "Content-Type: application/json" -H "X-API-Key: $PT_KEY" \
     -H "X-Session-ID: pt-3" \
     -d '{"messages":[{"role":"user","content":"latest tender notices"}],"skill":"tender-notices"}' | jq 'keys'
   # => normal retrieval response (not rejected)
   ```
4. **Coexistence with opportunistic MCP** (optional): a CRM-style question with no
   skill match — e.g. *"what's the health score of the top EMEA account?"* — falls
   through to the `business-sample` MCP tools when `mcp_client.enabled` +
   `mcp_client.allow_opportunistic` are set (see
   [playbook-mcp-tool-loop.md](playbook-mcp-tool-loop.md)). The auto-routed skills
   above and the MCP loop never fire on the same turn.

## 8. Manual override still wins

Send an explicit `skill` that differs from what the text implies — the explicit
skill must be honored and detection skipped entirely:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: auto-route-override" \
  -d '{"messages":[{"role":"user","content":"make a pdf"}],"skill":"Image"}' | jq 'keys'
```

**Expected:** an `image` result (the explicit `skill: "Image"`), NOT a PDF.

## 9. Backward-compatibility check

Set `skill_routing.auto_detect: false` again (or unset `auto_skill_routing` on
the adapter) and repeat step 4. **Expected:** the "create a PDF…" message now
returns a normal conversational text response — proving the feature is fully
gated and off by default.

## 10. OrbitChat UI

1. Point OrbitChat at an API key for `simple-chat-with-files` and open a new chat.
2. **Without** touching the `/` picker, type: *"Can you make a PDF of this conversation?"* and send.
   - The response renders as a downloadable document, same as if you had picked `/PDF`.
3. Type an ordinary question (*"Explain how vector search works"*). It answers as normal chat — no skill triggered.
4. Open the `/` picker and explicitly pick a skill, then send. It still works and overrides any inference (step 7).

> **Note:** the `/` picker is suppressed for threading adapters (intent-SQL);
> auto-routing is intended for conversational/multimodal adapters like
> `simple-chat-with-files`, which is why it's enabled there.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Every plain message answers as normal chat, never a skill | `skill_routing.auto_detect` is `false`, or `auto_skill_routing` not set on the adapter (both required). |
| `Auto-detected skill` never logs even for obvious requests | Embedding provider has no key / failed to init (router degrades to None on error — check logs), or `embedding_threshold` too high. |
| Confirm step errors in logs, routing silently disabled | `router_provider` has no valid API key. Switch it to a configured provider or delete it to reuse the adapter's provider. |
| Wrong skill chosen among similar ones | Tune the skill's `routing_examples`, or lower/raise `embedding_threshold`. |
| Normal chat feels slower after enabling | The embedding call runs every turn for the opted-in adapter. Keep `available_skills` scoped; the confirm LLM only runs on a pre-filter hit. |

## Unit tests

```bash
# From repo root:
venv/bin/python -m pytest server/tests/test_services/test_skill_intent_router.py -v
```

Covers: positive routing, the negative fast-path (asserts the confirm LLM is
**not** called), disambiguation, confirm-answer parsing (exact / wrapped /
`NONE` / out-of-list), and filtering retrieval skills out of the candidate set.
