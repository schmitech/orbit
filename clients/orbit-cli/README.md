# orbit-cli

Terminal REPL client for ORBIT. See `docs/roadmap/orbit-cli-repl.md` at the
repo root for the phased plan.

## Status

Phases 0–3 are done: connection/`--health`, one-shot mode, the REPL, and
agents/models/`@` attachments/artifacts/markdown rendering.

## Quick start

```bash
npm install -g @schmitech/orbit-cli@latest

orbit-chat --version
orbit-chat --key sk-... --health
```

## Usage

```bash
npm install
npm run build

# --url defaults to http://localhost:3000 if omitted (flag/env/prompt all fall back to it):
node bin/orbit-chat.js --key sk-... --health

# Flags:
node bin/orbit-chat.js --url http://localhost:3000 --key sk-... --health

# Or via env (preferred — a --key flag lands in shell history):
export ORBIT_URL=http://localhost:3000
export ORBIT_API_KEY=sk-...
node bin/orbit-chat.js --health

# One-shot mode: send a single message and print the reply to stdout.
node bin/orbit-chat.js "What is the capital of France?"

# Read the message from stdin instead:
echo "Summarize this." | node bin/orbit-chat.js -

# Pick an agent (skill) or model for this turn:
node bin/orbit-chat.js --agent <skill-name> --model <model-id> "hi"

# Plain text out, no ANSI — safe to pipe:
node bin/orbit-chat.js "hi" | cat

# Ctrl+C cancels an in-flight one-shot turn (exit code 130).

# Interactive REPL: no message, run from a real terminal.
node bin/orbit-chat.js

# In the REPL:
#   type a message and press Enter to send a turn
#   type / to see a filtered command menu (arrow keys, Tab/Enter to pick)
#   /new                 start a new session
#   /agents              pick an agent (arrow keys) — the key's own adapter +
#                        enabled skills actually available to it; clears any
#                        /model selection
#   /agents <name|#>      switch agent directly, same effect
#   /model               pick a model for the current agent (arrow keys)
#   /model <id|#>        set the model directly, no picker
#   /key                 switch API key without restarting (masked prompt;
#                        re-discovers agents/models for the new key)
#   /clear               clear the screen and this session's server-side history
#   /help                list commands
#   /exit                exit (also clears this session's server-side history)
#   Ctrl+C               cancel the in-flight turn; again while idle to exit
#   Ctrl+R               reverse search through this session's input history
#   Ctrl+D               exit
#
# @path/to/file inline in a message attaches that file to the turn (works in
# both the REPL, with tab completion, and one-shot mode). Generated media
# (images, video, documents, TTS audio) is written to ./.orbit-out/.
```

Exit codes: `0` ok, `1` server error, `2` usage, `3` auth, `4` network,
`130` cancelled.
