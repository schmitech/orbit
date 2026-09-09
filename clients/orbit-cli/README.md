# orbit-cli

Terminal REPL client for ORBIT. See `docs/roadmap/orbit-cli-repl.md` at the
repo root for the phased plan.

## Status

Phase 0 — scaffold, connection resolution, `--health`. One-shot and
interactive modes land in later phases.

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
```

No config file, `.env`, or keychain is used. Nothing is written to disk.
