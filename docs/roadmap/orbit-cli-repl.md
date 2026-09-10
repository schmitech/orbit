# ORBIT CLI — REPL Client

## Summary

A small terminal REPL for ORBIT: connect to a server, pick an agent, chat with
streaming output, attach files with `@path`. Deliberately far simpler than
OrbitChat.

**No config files, no `.env`, no profiles, no keychain, no proxy.** The CLI is
run by a human on their own machine against a server they chose, so the API
key is passed directly and no effort is spent hiding it from the process that
is using it. That is the one big simplification the browser could never make.

Built on `@schmitech/chatbot-api` (`clients/node-api`), which already covers
everything below except artifact downloads.

New package: **`clients/orbit-cli`** (Node 20+, TypeScript). Not a workspace
member — the repo has no root Node workspace config.

---

## Connecting

Two inputs, three sources, checked in order:

1. Flags — `orbit-chat --url http://localhost:3000 --key sk-...`
2. Env — `ORBIT_URL`, `ORBIT_API_KEY`
3. Interactive prompt on first run if either is missing

Nothing is written to disk in v1 — not the key, not history, not sessions. A
run is self-contained. (Remembering the last URL is an easy later addition;
it is not needed to make the tool useful.)

Prefer the env var over `--key`: a flag lands in shell history. That is the
only security note the CLI makes.

---

## `/agents` — what it can and cannot do

This was checked against the server, because the obvious design does not work.

**The chat adapter is derived from the API key.** `routes_configurator.py:409`
resolves `adapter_name` via `get_adapter_for_api_key`; nothing in the chat
request body or headers can override it. `X-Adapter-Name` is an OrbitChat-proxy
concept — the SDK sends it in exactly one place
(`clients/node-api/api.ts:666`, autocomplete) and `streamChat` has no
middleware path at all. So one key = one adapter, and no amount of client work
changes that.

**But skills route across adapters.** An adapter with
`capabilities.expose_as_skill: true` is registered as a skill, and passing
`skill` on a chat request re-targets the call to that skill's adapter
(`routes_configurator.py:836-839`). `streamChat` already accepts a `skill`
argument.

**And skills are discoverable with no auth at all.**
`GET /admin/adapter-skills` (`discovery_routes.py:301`) returns every
registered skill with `name`, `description`, `adapter_name`, `enabled` — no
API key required. The SDK exposes it as `getAllSkills()`.

So `/agents` works exactly as wanted, backed by skills rather than adapters:

- On connect, the CLI calls `getAllSkills()` and `getAdapterInfo()`.
- `/agents` lists the key's own adapter (the default) plus every enabled skill.
- Picking one sets the `skill` argument on subsequent turns. No reconnect, no
  new client, no second key.
- If the server has no skills registered, `/agents` shows the single adapter
  behind the key and says so. The CLI is then single-agent, which is honest
  and still fine.

`GET /admin/adapters/capabilities` does list *all* adapters and accepts any
valid API key (`permission_or_api_key` returns true for a valid key regardless
of permission). It is deliberately **not** used: listing adapters the key
cannot actually chat with would offer choices that fail on selection.

---

## Command surface

Small on purpose.

| Input | Effect |
|---|---|
| *plain text* | send a turn |
| `@path/to/file` | inline in the message — uploads and attaches |
| `/agents` | list agents; `/agents <name>` or number to select |
| `/models`, `/model <id>` | `getAllModels()`; set model for later turns |
| `/new` | new session |
| `/clear` | clear the screen only |
| `/help`, `/exit` | local |
| `Ctrl+C` | cancel the in-flight turn; again to exit |
| `Ctrl+D` | exit |

Not included: profiles, login, feedback, threads, voice, history deletion,
i18n, resume. Each can be added later; none is needed for the tool to be worth
using.

### `@` attachments

`@` replaces `/upload`. Typing `@` opens filename completion; the path is
uploaded via `uploadFile()` when the turn is sent, and its file id rides along
on that turn. Attachments are per-turn by default — they do not silently
persist across every subsequent message, which removes the need for a
`/detach` command.

`uploadFile()` takes a Web `File` (`api.ts:1939`), so the CLI reads the path
and constructs one. Node 20+ is therefore the floor.

---

## Phases

### Phase 0 — Connect ✅ Complete

- Package scaffold, tsc + tsup, `bin/orbit-chat.js`, `engines: node >=20`.
- Connection resolution (flags → env → prompt).
- A thin named-options wrapper around the SDK's 15-argument positional
  `streamChat()`. The only place the CLI touches that signature.
- Decide: `file:` link to `../node-api` during development, or the published
  npm package. (Recommendation: `file:` link, pinned at release.)
- `orbit-chat --health`.

**Verify:** `--health` returns ok against a local server; a bad key gives one
clear line, not a stack trace; missing url/key prompts rather than crashing.

Shipped in `clients/orbit-cli`. `--health` calls both `getHealth()` (proves
the server is reachable) and `getAdapterInfo()` (proves the key is valid) so
a bad key fails loudly instead of reporting healthy. `args.ts` rejects a
missing or flag-like value for `--url`/`--key` rather than silently consuming
the next flag. Verified against a live local ORBIT server: valid key, invalid
key, unreachable server, env-var resolution, and malformed flags all produce
the documented exit code and message.

---

### Phase 1 — One-shot mode

Built before the REPL: it is the scriptable path and the substrate the tests
drive. **It must not initialize any TUI framework.**

- `orbit-chat "question"`, and `cat f | orbit-chat -`.
- Plain text out, no ANSI.
- stdout carries the response only; errors and progress go to stderr.
- Exit codes: `0` ok, `1` server error, `2` usage, `3` auth, `4` network,
  `130` cancelled.
- `--agent <name>` and `--model <id>` flags so scripts skip the REPL.

**Verify:** `orbit-chat "hi" | cat` produces clean text with no escape
sequences; a broken pipe exits quietly; exit codes tested per class.

*~1 day.*

---

### Phase 2 — The REPL

- Prompt line + streaming transcript.
- Session UUID per run; `/new` rotates it.
- **Cancellation uses both mechanisms.** On `Ctrl+C`: abort the local
  `AbortController` (the only thing that works before the first `request_id`
  chunk arrives), then best-effort `stopChat(sessionId, requestId)` if an id
  has arrived, mark the partial reply cancelled, restore the prompt. Second
  `Ctrl+C` exits.
- In-memory prompt history with up/down. Not persisted in v1.
- Framework: timebox a half-day spike on Ink before committing. Ink is the
  likely answer, but stable scrollback and resize handling need proving. Phase
  1 is unaffected by the choice either way.

**Verify:** cancel before *and* after the first `request_id` chunk — both
restore the prompt and leave the session usable; context is retained across
turns after a cancel.

---

### Phase 3 — Agents, models, files, rendering

- `/agents` and `/models` as described above.
- `@path` attachments with filename completion.
- Markdown → ANSI: headings, lists, emphasis, code fences with syntax
  highlighting (`cli-highlight`), tables. Streaming-safe: buffer by block and
  re-render only the tail so partial fences do not flicker. Respect
  `NO_COLOR` and non-TTY.
- Artifacts, both shapes the SDK returns: inline base64 (`image`, `video`,
  `document`, `audio` with their `*_format` fields) and URLs (`image_url`,
  `video_url`, `document_url`, `generated_audio_url`). Written to
  `./.orbit-out/`, path printed.
  Downloading a URL is the one thing the SDK cannot do — add
  `downloadArtifact(url)` to `@schmitech/chatbot-api` in the same change
  rather than growing a parallel HTTP layer in the CLI.

**Verify:** golden-file renderer tests over fixture streams chunked mid-fence
and mid-table; `@file.pdf` produces a grounded answer; both artifact paths
write byte-correct files; selecting an agent visibly changes which backend
answers.

---

## Testing

Two tiers, no more:

1. **Unit** — connection resolution, the `streamChat` options wrapper,
   `@`-path parsing, artifact decoding, exit-code mapping, renderer snapshots
   over fixture SSE streams (including malformed and truncated ones).
2. **PTY** (`node-pty`) — `SIGINT` in both cancellation windows, `Ctrl+D`,
   resize, non-TTY output purity, tab completion.

Live-server checks stay a separate integration script, not part of
`npm test`.

---

## Deferred

Everything OrbitChat does that this does not, in rough order of likely demand:
persisted history and `--resume`, `/feedback`, bearer-token login (needs an
`accessToken` option on `ApiClientConfig` — `streamChat` sends only the API
key today), autocomplete suggestions, multi-key multi-adapter switching,
conversation threads, voice, i18n, rich rendering (mermaid, KaTeX, charts).
