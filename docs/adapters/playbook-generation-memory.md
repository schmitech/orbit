# Manual/Integration Check: Generation Memory (Multi-Turn Refinements)

Steps to verify that image/video/document generation adapters remember the
*effective prompt* (or, for documents, the full JSON spec) from the previous
turn in a session, so a follow-up like *"make the dog wear a space suit"* or
*"add a chart to the sales section"* refines what was actually generated
instead of being interpreted as a brand-new, context-free request. See
[`skills.md`](skills.md#image-generation-prompt-rewriting) for the prompt-rewrite
design this builds on.

Generation memory is **on by default** — it piggybacks on
`conversation_threading` (enabled by default in `config/config.yaml`) and
needs no adapter YAML changes.

## 1. Confirm the prerequisite is on

`config/config.yaml`:

```yaml
conversation_threading:
  enabled: true              # ← must be true (default)
  dataset_ttl_hours: 24      # how long a turn's memory survives
  storage_backend: "sqlite"  # cache, sqlite, mongodb, postgres — any backend works
```

No adapter config changes are required — `image-generator`, `video-generator`,
and `pdf-generator` (`config/adapters/{image,video,pdf}-generator.yaml`) pick
this up automatically. If `conversation_threading.enabled` is `false`,
generation memory no-ops and each turn is treated as brand-new — this is the
behavior to confirm in step 7.

## 2. Start the server and create API keys

```bash
python3 server/main.py
# in another shell:
./bin/orbit.sh key create --adapter image-generator --name "Generation memory test (image)"
./bin/orbit.sh key create --adapter video-generator --name "Generation memory test (video)"
./bin/orbit.sh key create --adapter simple-chat-with-files --name "Generation memory test (PDF skill)"
```

Export the returned keys:

```bash
export IMG_KEY=<image-generator key>
export VID_KEY=<video-generator key>
export FILES_KEY=<simple-chat-with-files key>
```

## 3. Image follow-up refinement

```bash
export SID=genmem-img-1

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $IMG_KEY" -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"Generate an image of a dog in a forest."}]}' \
  | jq '{image_revised_prompt}'
```

Then, **same session id**:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $IMG_KEY" -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"make the dog wear a space suit"}]}' \
  | jq '{image_revised_prompt}'
```

**Expected:** the second `image_revised_prompt` describes a dog *and* a space
suit (e.g. "...a fluffy dog wearing a miniature space suit..."), not a
prompt built from "make the dog wear a space suit" alone. Server log at
`DEBUG` shows `has_memory=True` on the second request:

```
Image generation context: context_messages=0, formatted_context_len=0, has_memory=True
```

(`context_messages=0` is expected — `image-generator` is called directly,
not via skill routing, so chat history isn't involved; memory comes purely
from the stored dataset.)

## 4. Video follow-up

Same pattern, `video-generator`:

```bash
export SID=genmem-vid-1

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $VID_KEY" -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"a cat chasing a laser pointer"}]}' \
  | jq '{video_revised_prompt}'

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $VID_KEY" -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"now set it at night with the cat wearing a tiny hat"}]}' \
  | jq '{video_revised_prompt}'
```

**Expected:** the second `video_revised_prompt` still describes the cat and
laser pointer from turn 1, plus night setting and hat from turn 2.

## 5. Document follow-up (via the PDF skill)

`pdf-generator` isn't its own OrbitChat tile — it's invoked as a skill from a
conversational adapter. Use `simple-chat-with-files`:

```bash
export SID=genmem-doc-1

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $FILES_KEY" -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"Write a one-page Q1 sales report."}],"skill":"PDF"}' \
  | jq '{document_revised_prompt}'

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $FILES_KEY" -H "X-Session-ID: $SID" \
  -d '{"messages":[{"role":"user","content":"Add a bar chart showing revenue by region."}],"skill":"PDF"}' \
  | jq '{document_revised_prompt}'
```

**Expected:** the second document keeps the sections from turn 1 (executive
summary, etc.) and adds the requested chart — download it (`document_url` in
the full response, not just the `jq` filter above) and open it to confirm,
rather than trusting the title alone. Document memory stores the **full JSON
spec**, not just a text prompt, so refinements can add/modify sections
directly instead of the rewrite LLM re-inventing the whole document from a
one-line prompt.

## 6. Session isolation — memory must not leak across sessions

Repeat the second image request from step 3 with a **different**
`X-Session-ID` (no first turn in that session):

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $IMG_KEY" -H "X-Session-ID: genmem-img-fresh" \
  -d '{"messages":[{"role":"user","content":"make the dog wear a space suit"}]}' \
  | jq '{image_revised_prompt}'
```

**Expected:** no dog/forest reference — the model has nothing to refine, so
either it enriches "space suit" generically or the rewrite is skipped
entirely (there's no history, no context, no memory to trigger a rewrite).
Server log shows `has_memory=False`.

## 7. Backward-compatibility check — feature fully gated

Set `conversation_threading.enabled: false` in `config/config.yaml`, restart,
and repeat step 3. **Expected:** the second turn no longer references the
forest dog — each request is generated independently, proving the feature
adds behavior on top of the existing pipeline rather than replacing it.
Restore `enabled: true` afterward.

## 8. OrbitChat UI

1. Open the **AI Image Generator** tile, send *"a dog in a forest"*, wait
   for the image, then send *"make the dog wear a space suit"* in the same
   chat. The second image should visibly be a refinement (same dog, same
   forest, now in a space suit) rather than an unrelated scene.
2. Repeat with the **AI Video Generator** tile using an analogous two-turn
   refinement.
3. Open **Simple AI Chat (Multimodal)**, use the `/` picker to invoke `PDF`
   with *"write a short report on renewable energy"*, then follow up
   (still via the `PDF` skill) with *"add a section comparing solar and
   wind"*. The regenerated PDF should contain the original sections plus the
   new one.
4. Start a **new chat** (fresh session) on any of the above tiles and send a
   refinement-style message first (*"make it wear a space suit"* with no
   prior turn). Confirm it doesn't silently reuse another chat's memory —
   OrbitChat's session id changes per chat, so this should behave like step 6.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Follow-up ignores the previous turn entirely | `conversation_threading.enabled` is `false`, or requests are using different `X-Session-ID` values (OrbitChat rotates session id per chat — make sure you're in the same chat). |
| `has_memory=False` on a turn that should have memory | Check the cache/database backend is actually up (`internal_services.cache` for `storage_backend: cache`, or the app database for `sqlite`/`mongodb`/`postgres`) — memory storage/retrieval failures are logged at `DEBUG` and swallowed by design (a broken cache must never break generation itself). |
| Memory from an old, unrelated conversation leaks in | Two different logical conversations are reusing the same session id — check the client isn't hardcoding `X-Session-ID`. |
| Document refinement rewrites the whole report from scratch instead of amending it | Check the rewrite LLM's response — the "Previous document spec" block only *informs* the rewrite, it doesn't force the model to preserve prior sections verbatim. Tune `config/rewriters-prompts.yaml`'s `document` template rules if this happens consistently. |
| Memory persists across a much longer time than expected, or expires too soon | `conversation_threading.dataset_ttl_hours` (default 24h) controls this — it's shared with intent-SQL thread datasets. |

## Unit tests

```bash
# From repo root, using the venv python:
venv/bin/python -m pytest server/tests/test_pipeline_steps/ -v
venv/bin/python -m pytest server/tests/test_document_generation/test_document_generation.py -k Memory -v
venv/bin/python -m pytest server/tests/test_threads/test_thread_dataset_service.py -v
```

Covers: the `get_generation_memory`/`store_generation_memory` round trip
through a real sqlite-backed `ThreadDatasetService` (not just mocks),
image/video step rewrite-and-store behavior, document spec memory, and the
concurrent-write race in the database-backend upsert path (two turns landing
at nearly the same time must not silently drop one).
