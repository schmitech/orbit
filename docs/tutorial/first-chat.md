# Your first chat (2 minutes)

**Level 0 · Orientation**

Before touching any data source, let's confirm the full request path works end-to-end. The `simple-chat` adapter is pure conversational — no retrieval, no setup — so it's the fastest way to prove the server + API key + client flow is wired. Its adapter definition lives in [`config/adapters/passthrough.yaml`](../../config/adapters/passthrough.yaml).

> **Already tested `default-key` from the README?** That's a pre-seeded example key mapped to `simple-chat`, meant for a quick smoke test — not for real use. This section creates your own key, tied to a persona you control, which is what you'll want for anything beyond a first look.

### 1. Create an API key

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
