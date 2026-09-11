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

### Phase 1 — One-shot mode ✅ Complete

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

Shipped in `clients/orbit-cli`: `src/one-shot.ts` streams `chunk.text` to
stdout as it arrives and returns the exit code; `src/stdin.ts` reads all of
stdin for the `-` form; a fresh `randomUUID()` session id is generated per
run (the server rejects chat requests with no `X-Session-ID`) since one-shot
has no REPL state to carry a session across turns. `Ctrl+C` aborts the
in-flight `AbortController` and exits 130. `--agent` maps to `streamChat`'s
`skill` parameter, `--model` to `model`. Verified against a live server:
plain and piped output, `-` reading stdin, an invalid key (exit 3), an
invalid model (exit 1, error on stderr only), no message given (falls
through to the Phase 2 stub, exit 0), an empty message (exit 2), a broken
pipe (exits quietly), and `Ctrl+C` mid-stream (exit 130).

---

### Phase 2 — The REPL ✅ Complete

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

Shipped in `clients/orbit-cli/src/repl.ts`, built on plain `node:readline`
rather than Ink — skipped the spike rather than timeboxing it, since a
framework choice makes sense once there's rendering complex enough to need
it (Phase 3's markdown/artifact output), and `readline`'s own terminal mode
already gives history navigation with up/down for free. `client.setSessionId`
rotates the session on `/new`; `/clear`, `/help`, `/exit` are handled
locally, and `/agents`/`/models`/`/model` report "lands in Phase 3" instead
of being sent as chat text. Cancellation: `rl.on('SIGINT')` aborts the local
`AbortController` and best-effort calls `stopChat` with the last-seen
`request_id` if one had arrived; the turn's `catch` swallows the resulting
abort and restores the prompt without exiting. A second `Ctrl+C` while idle
(no turn in flight) closes the REPL, matching `Ctrl+D`/`/exit`. Verified
over a PTY (Python's `pty` module, since `node-pty` isn't a project
dependency yet): a normal turn, `/new`, `/help`, cancelling mid-generation
(prompt restores, next turn still works), `/exit`, `Ctrl+D`, and an idle
`Ctrl+C` — all exit or recover as designed. Also re-verified Phases 0/1
still behave (`--health`, one-shot piped output, no-message-on-non-TTY).

---

### Phase 3 — Agents, models, files, rendering ✅ Complete

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

Shipped in `clients/orbit-cli`, with one SDK addition:

- **`downloadArtifact(url)`** added to `@schmitech/chatbot-api`
  (`clients/node-api/api.ts`) exactly as planned: the `*_url` fields are
  paths relative to the API base (e.g. `/api/files/{id}/content`) that
  require the same `X-API-Key` used for chat, so a plain unauthenticated
  fetch 401s — it goes through the client's existing request pipeline
  instead. `dist/` rebuilt so the `file:`-linked CLI picks it up.
- **`/agents`** (`src/agents.ts`) lists the key's own adapter plus every
  enabled skill from `getAllSkills()`, exactly as designed above; picking
  one sets `skill` on later turns and also clears any `/model` selection
  (a model choice is adapter-specific, so it shouldn't silently survive an
  agent switch).
- **`/models`/`/model`** (`src/models.ts`) call `getAdapterModels()` for the
  *current* agent's models. Fixed a real bug caught in review: the
  discovery route resolves models for the API key's own adapter regardless
  of the `adapterName` path param, *unless* a `skill` query param is also
  given — so listing models after switching to a skill was silently
  showing the base adapter's models (and a `/model` selection from that
  list could then be rejected on send). `getAdapterModels()` gained an
  optional `skill` parameter in the SDK to match the server route, and the
  CLI now always passes the current agent's `skill` alongside its
  `adapterName`.
- **`@path` attachments** (`src/attachments.ts`): `@`-tokens are extracted
  from the message, each file is read and uploaded via `uploadFile()`
  ahead of the turn, and the resulting file ids ride along as that turn's
  `fileIds` only — nothing persists onto later turns. Tab completion for
  `@` (`src/repl.ts`'s `completer`) lists filesystem entries matching the
  partial path. Used in both the REPL and one-shot mode.
- **Artifacts** (`src/artifacts.ts`): both inline-base64 and URL shapes are
  handled, written to `./.orbit-out/`. One real bug found and fixed during
  verification — a single chunk can carry *both* an inline copy and a URL
  for the same generated image, which without care wrote two identical
  files; fixed by saving a given artifact kind only once per chunk,
  preferring the inline copy (skips the extra download). Artifact paths
  print to stdout in the REPL and to stderr in one-shot mode, keeping
  one-shot's stdout reply-only per Phase 1. A second review bug: the REPL
  wrote an artifact's "Saved artifact: ..." notice as soon as it saw the
  artifact, but a chunk's `text` (typically the final chunk, with no
  trailing newline) stays buffered in `MarkdownRenderer` until a newline or
  an explicit flush — so the notice could print before the reply text it
  belonged after. Fixed by flushing the renderer before writing any
  artifact notice.
- **Markdown → ANSI** (`src/markdown.ts`): headings, bold/italic, inline
  code, list markers, and a dimmed treatment for fenced code blocks;
  respects `NO_COLOR` and non-TTY by stripping markdown syntax instead of
  emitting escape codes — including the fence delimiters themselves, which
  a review pass caught being emitted verbatim (as literal `` ``` `` marks)
  in the no-color path; they're now dropped like every other stripped
  syntax marker. This is a deliberately scoped-down rendering strategy,
  not the roadmap's block-buffered tail-redraw design — it is
  **line-buffered**: a completed line is written once and never rewritten.
  That's simpler (no cursor bookkeeping) and still streaming-safe, but it
  does **not** syntax-highlight code by language (no `cli-highlight`
  dependency added) and does not reflow tables. One-shot mode is
  unaffected — it stays plain text per Phase 1.

Verified against a live server: `/agents` lists the default adapter plus
20 real skills; `/models` lists an adapter's `allowed_models`; switching to
the Image skill and generating an image saves exactly one file to
`.orbit-out/` (after the inline/URL duplicate-save bug above was fixed);
`@path` uploads a real file and its `file_id` reaches the server
(confirmed via `listFiles()`) — the `simple-chat` adapter itself doesn't
use file content (`isFileSupported: false`), which is a server adapter
property, not a CLI defect; an unknown attachment path fails with exit 2
in one-shot mode; markdown bold/lists render correctly in a real terminal
and fall back to clean stripped text under `NO_COLOR`; REPL startup now
also calls `getAdapterInfo()` up front, so an invalid key fails fast with
exit 3 instead of only failing on the first turn.

### Phase 4 — Interactive UX ✅ Complete

Goal: close the biggest gap with Claude Code's own CLI — discovering and
running `/` commands is still "type it fully, press Enter, read the result."
Add a live filtered menu plus a few other polish items already named in
Deferred or scoped down in Phase 3.

- Interactive `/` command menu: type `/` to see every command with its
  usage and description; keep typing to fuzzy-filter it; arrow keys move a
  highlighted selection; Tab or Enter accepts it into the buffer.
- Ctrl+R reverse-search over the session's input history (classic shell
  UX: `(reverse-i-search)`query`: match`).
- A spinner between submitting a turn and the first stream chunk arriving.
- Real language-aware syntax highlighting for fenced code blocks, the one
  piece Phase 3 explicitly scoped out.

**Why a rewrite of input handling was required:** `node:readline`'s public
API has no hook for rendering extra UI below the input line while it owns
line editing — `completer` only supports Tab-cycling replacement text, and
there's no way to intercept individual keystrokes before readline consumes
them. Delivering a live filtered dropdown and a search overlay meant
replacing readline's line editing with a hand-rolled one, the same pattern
`src/prompt.ts::askSecret()` already used for the masked API-key prompt,
extended with cursor movement, in-memory history, and the two overlays.

Shipped in `clients/orbit-cli`:

- **`src/input.ts`** (new) — `LineReader`, a raw-mode line editor built on
  `readline.emitKeypressEvents()` + `process.stdin`. Owns the buffer,
  cursor, and an in-session history array; exposes an async iterator so
  `src/repl.ts`'s `for await (const line of rl)` loop is unchanged in
  shape. The `/` menu and Ctrl+R search render as extra lines below the
  prompt using `readline.cursorTo`/`clearScreenDown`/`moveCursor` for
  redraw bookkeeping, gated by the same `ansiEnabled()` check as
  everything else for the highlighted-selection styling (the cursor
  bookkeeping itself isn't color, so it isn't gated by `NO_COLOR`). The
  existing `@path` filesystem completer moved here unchanged, wired to
  Tab. `requestExit()` lets `src/repl.ts` force the current read to end as
  EOF from its own Ctrl+C-at-idle handler, matching the exact exit
  semantics readline gave for free before.
- **Single command table**: `src/repl.ts` now builds both the `/help` text
  and the menu's entries from one `COMMANDS: CommandSpec[]` array, so the
  two can't drift out of sync the way two hand-written lists eventually
  would.
- **`src/spinner.ts`** (new) — a `\r`-overwritten Braille-frame spinner,
  started right after a turn is submitted and stopped (erasing its line)
  the instant the first chunk with text or an artifact arrives, before any
  rendering happens — same ordering discipline as the Phase 3
  flush-before-artifact-notice fix. No-ops under `NO_COLOR`/non-TTY via the
  shared `ansiEnabled()` check.
- **`src/tty.ts`** (new) — `ansiEnabled()` extracted out of `markdown.ts`
  into its own module so `input.ts` and `spinner.ts` share the exact same
  TTY/`NO_COLOR` predicate instead of each reimplementing it.
- **`src/markdown.ts`**: fenced code blocks now track their language tag
  (the text after ` ``` `) and, when color is enabled, run each fence line
  through `cli-highlight` — the dependency named but not added back in
  Phase 3. Falls back to the flat dimmed treatment for an unrecognized or
  absent language tag, or if `cli-highlight` throws; the `NO_COLOR`/non-TTY
  stripped-text path is untouched.
- **`cli-highlight`** added as the CLI's one runtime dependency beyond the
  SDK.

Verified against a live server via the same PTY-harness approach as Phase
3: typing `/mo` filters the menu to `/models`/`/model`; arrow-down + Tab
fills the buffer with the highlighted entry; up-arrow with no menu open
still recalls prior lines; Ctrl+R against a two-command history correctly
narrows to and submits a match; Ctrl+C mid-turn still aborts and prints
`[cancelled]`, Ctrl+C at an idle prompt still exits; `@path` Tab-completion
(including its existing multi-match common-prefix behavior) is unchanged;
the spinner cycles frames and clears cleanly the moment a reply's first
chunk arrives; a fenced Python block renders with real syntax highlighting
in a TTY and degrades to plain stripped text under `NO_COLOR`; piped
one-shot input (`echo hi | orbit-chat -`) is unaffected since it never
constructs a `LineReader`.

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
persisted history across process restarts and `--resume`, `/feedback`,
bearer-token login (needs an `accessToken` option on `ApiClientConfig` —
`streamChat` sends only the API key today), multi-key multi-adapter
switching, conversation threads, voice, i18n, rich rendering (mermaid,
KaTeX, charts). (The interactive `/` menu and Ctrl+R history search that
used to be listed here shipped in Phase 4 — see above.)
