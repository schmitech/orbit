# Before you start

You need three things:

1. **ORBIT installed.** Follow the [Quick Start](../../README.md#-quick-start) release-tarball steps. Developing from a git clone instead? See the aside below.
2. **An inference provider.** The shipped adapters default to **OpenAI (`gpt-5.4-mini`)**, so set `OPENAI_API_KEY` in your environment — or swap to another provider in `config/inference.yaml` (Ollama, Anthropic, Gemini, and 25+ others are supported).
3. **The server running.**
   ```bash
   ./bin/orbit.sh start
   ```
   `bin/orbit.sh` activates its own virtual environment automatically, so no manual `source venv/bin/activate` is needed. You should see `Uvicorn running on http://0.0.0.0:3000` in the logs.

> **Developing from a git clone instead of the release tarball?** Run `./install/setup.sh` once to create the venv and install dependencies, then `./bin/orbit.sh start` the same way. A fresh git clone doesn't ship the pre-seeded `orbit.db` that the release tarball includes (see the API key note below) — copy `install/orbit.db.default` to `orbit.db` in the project root first if you want the same `default-key` example to work, or just create your own key in [Your first chat](first-chat.md).

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
- **Admin panel** — point your browser at **`http://localhost:3000/admin`** and sign in with the default admin credentials, `admin` / `admin123` (override via `ORBIT_DEFAULT_ADMIN_PASSWORD` in your `.env`).

The panel covers Users, API Keys, Prompts/Personas, Adapters (with live toggle + per-adapter YAML editor), Settings (in-browser `config.yaml` editor), Audit, and Overview monitoring. The CLI is faster for scripted setup; the UI is friendlier for exploration. Use whichever you prefer — they act on the same underlying state.

### Install the chat client (`orbitchat`)

You'll see `orbitchat …` invocations throughout this tutorial — that's the standalone chat UI for testing adapters end-to-end. It's a separate npm package from the ORBIT server; it proxies your API requests so real API keys never reach the browser.

```bash
npm install -g orbitchat@latest
```

Point it at your running server and an API key:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"orbit_YOUR_KEY"}' orbitchat --open
```

That starts a local proxy and opens the browser at `http://localhost:5173`. The JSON maps an adapter ID to its ORBIT API key; OrbitChat keeps the real key in the proxy and the browser sends only the adapter name.

You can map multiple adapters the same way, or define richer names, descriptions, and backend URLs in `orbitchat.yaml` — see [`clients/orbitchat/README.md`](../../clients/orbitchat/README.md) for the full option reference, config format, and HTTP contract for custom frontends.

> The **admin panel** at `/admin` is for configuration (keys, prompts, adapters, settings). **`orbitchat`** is for actually *chatting* with an adapter to test it. You'll use both.

---

[Tutorial home](../tutorial.md) | [Next: Your first chat (2 minutes)](first-chat.md)

---
