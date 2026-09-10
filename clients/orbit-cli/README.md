# orbit-cli

Terminal REPL client for ORBIT. See `docs/roadmap/orbit-cli-repl.md` at the
repo root for the phased plan.

## Status

Phase 0 (connection, `--health`) and Phase 1 (one-shot mode) are done.
Interactive REPL mode lands in Phase 2.

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
```

Exit codes: `0` ok, `1` server error, `2` usage, `3` auth, `4` network,
`130` cancelled.
