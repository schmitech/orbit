# Your first chat (2 minutes)

Before touching any data source, let's confirm the full request path works end-to-end. The `simple-chat` adapter is pure conversational — no retrieval, no setup — so it's the fastest way to prove the server + API key + client flow is wired. Its adapter definition lives in [`config/adapters/passthrough.yaml`](../../config/adapters/passthrough.yaml).

> **Already tested `default-key` from the README?** That's a pre-seeded example key mapped to `simple-chat`, meant for a quick smoke test — not for real use. This section creates your own key, tied to a persona you control, which is what you'll want for anything beyond a first look.

### 1. Create an API key

Open `http://localhost:3000/admin`, sign in, then go to **Prompts / Personas**.

1. Create a persona with the prompt `You are a friendly assistant.`.
2. Go to **API Keys** → **+ Create**.
3. Pick `simple-chat` as the adapter.
4. Name the key `First Chat` and select the persona you just created.
5. Save the key and copy the `orbit_…` value shown once.

<p align="center">
  <video src="./first-chat-admin-panel-placeholder.mp4" controls muted playsinline width="80%"></video>
  <br />
  <em>Placeholder video: record the admin-panel flow for creating a persona and API key here.</em>
</p>

### 2. Chat

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"orbit_YOUR_KEY"}' orbitchat --open
```

Ask it anything. **If you get a response, the stack is working.** If not, skip down to [Troubleshooting](troubleshooting.md) before going further.

Now that you have a known-good baseline, pick an example below based on what you want to chat with.

---

[Tutorial home](../tutorial.md) | [Previous: Before you start](before-you-start.md) | [Next: Adapter Types Overview](adapter-types.md)

---
