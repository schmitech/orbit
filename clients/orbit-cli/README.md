# orbit-cli

Terminal REPL client for ORBIT. See `docs/roadmap/orbit-cli-repl.md` at the
repo root for the phased plan.

## Status

Phases 0–3 are done: connection/`--health`, one-shot mode, the REPL, and
agents/models/`@` attachments/artifacts/markdown rendering.

## Usage

```bash
npm install
npm run build

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
#   /new                 start a new session
#   /agents              list agents (the key's own adapter + enabled skills)
#   /agents <name|#>      switch agent — clears any /model selection
#   /models              list models allowed for the current agent
#   /model <id|#>        set the model for later turns
#   /clear               clear the screen
#   /help                list commands
#   /exit                exit
#   Ctrl+C               cancel the in-flight turn; again while idle to exit
#   Ctrl+D               exit
#
# @path/to/file inline in a message attaches that file to the turn (works in
# both the REPL, with tab completion, and one-shot mode). Generated media
# (images, video, documents, TTS audio) is written to ./.orbit-out/.
```

Exit codes: `0` ok, `1` server error, `2` usage, `3` auth, `4` network,
`130` cancelled.
