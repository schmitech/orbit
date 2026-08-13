# Token-Optimization Regression Playbook

Manual regression checklist for the changes tracked in
`docs/roadmap/token-optimization-plan.md` (chart gating, prompt-prefix
caching, cache-token-aware pricing, MCP tool relevance filtering), run
against a live ORBIT server + the OrbitChat client, using the
`simple-chat-with-files` adapter in `config/adapters/multimodal.yaml`.

Each phase below touches shared code (`prompt_builder.py`,
`_utils.py::record_usage`, `llm_inference.py`, `mcp_agent.py`), so a
regression in one phase can show up on any adapter — this walks the paths
most likely to be affected first, then a broader sanity pass.

## 0. Before you start

`supports_charts: true` is set on both `simple-chat-with-files` and `simple-chat-with-files-audio`
in your current `config/adapters/multimodal.yaml`, and `simple-chat-with-files-audio` is present —
Section 2 (chart gating) and audio-upload coverage both apply as written; no adapter-config gap to
work around this pass.

**Config sanity check** (run from `server/`, using the venv):
```bash
../venv/bin/python -c "import yaml; yaml.safe_load(open('../config/adapters/multimodal.yaml')); yaml.safe_load(open('../config/mcp_clients.yaml')); yaml.safe_load(open('../config/pricing.yaml')); print('ok')"
```

**MCP tool count check** — the selector (Phase 3) only filters when a request's tool count exceeds
`mcp_clients.tool_selection.max_tools` (default 15). `simple-chat-with-files` only allowlists
`mcp_servers: ["business-sample"]`, which likely exposes well under 15 tools, so the filter will
never actually trigger in normal use. To exercise the filtering path itself (Section 4), temporarily
lower the cap:
```yaml
# config/mcp_clients.yaml
mcp_clients:
  tool_selection:
    max_tools: 1        # TEMP — forces filtering with even a small tool set; revert after testing
```
Revert this after Section 4 — leaving `max_tools: 1` in place would over-filter in production.

**Start everything:**
```bash
python3 server/main.py            # or ./bin/orbit.sh start
# in clients/orbitchat:
node bin/orbitchat.js --config orbitchat-local.yaml --open
```

**Get an admin auth token/cookie ready** for `GET /admin/audit/events` — you'll pull this up after
each test turn below. Filter by adapter/session where the endpoint supports it, otherwise just take
the newest few rows after each turn.

---

## 1. Baseline sanity (no regression from any of this)

Send a plain "hello" on `simple-chat-with-files` (no file, no chart language, no tool-triggering
language).

**Expect:**
- Normal conversational reply, no chart-instruction text or JSON leaking into the visible response.
- `GET /admin/audit/events` newest row: `prompt_tokens` present and reasonable for a short adapter
  system prompt (not the ~1,700-token pre-optimization baseline). `reported: true`.
- No errors in server logs.

This is the control turn — if this breaks, something more basic than the optimizations regressed.

---

## 2. Chart-instruction gating (Phase 1)

**2a. Non-chart turn should get the ~120-token hint, not the ~1,200-token full spec.**
Ask something ordinary, e.g. "what's 12 * 8?".
- Check server logs / audit `prompt_tokens` — should be close to the Section 1 baseline, not ~1,000
  tokens higher.

**2b. Chart-related turn should get the full spec.**
Upload a small CSV (via OrbitChat's file upload) and ask "show me a bar chart of this data by category".
- **Expect:** the model actually emits a ` ```chart ` fenced block (or a clear table if the model
  declines), i.e. the full chart-formatting instructions took effect.
- Audit `prompt_tokens` for this turn should be noticeably higher than 2a (full spec, not the hint).

**2c. Follow-up in the same chart conversation should still get the full spec via history detection.**
In the same session, follow up with "make it horizontal" (no explicit chart keyword).
- **Expect:** still gets the full instruction set (detected via the ` ```chart ` fence in recent
  history), and the model's response still respects chart formatting.

---

## 3. Prompt-prefix stability & caching (Phase 2)

Use the `claude` entry in `allowed_models` (Anthropic) for this section — it's the only provider
with an explicit `cache_control` breakpoint wired up.

**Two different code paths apply the breakpoint, and a prior pass had it wired into only one of
them:** the plain `generate()`/`generate_stream()` path, and the MCP tool-calling path
(`generate_with_tools()`), which is what actually runs on `simple-chat-with-files`'s
`mcp_tools: true` opportunistic loop for **every** turn, tool-triggering or not. Run this section
once with `mcp_tools` at whatever your adapter currently has it set to, so both paths get exercised
across your regression pass as a whole (Section 4 already covers `simple-chat-with-files`'s MCP
path specifically) — if you only ever test caching on a `mcp_tools: false` adapter, a regression in
the tool-calling path's breakpoint would go unnoticed here.

1. Start a **new session**. Send turn 1: "hello" with `model: "claude"` selected in the client.
2. Send turn 2 in the **same session**: any follow-up question.
3. Pull both turns from `GET /admin/audit/events`, or open the Admin Panel's Audit tab, click the
   inference row, and check the "Usage & cost" section of the detail dossier — a "Cached prompt
   tokens" row now appears there whenever the provider reports one (mirrors "Reasoning tokens").

**Expect:**
- Turn 1: normal `prompt_tokens`, `cached_prompt_tokens` absent or `0` (nothing to read from cache
  yet — this turn is the cache **write**).
- Turn 2: `cached_prompt_tokens > 0` — the stable prefix (system prompt + chart instruction +
  persona footer) was served from Anthropic's cache. `cost_usd` for turn 2 should reflect the
  discount (see Section 5) rather than pricing the full prompt at the standard input rate.
- If `cached_prompt_tokens` is `0`/absent on every turn indefinitely, that's a regression — the
  prefix isn't staying stable (check whether the clock/language instruction leaked back before the
  cache breakpoint).

**Also try:** OpenAI (`openai` entry) and Gemini (`gemini` entry) for 2-3 turns each — these get
passive caching with no explicit breakpoint, so you won't see `cached_prompt_tokens` populated
(neither extracts it), but conversation quality/latency should be unaffected. This is mostly a
"didn't break" check, not a "caching visibly worked" check for these two.

---

## 4. MCP tool relevance filtering (Phase 3) + the persisted-history fix

This is the newest and highest-risk area. `simple-chat-with-files` has `mcp_tools: true` and
`mcp_servers: ["business-sample"]` — opportunistic (no explicit skill needed).

**Prerequisite:** apply the temporary `max_tools: 1` override from Section 0 and restart the server,
so filtering actually triggers even with `business-sample`'s small tool set.

**4a. Basic tool call still works with filtering active.**
Ask something that should trigger one of `business-sample`'s tools (check
`config/mcp_clients.yaml`'s `business-sample` entry / the sample server's own docs for what it
exposes — e.g. an order-lookup or product-lookup style question).
- **Expect:** the tool actually gets called (check server logs for `MCP tool call: business-sample__...`)
  and the response incorporates the result. `context.sources` in the response should include a
  `mcp_tool_call` entry.
- Server log should show `MCP tool selection: kept N/M tools for adapter 'simple-chat-with-files'`
  at debug level (bump logging to DEBUG if you want to see it) confirming the selector ran.

**4b. The "already-called tool" safeguard survives a stored/reloaded session (the specific bug just fixed).**
This is the one to be most careful about — it was broken until this session's fix.

1. In session A, turn 1: trigger tool `X` (per 4a). Confirm it worked.
2. **Restart the ORBIT server** (or at minimum, don't rely on any in-memory state — the point is to
   force `context_messages` to come from a fresh `get_context_messages()` read against the database,
   not anything cached in-process).
3. In the **same session A** (same session_id / same OrbitChat conversation), send turn 2 — a message
   that does *not* obviously mention tool `X`, but where the model might reasonably want to call it
   again as a follow-up (e.g. "what about last month?" after an order-lookup).
4. Check the DB directly if you can (or via an admin history endpoint) that turn 1's assistant message
   has `metadata.mcp_tools_used` containing tool `X`'s namespaced name.
5. **Expect:** tool `X` is still available to the model on turn 2 even though `max_tools: 1` would
   otherwise filter it out — check server logs for `MCP tool selection: kept N/M tools...` where the
   count includes one more than the embedding-relevance cap, or just confirm the model can still
   call `X` successfully if it needs to.

If tool `X` is silently unavailable on turn 2 after a server restart, the fix regressed — this was
exactly the failure mode the review comment caught.

**4c. Fallback path — no embedding provider.**
Temporarily set `mcp_clients.tool_selection.enabled: false` (or point `embedding_provider`/global
`embedding.provider` at something invalid), restart, repeat 4a.
- **Expect:** falls back to the full (unfiltered) tool list — the turn must **not** fail or hang.
  Check logs for the one-time warning `MCP tool selection falling back to full tool list: ...`.
- Revert this override afterward.

**Revert the `max_tools: 1` override from Section 0 now** and restart the server before continuing.

---

## 5. Cache-token-aware pricing (Phase 4.3 / 2c)

Reuse the Anthropic turn-2 result from Section 3 (or DeepSeek, if you have `allowed_models: "deepseek"`
configured elsewhere — not present on this adapter by default).

**Expect (Anthropic):**
- `GET /admin/audit/events` for that turn shows `cached_prompt_tokens > 0` and a `cost_usd` lower
  than `prompt_tokens * input_rate_per_1m / 1_000_000` alone would predict — the cached portion
  should be priced at the `cached_input_per_1m` rate from `config/pricing.yaml` (0.30 for
  claude-sonnet), not the full 3.00 rate.
- If you have access to xAI (`grok-4.3` entry): trigger a `web_search=True` turn (search skill) and
  confirm `cached_prompt_tokens` gets populated when xAI reports a cache hit — this is the specific
  Responses-API gap fixed in the last review pass. It will price at parity (no discount tier
  configured for xAI yet), which is expected, not a bug.

---

## 6. File-upload / RAG regression (unrelated code path, shares the adapter)

Since all of the above changes flow through the same `PromptInstructionBuilder` and pipeline steps
this adapter also uses for RAG, do one pass to confirm nothing here regressed:

1. Upload a text/PDF/CSV file via OrbitChat.
2. Ask a question whose answer is only in that file.
3. **Expect:** correct retrieval-grounded answer, `retrieval_behavior: conditional` still only kicks
   in when `file_ids` is present (ask an unrelated question with no file in the same session — should
   get a normal conversational answer, not a forced "no relevant documents" response).

---

## 7. Wrap-up

- Revert every temporary config change made for this pass (`max_tools`, `tool_selection.enabled`,
  any embedding-provider override).
- Re-run the automated regression suite once more to confirm nothing was left inconsistent:
  ```bash
  cd server && ../venv/bin/python -m pytest tests/test_inference/ tests/test_pipeline_steps/ tests/test_services/ tests/chat_handlers/ -q
  ```
