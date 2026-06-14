# Before you start

You need three things:

1. **ORBIT installed.** Either the [release download](../../README.md#option-2-download-latest-release) or a [git clone](../../README.md#option-3-clone-from-git-development).
2. **An inference provider.** The shipped adapters default to **OpenAI (`gpt-5.4-mini`)**, so set `OPENAI_API_KEY` in your environment — or swap to another provider in `config/inference.yaml` (Ollama, Anthropic, Gemini, and 25+ others are supported).
3. **The server running.**
   ```bash
   source venv/bin/activate
   ./bin/orbit.sh start
   ```
   You should see `Uvicorn running on http://0.0.0.0:3000` in the logs.

> **Tip:** The basic Docker image (`schmitech/orbit:basic`) includes simple chat only. For database and file adapters, use the release tarball or a git checkout.

Quick health check:

```bash
curl -s http://localhost:3000/health
# {"status":"ok", ...}
```

If that responds, you're ready.

### CLI or web UI — your choice

Every admin task in this tutorial (creating API keys, managing prompts/personas, toggling adapters, editing config, viewing audit events, watching live metrics) can be done two ways:

- **CLI** — the `./bin/orbit.sh …` commands you'll see below.
- **Admin panel** — point your browser at **`http://localhost:3000/admin`** and sign in with the admin credentials from your `.env` (`ORBIT_DEFAULT_ADMIN_PASSWORD`, default username `admin`).

The panel covers Users, API Keys, Prompts/Personas, Adapters (with live toggle + per-adapter YAML editor), Settings (in-browser `config.yaml` editor), Audit, and Overview monitoring. The CLI is faster for scripted setup; the UI is friendlier for exploration. Use whichever you prefer — they act on the same underlying state.

### Install the chat client (`orbitchat`)

You'll see `orbitchat …` invocations throughout this tutorial — that's the standalone chat UI for testing adapters end-to-end. It's a separate npm package from the ORBIT server; it proxies your API requests so real API keys never reach the browser.

```bash
npm install -g orbitchat
```

Point it at your running server and an API key:

```bash
orbitchat --api-url http://localhost:3000 --api-key orbit_YOUR_KEY --open
```

That opens a browser against a local proxy (default `http://localhost:5173`). You can also run it against multiple adapters at once or as a proxy-only layer for your own UI — see [`clients/orbitchat/README.md`](../../clients/orbitchat/README.md) for the full option reference, `orbitchat.yaml` config, and the HTTP contract for custom frontends.

> The **admin panel** at `/admin` is for configuration (keys, prompts, adapters, settings). **`orbitchat`** is for actually *chatting* with an adapter to test it. You'll use both.

---

[Tutorial home](../tutorial.md) | [Next: Your first chat (2 minutes)](first-chat.md)

---
