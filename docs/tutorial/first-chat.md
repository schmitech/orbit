# Your first chat (2 minutes)

Before touching any data source, let's confirm the full request path works end-to-end. The `simple-chat` adapter is pure conversational — no retrieval, no setup — so it's the fastest way to prove the server + API key + client flow is wired. Its adapter definition lives in [`config/adapters/passthrough.yaml`](../../config/adapters/passthrough.yaml).

### 1. Create an API key

```bash
./bin/orbit.sh login --username admin --password admin123

./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "First Chat" \
  --prompt-text "You are a friendly assistant."
```

Copy the `orbit_…` key that's printed.

> Prefer clicking? Open `http://localhost:3000/admin` → **API Keys** → **+ Create**, pick `simple-chat` as the adapter, paste a prompt, and save. The key is shown once — copy it immediately.

### 2. Chat

```bash
orbitchat --api-url http://localhost:3000 --api-key orbit_YOUR_KEY --open
```

Ask it anything. **If you get a response, the stack is working.** If not, skip down to [Troubleshooting](troubleshooting.md) before going further.

Now that you have a known-good baseline, pick an example below based on what you want to chat with.

---

[Tutorial home](../tutorial.md) | [Previous: Before you start](before-you-start.md) | [Next: Adapter Types Overview](adapter-types.md)

---
