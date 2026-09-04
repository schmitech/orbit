# Your first chat (2 minutes)

**Level 0 · Orientation**

Before touching any data source, let's confirm the full request path works end-to-end. The `simple-chat` adapter is pure conversational — no retrieval, no setup — so it's the fastest way to prove the server + API key + client flow is wired. Its adapter definition lives in [`config/adapters/passthrough.yaml`](../../config/adapters/passthrough.yaml).

> **Default installation seed:** `install/orbit.db.default` includes two ready-to-use API keys: `default-key` for `simple-chat` and `multimodal` for `simple-chat-with-files`. The matching adapter definitions are included in the default configuration. These seeded credentials are for quick smoke tests, not production use.

You can inspect the available seeded keys and adapters with the CLI:

```bash
./bin/orbit.sh key list
./bin/orbit.sh key list-adapters
```

### 1. Create an API key

The admin panel is the visual way to create a key. If you prefer the CLI, create a key and its prompt in one command:

```bash
./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "First Chat" \
  --prompt-name "First Chat Prompt" \
  --prompt-text "You are a friendly assistant."
```

See [API Key Management](../server.md#api-key-management) for more key-management commands and options.

Open `http://localhost:3000/admin`, sign in, then go to **Prompts / Personas**.

1. Create a persona with the prompt `You are a friendly assistant.`.
2. Go to **API Keys** → **+ Create**.
3. Pick `simple-chat` as the adapter.
4. Name the key `First Chat` and select the persona you just created.
5. Save the key and copy the `orbit_…` value shown once.

<!-- MEDIA: screenshot | first-chat/persona-create | Prompts/Personas tab showing the "You are a friendly assistant." persona being created -->
> 🖼️ **Screenshot placeholder:** creating the persona in Prompts / Personas.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

<!-- MEDIA: screenshot | first-chat/api-key-create | API Keys tab showing the "First Chat" key creation form with simple-chat selected -->
> 🖼️ **Screenshot placeholder:** creating the "First Chat" API key.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

<!-- MEDIA: video | first-chat/admin-panel-walkthrough | 90s walkthrough: create persona -> create API key -> copy the orbit_ key -->
> 🎬 **Video placeholder:** 90-second walkthrough of the admin-panel flow above.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### 2. Chat

You can test the conversation directly against the HTTP API with `curl`. This uses the seeded `default-key`; replace it with the key returned by the admin panel or CLI if you created your own.

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

Reuse the `X-Session-ID` value in a later request to continue the same conversation. For the browser-based option, install and launch OrbitChat with the key you created:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"orbit_YOUR_KEY"}' orbitchat --open
```

Ask it anything. **If you get a response, the stack is working.** If not, skip down to [Troubleshooting](troubleshooting.md) before going further.

<!-- MEDIA: screenshot | first-chat/chat-response | OrbitChat window showing a sent message and the model's reply -->
> 🖼️ **Screenshot placeholder:** OrbitChat showing a successful reply.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

Now that you have a known-good baseline, pick an example below based on what you want to chat with.

---

[Tutorial home](../tutorial.md) | [Previous: Before you start](before-you-start.md) | [Next: Adapter Types Overview](adapter-types.md)

---
