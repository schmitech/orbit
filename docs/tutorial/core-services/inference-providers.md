# Inference Providers

**Level 2 · Core AI Services**

[`config/inference.yaml`](../../../config/inference.yaml) lists 37+ inference providers — local runtimes like Ollama and llama.cpp, and hosted APIs like OpenAI, Anthropic, Gemini, Bedrock, Azure, and dozens more. Seeing all of them at once is the single biggest source of "is this really for me?" hesitation for newcomers. It shouldn't be: **you configure one**, the one your first adapter actually uses, and leave the rest alone.

## You already configured one — here's how it connects

If you followed [Before you start](../before-you-start.md), you set `OPENAI_API_KEY` and didn't touch anything else. That's the whole pattern:

```yaml
# config/inference.yaml
inference:
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    model: "gpt-5.4-mini"
    context_window: 128000
    max_tokens: 16000
    stream: true
```

An adapter opts into this block by name:

```yaml
# config/adapters/passthrough.yaml
- name: "simple-chat"
  inference_provider: "openai"   # <- matches the "openai:" key above
  model: "gpt-oss:120b"          # optional: override the model for this adapter only
```

`inference_provider` is the only required link. `model` is optional per adapter — omit it to use the provider's default `model:` above, or set it to run a different model on the same provider account (useful when one adapter needs a cheap/fast model and another needs a stronger one).

## Picking a provider to start with

Don't try to configure all 37. Pick based on what you have available:

| You have | Use | Setting |
|---|---|---|
| An OpenAI/Anthropic/Gemini API key | The matching hosted provider | Set `enabled: true`, put your key in the `${...}_API_KEY` env var referenced in that block |
| A local machine, no API keys, want to try ORBIT offline | `ollama` (already `enabled: true` by default with a small preset model) or `llama_cpp` (direct GGUF loading) | No API key needed — see `config/ollama.yaml` / `config/llama_cpp.yaml` for the model presets these reference |
| A GPU server and want maximum throughput | `vllm` or `sglang` (connect to a running server) | `mode: "api"` and a `base_url` pointing at your running inference server |

Every other block in `inference.yaml` can stay exactly as shipped — most default to `enabled: false` or point at placeholder credentials, and ORBIT never touches a provider your adapters don't reference.

## Every provider block follows the same shape

Regardless of which of the 37+ you use, the fields are the same handful of concepts:

- **`enabled`** — whether ORBIT will try to use this provider at all.
- **Connection** — `api_key` (usually an `${ENV_VAR}` reference, never a literal secret in the file), plus `base_url`/`host`/`port` for self-hosted or non-default endpoints.
- **`model`** — the default model this provider runs; adapters can override it per-adapter (see above) or even per-request via `allowed_models` (see [Adapter Configuration Reference](../adapter-configuration-reference.md)).
- **Generation parameters** — `temperature`, `top_p`, `max_tokens`, `stream`, and provider-specific reasoning controls (`effort`, `reasoning_effort`, `thinking_level`, `think` — the name varies by provider, but the concept is the same: how much the model "thinks" before answering).
- **`context_window`** — how many tokens of conversation history + retrieved context the model can accept; this reshapes ORBIT's own history-trimming budget, so set it to match what the model/provider actually supports.

Once you can read one block, you can read any of them — they're not 37 different formats, they're one format repeated 37 times with provider-specific extras (e.g. `vllm`'s GPU/quantization settings, `bitnet`'s kernel parameters) that only matter if you're using that specific runtime.

## Local vs. hosted, at a glance

| | Local (Ollama, llama.cpp, vLLM, SGLang, BitNet) | Hosted (OpenAI, Anthropic, Gemini, ...) |
|---|---|---|
| Cost | Free after hardware/setup | Per-token billing |
| Setup | Requires installing/running a model server | Just an API key |
| Latency | Depends on your hardware | Consistent, provider-managed |
| Privacy | Data never leaves your machine | Data sent to the provider |
| Model quality ceiling | Limited by what fits on your hardware | Access to the largest available models |

Most people prototype on a hosted provider (fastest to get running, per `before-you-start.md`) and move to local inference later for cost or privacy reasons, or the reverse if they started fully offline. Both paths are the same one-line change: swap `inference_provider:` on the adapter and set `enabled: true` on the new provider block.

---

Next: [Datasources](datasources.md) — where the data behind a retriever adapter actually lives.

[Core AI Services overview](overview.md) | [Tutorial home](../../tutorial.md)
