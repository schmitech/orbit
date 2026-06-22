# Web Search Adapters

ORBIT has two distinct web search mechanisms. They are complementary and solve different problems. This guide explains both, when to use each, and how to configure them.

---

## Quick Comparison

| | Provider-native search | External search providers |
|---|---|---|
| **Config file** | `config/adapters/web-search.yaml` | `config/adapters/web-search-providers.yaml` |
| **Adapter type** | `passthrough` | `web-search` |
| **Who does the searching** | The LLM provider (Gemini, OpenAI, xAI) | A dedicated external search API |
| **Who synthesizes the answer** | Same LLM, in the same call | Any configured LLM, in a follow-up step |
| **Supported LLM providers** | Gemini, OpenAI, xAI only | Any (Anthropic, Ollama, OpenAI, …) |
| **Available search backends** | Provider's own index | DuckDuckGo, Brave, SearXNG, Serper, Tavily, Google PSE, Perplexity |
| **Citation style** | Provider-native grounding | Numbered snippet list in context |
| **Free tier** | Depends on provider | DuckDuckGo and SearXNG (self-hosted) are free |
| **Pipeline step** | `LLMInferenceStep` (native tool) | `WebSearchStep` → `LLMInferenceStep` |

---

## 1. Provider-Native Web Search

Configured in `config/adapters/web-search.yaml`.

The adapter has `type: "passthrough"` and `capabilities.web_search: true`. When a request arrives, `LLMInferenceStep` reads the flag from `ProcessingContext.web_search` and passes `web_search=True` to the provider's inference call. The provider performs its own web search and returns a grounded response — searching and synthesizing happen in a single API round-trip.

```
User request
    ↓
RequestContextBuilder: reads capabilities.web_search → context.web_search = True
    ↓
LLMInferenceStep: passes web_search=True to provider.generate()
    ↓
Provider (Gemini / OpenAI / xAI) performs native web search + synthesis
    ↓
Response with inline citations
```

### Supported providers

| Provider | Mechanism | Example model |
|----------|-----------|---------------|
| `gemini` | `google_search` grounding tool on the generate-content call | `gemini-3.1-pro-preview` |
| `openai` | `web_search_preview` tool via the Responses API | a search-capable OpenAI model |
| `xai` | `web_search` tool via the xAI API | `grok-4.3` |

Any other provider will produce undefined behavior: some inference services pass unknown kwargs directly to the underlying API client, which will return an API error (e.g. HTTP 400 from Anthropic); others may silently discard the flag. Point this adapter only at the three providers above.

### Configuration

```yaml
adapters:
  - name: "web-search-chat"
    enabled: true
    type: "passthrough"
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    inference_provider: "gemini"
    model: "gemini-3.1-pro-preview"
    capabilities:
      web_search: true                   # enables native search on the inference call
      expose_as_skill: true
      skill_name: "web-search"
      skill_description: "Search the web and answer with up-to-date information and citations"
      retrieval_behavior: "none"
      formatting_style: "standard"
      requires_api_key_validation: false
```

To use OpenAI or xAI instead, change `inference_provider` and `model`. The `web_search: true` capability flag is the only required change — no other fields differ.

### Invoking as a skill

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an adapter that lists web-search in available_skills>" \
  -d '{"messages":[{"role":"user","content":"What are today'\''s top news headlines?"}],
       "skill":"web-search"}'
```

---

## 2. External Search Providers

Configured in `config/adapters/web-search-providers.yaml`.

These adapters have `type: "web-search"`. A new `WebSearchStep` in the inference pipeline fires for this adapter type, calls the configured external search API, formats the results as a numbered snippet list in `context.formatted_context`, and then lets `LLMInferenceStep` synthesize the final answer using any configured LLM.

```
User request
    ↓
WebSearchStep: calls external search API (DuckDuckGo, Brave, Serper, …)
    ↓
context.formatted_context = numbered list of [title, URL, snippet]
context.sources = [{title, url, snippet}, …]
    ↓
LLMInferenceStep: synthesizes answer using context (any LLM provider)
    ↓
Response with sources array
```

Because searching and synthesis are decoupled, you can mix and match freely — e.g. DuckDuckGo results synthesized by Claude, or Perplexity results synthesized by a local Ollama model.

### Supported search backends

| Provider key | Free tier | API key required | Notes |
|---|---|---|---|
| `duckduckgo` | Yes | No | Best for private, no-signup use |
| `searxng` | Yes (self-hosted) | No | Requires a running SearXNG instance |
| `brave` | Limited | Yes | [brave.com/search/api](https://brave.com/search/api/) |
| `serper` | Limited | Yes | Google results via [serper.dev](https://serper.dev/) |
| `tavily` | Limited | Yes | AI-native search, [tavily.com](https://tavily.com/) |
| `google_pse` | Limited | Yes | Google Programmable Search Engine |
| `perplexity` | No | Yes | Structured results via [/search endpoint](https://docs.perplexity.ai/docs/search/quickstart) |

### Configuration

Every adapter in this file follows the same structure. The `web_search` block is the only part that varies per provider:

```yaml
adapters:
  - name: "web-search-duckduckgo"
    enabled: true
    type: "web-search"              # activates WebSearchStep
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    inference_provider: "anthropic"  # any LLM for synthesis
    model: "claude-haiku-4-5-20251001"
    web_search:
      provider: "duckduckgo"         # required — must match a key in PROVIDERS registry
      result_count: 5                # number of results to fetch (default: 5)
      # filter_list: ["example.com"] # optional domain whitelist
    capabilities:
      expose_as_skill: true
      skill_name: "web-search-duckduckgo"
      skill_description: "Search the web using DuckDuckGo (free, no API key)"
      retrieval_behavior: "none"
      formatting_style: "standard"
      requires_api_key_validation: false
```

### `web_search` block options

| Key | Required | Description |
|---|---|---|
| `provider` | Yes | Provider name (see table above) |
| `result_count` | No | Max results to fetch (default: `5`) |
| `filter_list` | No | List of domain substrings — only matching results are kept |
| `api_key` | Depends | Required by Brave, Serper, Tavily, Google PSE, Perplexity |
| `query_url` | SearXNG only | Base URL of your SearXNG instance |
| `search_engine_id` | Google PSE only | Programmable Search Engine ID |
| `api_url` | Perplexity only | Override for custom deployments |
| `backend` | DuckDuckGo only | Backend to use: `auto`, `google`, `brave`, etc. |

### Required environment variables

| Provider | Variable |
|---|---|
| Brave | `BRAVE_SEARCH_API_KEY` |
| SearXNG | `SEARXNG_URL` |
| Serper | `SERPER_API_KEY` |
| Tavily | `TAVILY_API_KEY` |
| Google PSE | `GOOGLE_PSE_API_KEY`, `GOOGLE_PSE_ENGINE_ID` |
| Perplexity | `PERPLEXITY_API_KEY` |

All variables are defined in `env.example`.

### Invoking as a skill

```bash
# DuckDuckGo (no API key needed).
# simple-chat already includes web-search-duckduckgo in its available_skills,
# so its API key works out of the box.
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <simple-chat API key>" \
  -d '{"messages":[{"role":"user","content":"Latest news about open source AI?"}],
       "skill":"web-search-duckduckgo"}'
```

> **Note:** to use an external search skill from any other adapter, add its `skill_name` to that adapter's `available_skills` first — see [Allowing Web Search Skills in Other Adapters](#allowing-web-search-skills-in-other-adapters) below.

The response includes a `sources` array with the raw search results alongside the synthesized `response`:

```json
{
  "response": "Here are the latest developments in open source AI...",
  "sources": [
    {"title": "...", "url": "https://...", "snippet": "..."},
    ...
  ]
}
```

---

## Choosing Between the Two

**Use provider-native search (`web-search.yaml`) when:**
- You are already using Gemini, OpenAI, or xAI as your inference provider
- You want the simplest setup (one adapter, one API call)
- Provider-native grounding quality and citation format are acceptable

**Use external search providers (`web-search-providers.yaml`) when:**
- You use Anthropic, Ollama, or another provider that doesn't support native search
- You need a specific search engine (DuckDuckGo for privacy, SearXNG for self-hosted, Perplexity for AI-ranked results)
- You need `sources` as structured data in the response
- You want full control over how many results are fetched, which domains are allowed, or which LLM synthesizes the answer

---

## Allowing Web Search Skills in Other Adapters

Both skill types are invoked via the `skill=` request parameter. To allow a skill in an adapter, add its `skill_name` to `available_skills` in that adapter's capabilities:

```yaml
# e.g. in config/adapters/passthrough.yaml
capabilities:
  available_skills:
    - "web-search"              # provider-native (Gemini/OpenAI/xAI)
    - "web-search-duckduckgo"   # external: DuckDuckGo
    - "web-search-serper"       # external: Google via Serper
```

Multiple skills can be listed. If `available_skills` is omitted, no skills can be invoked from that adapter. See [skills.md](./skills.md) for the full skills system documentation.

---

## Adding a New External Search Provider

1. Create `server/web_search/providers/<name>.py` with an async function:
   ```python
   async def search_<name>(query: str, count: int, api_key: str, ...) -> list[SearchResult]:
       ...
   ```
2. Register it in `server/web_search/registry.py`:
   ```python
   from .providers.<name> import search_<name>
   PROVIDERS["<name>"] = search_<name>
   ```
3. Add an adapter entry to `config/adapters/web-search-providers.yaml` with `provider: "<name>"`.
4. Add the required API key to `env.example` and `.env`.

No pipeline or registration changes are needed — `WebSearchStep` resolves providers dynamically from the registry at request time.

---

## Implementation Reference

| Component | File | Role |
|-----------|------|------|
| Provider-native flag | `server/adapters/capabilities.py` | `AdapterCapabilities.web_search` |
| Native search in pipeline | `server/inference/pipeline/steps/llm_inference.py` | Reads `context.web_search`, passes to provider |
| Gemini native search | `server/ai_services/implementations/inference/gemini_inference_service.py` | Injects `types.Tool(google_search=…)` |
| OpenAI/xAI native search | Respective inference service files | Calls `_build_web_search_params()` |
| `WebSearchStep` | `server/inference/pipeline/steps/web_search.py` | Calls provider, populates `context.formatted_context` |
| Provider implementations | `server/web_search/providers/` | One file per search backend |
| Provider registry | `server/web_search/registry.py` | Maps provider name → async callable |
| Shared types | `server/web_search/base.py` | `SearchResult`, `get_filtered_results` |
| Adapter registration | `server/adapters/__init__.py` | Registers `web-search` type in `ADAPTER_REGISTRY` |
| Native skill config | `config/adapters/web-search.yaml` | `web-search-chat` adapter |
| External skill configs | `config/adapters/web-search-providers.yaml` | All external provider adapters |
| Pipeline wiring | `server/inference/pipeline/pipeline.py` | `WebSearchStep` inserted before `LLMInferenceStep` |
