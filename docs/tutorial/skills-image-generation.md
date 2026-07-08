# Example 9: Skills and Image Generation

Skills let one adapter call another adapter for a single message without changing API keys or switching the whole conversation. The calling adapter must explicitly allow the skill, and the skill adapter must expose itself with a `skill_name`.

This example uses the image-generation skill:

- [`config/adapters/image-generator.yaml`](../../config/adapters/image-generator.yaml) exposes the `image-generator` adapter as the `Image` skill.
- [`config/adapters/multimodal.yaml`](../../config/adapters/multimodal.yaml) allows `simple-chat-with-files` to invoke `Image` through `capabilities.available_skills`.

## How the Image skill is exposed

The skill adapter is a normal adapter with skill metadata in `capabilities`:

```yaml
- name: "image-generator"
  enabled: true
  type: "image_generation"
  adapter: "multimodal"
  image_provider: "xai"
  rewrite_provider: "deepseek"

  capabilities:
    expose_as_skill: true
    skill_name: "Image"
    skill_description: "Generate images from text descriptions using AI (imagine, Imagen, or Ollama)"
    retrieval_behavior: "none"
    requires_api_key_validation: false
```

`skill_name` is the value clients send in the chat request. Use the exact configured name; in the current sample config that is `Image`.

## How a chat adapter allows the skill

The consumer adapter lists allowed skills under `available_skills`:

```yaml
- name: "simple-chat-with-files"
  enabled: true
  type: "passthrough"
  adapter: "multimodal"

  capabilities:
    retrieval_behavior: "conditional"
    available_skills:
      - "Image"
      - "web-search"
      - "mcp-agent"
```

When an API key is bound to `simple-chat-with-files`, that key can invoke `Image`. A key bound to an adapter without `Image` in `available_skills` cannot.

## Create an API key

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** with the prompt `You are a helpful multimodal assistant.`.

Then go to **API Keys** → **+ Create**:

1. Choose `simple-chat-with-files` as the adapter.
2. Name the key `File Chat with Image Skill`.
3. Select the persona you just created.
4. Save the key and copy the `orbit_…` value shown once.

## Try it from OrbitChat

Start OrbitChat with the key:

```bash
orbitchat --api-url http://localhost:3000 --api-key orbit_YOUR_KEY --open
```

In the message box, type `/` to open the skill picker, choose `Image`, then send a prompt such as:

```text
Create a clean product-style illustration of an ORBIT data assistant connecting documents, databases, and APIs.
```

The response should render an image instead of a normal text answer. If you are already chatting about uploaded files, the image prompt can use that conversation context.

## Try it with curl

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: orbit_YOUR_KEY" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Create a diagram-style image of a data assistant routing a question to files, SQL, and APIs."
      }
    ],
    "skill": "Image"
  }'
```

A successful response includes image fields:

```json
{
  "response": "Create a diagram-style image...",
  "image": "<base64-encoded image>",
  "image_format": "png",
  "image_revised_prompt": "..."
}
```

## What happens internally

1. The API key authenticates as `simple-chat-with-files`.
2. ORBIT checks that `Image` is listed in that adapter's `available_skills`.
3. ORBIT routes only this request to the `image-generator` adapter.
4. `ImageGenerationStep` generates the image; the normal chat inference path is skipped for this request.
5. The original conversation continues on `simple-chat-with-files` after the skill response.

See [Skills](../adapters/skills.md) for the full capability reference, admin endpoints, UI integration notes, and the pattern for exposing additional adapters as skills.

---

[Tutorial home](../tutorial.md) | [Previous: Example 8: Agent with Function Calling](agent-function-calling.md) | [Next: Creating API Keys](creating-api-keys.md)

---
