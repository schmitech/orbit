# Manual/Integration Check: Grounded Real-Time Voice (OpenAI Realtime + Retriever Adapters)

Steps to verify after implementation, in order. See
[`grounded-realtime-voice.md`](grounded-realtime-voice.md) for the
architecture this exercises.

## 1. Confirm the demo adapter is loaded

`config/adapters/qa.yaml` already defines `qa-realtime-voice`, grounded
against the existing `qa-sql` retriever adapter (SQLite `city` QA table,
`examples/city-qa-pairs.json`):

```yaml
- name: "qa-realtime-voice"
  enabled: true
  type: "openai_realtime"
  config:
    grounding_adapter: "qa-sql"
    grounding_tool_name: "lookup_answer"
```

Confirm `config/adapters.yaml` imports `adapters/qa.yaml`, and that `qa-sql`
itself is `enabled: true` right above it in the same file (it's the adapter
actually queried — `qa-realtime-voice` never retrieves on its own).

## 2. Set the OpenAI API key and start the server

```bash
export OPENAI_API_KEY=sk-...
python3 server/main.py
```

Check startup logs for adapter registration errors on `qa-realtime-voice` or
`qa-sql` — a bad `domain_config_path`/`database` path in `qa-sql`'s config
would surface here, before any voice traffic is sent.

## 3. Point the node client at the adapter

```bash
cd clients/openai-realtime-voice
cp .env.example .env.local
```

Edit `.env.local`:

```bash
VITE_ORBIT_SERVER_URL=ws://localhost:3000
VITE_ADAPTER_NAME=qa-realtime-voice
```

```bash
npm install
npm run dev
```

Open the printed local URL (Vite default `http://localhost:5175`) and start
a conversation.

## 4. Wire up the voice persona (optional)

The realtime handler only loads a persona via `system_prompt_id`, which is
resolved from an API key — not set directly in `qa-realtime-voice`'s adapter
config. To use the voice-adapted city persona
(`examples/prompts/audio/city-assistant-realtime-voice-prompt.md`) instead
of the default system prompt:

```bash
./bin/orbit.sh key create \
  --adapter qa-realtime-voice \
  --name "City Voice Client" \
  --prompt-name "City Voice Assistant" \
  --prompt-file examples/prompts/audio/city-assistant-realtime-voice-prompt.md
```

`--name` is the key's own client label (required); `--prompt-name` +
`--prompt-file` create the stored system prompt and bind it to this key in
one step. This prints an API key bound to both the adapter and the prompt.
Set it in the client's `.env.local`:

```bash
VITE_API_KEY=<key printed above>
```

Restart `npm run dev` and reconnect. Confirm the persona is loaded by
checking the server debug logs for `OpenAI Realtime loaded system prompt for
adapter 'qa-realtime-voice' (system_prompt_id=..., preview=...)` — the
preview text should match the new prompt, not the default. Skip this step
to test with the default system prompt instead.

## 5. Trigger a grounded tool call

Ask, by voice:

> "How much is the birth certificate?"

Run the server with `--log-level debug` (or set the equivalent in
`config.yaml`'s logging section) to see the grounding log lines below.

Confirm:
- A brief pause (the retrieval round-trip) before the spoken reply starts.
- The assistant answers with the substance of `qa-sql`'s stored answer — a
  $20 fee at the Vital Records Office — in its own natural phrasing, not a
  verbatim recitation of the stored text.
- Server logs show a line like `_handle_function_call invoking
  grounding_adapter='qa-sql' query='...'` followed by `grounding lookup
  result (N chars): '...'` — confirming the retriever actually ran and what
  it returned.
- Only **one** `done` event reaches the client for the whole turn — not one
  for the tool-call response and a second for the spoken answer (see
  Troubleshooting if you see two, or none).

## 6. Confirm ungrounded turns don't call the tool

In the same session, ask something conversational:

> "How's your day going?"

Confirm a normal spoken reply with no tool call in the logs — the model
should only reach for `lookup_answer` on factual questions, not every turn.

## 7. Confirm backward compatibility of the plain (ungrounded) adapter

Switch `VITE_ADAPTER_NAME` back to `open-ai-real-time-voice-chat` (no
`grounding_adapter` configured), restart the client, and have a short
conversation. Confirm behavior is unchanged from before this feature: no
`tools` sent in `session.update` (check server debug logs / a packet
capture if needed), no function-call branch ever taken.

## 8. Run the checks

```bash
ruff check server/
pytest server/tests/
```

## 9. Repeat the grounded check against Gemini Live

`config/adapters/qa.yaml` also defines `qa-gemini-realtime-voice`, the Gemini
counterpart of `qa-realtime-voice` — same `grounding_adapter: "qa-sql"`,
different provider (`type: "gemini_live"`, via the `google-genai` SDK).

```bash
export GOOGLE_API_KEY=...   # or GEMINI_API_KEY
python3 server/main.py --log-level debug
```

Point the node client at it:

```bash
# clients/openai-realtime-voice/.env.local
VITE_ADAPTER_NAME=qa-gemini-realtime-voice
```

Restart `npm run dev`, reconnect, and repeat step 5's check: ask *"How much
is the birth certificate?"* Confirm:
- Server logs show `Gemini Live: _handle_tool_call invoking
  grounding_adapter='qa-sql' query='...'` followed by `Gemini Live: grounding
  lookup result (N chars): '...'`.
- The assistant answers with the same $20 / Vital Records substance, spoken
  naturally.
- Small talk ("how's your day going?") still gets a normal reply with no
  tool call (step 6's check, same result expected).

Then confirm the plain `gemini-live-voice-chat` adapter (no
`grounding_adapter`) behaves like an unmodified voice chat — same
backward-compatibility check as step 7, just against the Gemini provider.

---

## Additional Test Scenarios

### A. Confidence threshold override

Add `grounding_confidence_threshold: 0.9` to `qa-realtime-voice`'s `config:`
block (temporarily) and restart. Ask a question that's only a loose
paraphrase of a stored Q&A pair (e.g. "what do I pay for a residential
parking permit thing" vs. the stored "What is the fee for a residential
parking permit?"). Confirm the higher bar makes a marginal match more likely
to fail, and the assistant says it doesn't have that information rather than
guessing. Revert the override afterward.

### B. Long retrieved answer respects `grounding_max_answer_chars`

Temporarily set `grounding_max_answer_chars: 40` on `qa-realtime-voice` and
restart. Ask the birth-certificate question again. Confirm (with debug
logging on, per step 5) the `grounding lookup result (N chars): '...'` log
line shows `N <= 40` and the printed text is a truncated snippet of the
full stored answer, not the whole thing. Confirm the assistant still
responds coherently rather than stopping mid-word audibly. Revert
afterward.

### C. Unknown/no-match question

Ask something entirely outside the `city` QA dataset:

> "What's the weather like on Mars?"

Confirm the tool call (if the model makes one) returns "I don't have
information about that." and the assistant says something equivalent
out loud, rather than hallucinating an answer or erroring out.

### D. Reusing the pattern on a different retriever domain

Temporarily point `qa-realtime-voice`'s `grounding_adapter` at
`intent-sql-postgres` (from `config/adapters/customer-orders.yaml`) instead
of `qa-sql`, update `grounding_tool_description` to describe customer/order
data, and restart. Ask an order-related question the postgres intent
templates support. Confirm the same tool-call → retrieve → speak flow works
unchanged against a completely different adapter type (intent-SQL vs.
QA-SQL), proving `grounding_adapter` genuinely generalizes. Revert to
`qa-sql` afterward.

### E. `response.done` suppression under multi-turn tool use

Ask two grounded questions back-to-back in the same session without
pausing between the assistant's replies (e.g. immediately after the
birth-certificate answer, ask "what about a dog license renewal?"). Confirm
exactly one client `done` per spoken answer — two questions should produce
two `done` events total, not four (one tool-call-turn `done` per question
being incorrectly forwarded).

## Troubleshooting

- **Client receives `done` before the spoken answer, or twice per turn**:
  means the tool-call-only `response.done` isn't being suppressed — check
  `_map_openai_event`'s `response.done` branch is inspecting `response.output`
  for `function_call`-only items (see `grounded-realtime-voice.md`).
- **Assistant reads the raw stored answer verbatim, no natural rephrasing**:
  the grounding-usage instruction appended in `_resolve_realtime_instructions`
  may not be reaching the model — check the built `instructions` string in
  debug logs includes the "call `lookup_answer`... don't read verbatim" line.
- **Tool never gets called at all**: confirm `session.update`'s `session`
  payload actually includes a `tools` array (only added when
  `config.grounding_adapter` resolves to a non-empty `GroundingConfig` —
  check for typos in the adapter name) and that `qa-sql` is `enabled: true`.
- **`ValueError: Adapter 'qa-sql' is not available`**: `grounding_adapter`
  points at a disabled or nonexistent adapter name — check
  `DynamicAdapterManager`'s config_manager output at startup.
- **No audio at all / immediate `error` event**: check `OPENAI_API_KEY` is
  set in the *server's* environment (not just the client's), per the base
  `openai_realtime` bridge's own troubleshooting notes.
