# Before you start

**Level 0 · Orientation**

You need three things:

1. **ORBIT installed.** Follow the [Quick Start](../../README.md#quick-start) release-tarball steps. Developing from a git clone instead? See the aside below.
2. **An inference provider.** The canonical installation defaults to **Ollama** in [`install/default-config/config.yaml`](../../install/default-config/config.yaml).

   The default setup enables `ollama` in `config/inference.yaml`, sets
   `general.inference_provider` to `ollama` in `config/config.yaml`, and uses the
   `gemma4-e2b-cpu` Ollama preset. Presets are defined in
   [`config/ollama.yaml`](../../config/ollama.yaml); this preset resolves to the
   `gemma4:e2b` model tag.

   Install and start [Ollama](https://ollama.com/). If it is not already running,
   run `ollama serve` in another terminal, then pull the default model:

   ```bash
   ollama pull gemma4:e2b
   ```

   If you plan to use the retrieval adapters, also pull the embedding
   model and enable Ollama embeddings in the active `config/embeddings.yaml`:

   ```bash
   ollama pull nomic-embed-text
   ```

   Set `embedding.enabled: true`; the canonical adapter uses
   `embedding_provider: "ollama"` and `embedding_model: "nomic-embed-text"`.

   Alternatively, enable another provider in `config/inference.yaml`, set its
   credential in `.env`, and select it in `config/config.yaml` or the adapter
   YAML. For a no-local-install option, use the prebuilt [Ollama, OpenAI, or
   Gemini Docker flavors](../../docker/README.md#flavor-images-recommended-pull-and-run).
3. **The server running.**
   ```bash
   ./bin/orbit.sh start
   ```
   `bin/orbit.sh` activates its own virtual environment automatically, so no manual `source venv/bin/activate` is needed. You should see `Uvicorn running on http://0.0.0.0:3000` in the logs.

Quick health check:

```bash
curl -s http://localhost:3000/health
# {"status":"ok", ...}
```

If that responds, you're ready.

<!-- MEDIA: screenshot | before-you-start/terminal-server-start | Terminal showing `./bin/orbit.sh start` output ending in "Uvicorn running on http://0.0.0.0:3000" -->
> 🖼️ **Screenshot placeholder:** terminal output of a successful `./bin/orbit.sh start`.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### CLI or web UI — your choice

Every admin task in this tutorial (creating API keys, managing prompts/personas, toggling adapters, editing config, viewing audit events, watching live metrics) can be done two ways:

- **CLI** — the `./bin/orbit.sh …` commands you'll see below.
- **Admin panel** — point your browser at **`http://localhost:3000/admin`** and sign in with the default admin credentials, `admin` / `ChangeMe!2026` (override via `ORBIT_DEFAULT_ADMIN_PASSWORD` in your `.env`).

The panel covers Users, API Keys, Prompts/Personas, Adapters (with live toggle + per-adapter YAML editor), Settings (in-browser `config.yaml` editor), Audit, and Overview monitoring. The CLI is faster for scripted setup; the UI is friendlier for exploration. Use whichever you prefer — they act on the same underlying state.

For a full visual tour of every tab, see [Admin Panel Tour](admin-panel-tour.md).

<!-- MEDIA: screenshot | before-you-start/admin-login | Admin panel login screen at http://localhost:3000/admin -->
> 🖼️ **Screenshot placeholder:** the admin panel login screen.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### Test a conversation with `curl`

Before installing a chat UI, you can test the running server directly with the API. The release tarball includes a `default-key` example; if you are using a git checkout, use a key you created instead.

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: my-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    "stream": false
  }'
```

The `X-Session-ID` header identifies the conversation, so reuse `my-session` in a later request when you want to continue it. This is the same basic request shown in the [Docker API examples](../../docker/README.md#basic-chat-request).

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
