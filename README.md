<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/e7beb0b9-59a2-4c0c-afaf-a72d445a264c" alt="ORBIT Logo" width="200"/>
  </a>

  <p>ORBIT — Open Retrieval-Based Inference Toolkit</p>
  <h3>The self-hosted AI gateway for production RAG across LLMs, databases, APIs, and files.</h3>
</div>

<br/>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/github/v/release/schmitech/orbit" alt="Latest release"></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit" alt="Last commit"></a>
  <a href="https://github.com/schmitech/orbit" target="_blank">
    <img src="https://img.shields.io/github/stars/schmitech/orbit?style=social&label=Star" alt="GitHub stars">
  </a>
</p>

<p align="center">
  <a href="docs/tutorial.md"><strong>Tutorial</strong></a>
  &nbsp;|&nbsp;
  <a href="docker/README.md"><strong>Docker Guide</strong></a>
  &nbsp;|&nbsp;
  <a href="docs/cookbook/"><strong>Cookbook</strong></a>
</p>

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/5118565d-5d44-45a6-990d-97bc18156ec0" controls muted playsinline width="75%"></video>
  <br />
  <em>The HR assistant answering workforce questions over employee, department, budget, and compensation data. Source available at <a href="examples/intent-templates/sql-intent-template/examples/sqlite/hr/">examples/intent-templates/sql-intent-template/examples/sqlite/hr</a>.</em>
</p>

---

ORBIT gives you one OpenAI-compatible API for private RAG, model routing, file Q&A, database copilots, voice agents, and MCP tools. Run it locally, connect your own data, and swap between hosted or local LLM providers without rewriting your app.

If ORBIT looks useful, **[star the repo](https://github.com/schmitech/orbit)** to follow new adapters, recipes, voice features, and production-ready RAG workloads.

---

### Get running in 60 seconds

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

Then test it:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: local-test' \
  -d '{
    "messages": [{"role": "user", "content": "Summarize ORBIT in one sentence."}],
    "stream": false
  }'
```

That's it. ORBIT is listening on port 3000 with an admin panel at [localhost:3000/admin](http://localhost:3000/admin) (default login: `admin` / `admin123`).

For GPU acceleration: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`

Adapter wiring and sample domains live in [`config/adapters/`](config/adapters/) and [`examples/intent-templates/`](examples/intent-templates/).

---

<p align="center">
  <img width="700" alt="image generation skill" src="https://github.com/user-attachments/assets/e2588037-8b94-4351-b3cb-40ff41102add" />
  <br />
  <em>Invoke specialized cross-adapter skills like image generation at any point during a conversation to visualize data, generate charts, or create infographics directly from retrieval results. <a href="docs/adapters/skills.md">Learn more</a>.</em>
</p>

---

### Why ORBIT?

| Without ORBIT | With ORBIT |
| :--- | :--- |
| One SDK per provider, rewrites when you switch | One OpenAI-compatible API across 37 providers |
| Separate pipelines for retrieval and inference | Unified model + retrieval + tooling gateway |
| Fragile glue scripts between data sources and LLMs | Intent adapters with template diagnostics |
| Separate tools for each database, with no easy way to combine them | Composite adapters fan one prompt across SQL + NoSQL + HTTP, merged by the LLM |
| Cascading failures when a provider hiccups | Circuit breakers, parallel fan-out, progressive throttling |
| No visibility into what models are doing | Built-in RBAC, quota-aware rate limiting, and audit logging |

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/994aaede-dcce-40b5-8622-47f28684cedd" controls muted playsinline width="75%"></video>
  <br />
  <em>The multimodal adapter lets you upload PDFs, documents, and images, then ask questions across all of them in a single conversation. Context is preserved across turns, and running it with a local model keeps every file and query entirely on your own infrastructure.</em>
</p>

---

### What ORBIT does differently

Most AI gateways stop at provider routing. ORBIT is built for the messy parts of production RAG.

- **Intent-based retrieval, not just vector search** — ship real queries, not vector guesses. Users ask in natural language; ORBIT picks the right template and runs the query against your data. [Learn more](docs/intent-sql-rag-system.md).
- **Cross-adapter RAG across mixed databases + APIs** — one question, many sources. Fan a query out to SQL, MongoDB, HTTP, and more in parallel and let the LLM merge the answers. [Learn more](config/adapters/composite.yaml).
- **Template diagnostics** — iterate on intent templates without burning LLM tokens. [Learn more](docs/template-diagnostics.md).
- **Conversation threading with cached datasets** — branch off any turn; follow-ups reuse the retrieved data instead of re-querying the DB. [Learn more](docs/conversation-threading-architecture.md).
- **Circuit breakers + parallel fan-out** — resilient adapter orchestration that survives provider hiccups. [Learn more](docs/fault-tolerance/).
- **Autocomplete that knows your data** — fuzzy-matched suggestions sourced from your intent templates. [Learn more](docs/autocomplete-architecture.md).
- **Two-layer rate limiting** — IP limits plus per-API-key quotas with progressive throttling. [Learn more](docs/rate-limiting-architecture.md).
- **Multilingual by default** — 100+ languages with conversation stickiness so the model doesn't flap between turns. [Learn more](docs/language-detection-architecture.md).
- **Runtime model selection** — adapters declare an `allowed_models` list; clients pick a model per request and ORBIT resolves it to the right provider at runtime. The chat UI exposes a model picker on every agent card and in the active conversation header — no redeploy needed to switch models. [Learn more](docs/adapters/adapter-configuration.md).
- **OpenClaw / Hermes / MCP integration** — drop ORBIT into MCP-capable agents as a tool server with a single config entry. [Learn more](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md).

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/55a1f582-5ea4-411d-bbfc-4ccffbd6f81a" controls muted playsinline width="75%"></video>
  <br />
  <em>ORBIT supports conversation threading with multi-turn follow-ups on the same result set — branch off any assistant response to keep drilling into the data without re-querying the database. Source available at <a href="examples/intent-templates/duckdb-intent-template/examples/analytics/">examples/intent-templates/duckdb-intent-template/examples/analytics</a>.</em>
</p>

---

### Is ORBIT a fit?

ORBIT is a good fit if you need a self-hosted AI gateway, private RAG over real business systems, mixed data-source retrieval, provider switching, or MCP tools for agents.

ORBIT is probably more than you need if you only want a thin wrapper around one LLM provider.

---

### Examples

| Example | Start here |
| :--- | :--- |
| Chat with a local model through an OpenAI-compatible API | [Step-by-step tutorial](docs/tutorial.md) |
| Ask Postgres, MySQL, MongoDB, DuckDB, or Elasticsearch questions in natural language | [Database copilot](docs/cookbook/build-natural-language-database-copilot-with-orbit.md) |
| Query SQL + NoSQL + REST APIs in one prompt | [Composite adapters](docs/adapters/composite-intent-retriever.md) |
| Upload files and get grounded answers | [File-upload RAG](docs/cookbook/orbit-file-upload-rag.md) |
| Run ORBIT as an MCP tool server for agents | [MCP / OpenClaw walkthrough](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md) |
| Build a full-duplex voice assistant | [PersonaPlex voice assistant](docs/cookbook/orbit-personaplex-full-duplex-voice-assistant.md) |

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/bd1aa8d0-abe4-499d-a6bb-32b4520ac504" controls muted playsinline width="75%"></video>
  <br />
  <em>OrbitChat rendering live charts from LLM output — bar, line, area, pie, scatter, composed, radar, funnel, radialbar, and horizontal bar — with no client-side charting code required. The model emits a fenced <code>chart</code> block, and the renderer handles the rest.</em>
</p>

---

### What's in the box

| Capability | Includes |
| :--- | :--- |
| **LLM gateway** | OpenAI-compatible chat API, 37 hosted and local providers, streaming, provider failover |
| **RAG over real systems** | SQL, NoSQL, REST, GraphQL, files, web content, vector stores, rerankers |
| **Intent-based retrieval** | Natural-language templates, diagnostics, autocomplete, cached datasets, conversation threading |
| **Production controls** | API keys, RBAC, audit logs, rate limits, quotas, moderation, circuit breakers |
| **Cross-adapter skills** | Invoke specialized adapters (image generation, and more) mid-conversation via a `skill` field — explicit allowlist per adapter, no separate auth |
| **Agent + voice support** | MCP server, OpenClaw / Hermes / Claude Desktop / Cursor compatibility, full-duplex PersonaPlex voice |
| **Clients** | Web chat, CLI, mobile app, Node SDK, Python client, or any OpenAI-compatible SDK |

<details>
<summary><strong>Full provider and integration list</strong></summary>

| Layer | Coverage |
| :--- | :--- |
| **LLM & inference** | 37 providers — OpenAI, Anthropic, Gemini, Cohere, Groq, DeepSeek, Mistral, xAI, AWS Bedrock, Azure, Vertex, Together, Fireworks, Perplexity, Replicate, OpenRouter, Watson, NVIDIA, Hugging Face, Ollama (local/cloud/remote), vLLM, TensorRT-LLM, llama.cpp, Shimmy, BitNet (1.58-bit), Transformers, Z.ai, Cerebras, DeepInfra, LM Studio, Moonshot AI, MiniMax, Nebius, Venice AI, Scaleway |
| **Data sources** | 17 — Postgres, MySQL, MariaDB, SQL Server, Oracle, SQLite, MongoDB, Redis, Cassandra, DuckDB, Athena, Elasticsearch, Supabase + HTTP/REST, GraphQL, Firecrawl |
| **Vector stores** | Chroma, Qdrant, Pinecone, Milvus, Weaviate, Elasticsearch |
| **Embeddings** | 10 providers — OpenAI, Cohere, Jina, Voyage, Mistral, Gemini, OpenRouter, Ollama, llama.cpp, Sentence-Transformers |
| **Rerankers** | 6 providers — Cohere, Jina, Voyage, OpenAI, Anthropic, Ollama |
| **Moderation / guardrails** | OpenAI, Anthropic, Llama Guard (local), pluggable chain |
| **Voice** | Full-duplex speech-to-speech via **PersonaPlex**; STT (Whisper, Google, Gemini), TTS (OpenAI, ElevenLabs, Coqui) |
| **Protocols** | OpenAI-compatible chat API + **MCP** — drop-in tool server for [OpenClaw](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md), Hermes, Claude Desktop, Cursor, or any MCP client |

</details>

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/4f291788-0c5c-4b06-947b-8147d746e508" controls muted playsinline width="75%"></video>
  <br />
  <em>Runtime model selection in action: the HR assistant queries a Canadian employee database in natural language. Switch between a local on-prem model and a cloud-hosted model mid-conversation — the selected model travels with every message, including thread replies and regenerations. No redeploy. No config change. Data residency stays in your control.</em>
</p>

---

### What can you build with ORBIT?

- **Private AI gateways** for regulated teams that need self-hosting, RBAC, audit logs, guardrails, and data residency.
- **Database copilots** for analysts who need natural-language access to SQL, NoSQL, APIs, and files without writing queries.
- **Document Q&A products** over PDFs, policies, contracts, manuals, and knowledge bases.
- **Voice-first copilots** for call centers, field service, kiosks, and internal operations.
- **MCP tools for agent platforms** that expose domain-specific data and actions to Claude Desktop, Cursor, OpenClaw, or custom agents.

ORBIT is Apache 2.0, so you can build and sell commercial products on top of it without royalties or per-seat licensing back to the project. If you build something, [open an issue](https://github.com/schmitech/orbit/issues) and we'll feature it.

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/268801ff-5e17-4358-9e69-b2667851d611" controls muted playsinline width="75%"></video>
  <br />
  <em>Image generation as a cross-adapter skill. ORBIT routes the request to the image adapter, enriching the prompt with conversation history and thread context before generating.</em>
</p>

---

### Clients

| Client | Description |
| :--- | :--- |
| **[Web Chat](clients/orbitchat/)** | React UI |
| **[Mobile](clients/orbit-mobile/)** | iOS & Android (Expo) |
| **[Node SDK](clients/node-api/)** | Or use any OpenAI-compatible SDK |

---

### Deployment options

#### Docker Compose (fastest path)

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

Starts ORBIT + Ollama with SmolLM2, auto-pulls models, and exposes the API on port 3000. The web admin UI is at `/admin` on the same host. Connect [orbitchat](https://www.npmjs.com/package/orbitchat) from your host:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat
```

<p align="center">
  <img width="1773" alt="admin panel dashboard" src="https://github.com/user-attachments/assets/87593829-ef9e-4306-b090-780e34ea47d9" />
  <br />
  <em>admin panel dashboard</em>
</p>

See the full [Docker Guide](docker/README.md) for GPU mode, volumes, and configuration.

#### Pre-built image (server only)

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 3000:3000 schmitech/orbit:basic
```

If Ollama runs on your host, add `-e OLLAMA_HOST=host.docker.internal:11434` so the container can reach it. Includes simple-chat only.

#### From release tarball (production)

```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.6.6/orbit-2.6.6.tar.gz -o orbit-2.6.6.tar.gz
tar -xzf orbit-2.6.6.tar.gz && cd orbit-2.6.6

cp env.example .env && ./install/setup.sh
source venv/bin/activate
./bin/orbit.sh start && cat ./logs/orbit.log
```

---

### Resources

- [Step-by-Step Tutorial](docs/tutorial.md) — Chat with your own data in minutes
- [Cookbook](docs/cookbook/) — 20+ recipes: database copilots, voice assistants, fault tolerance, MCP agents, private gateways
- [Documentation](docs/) — Full architecture and setup guides
- [GitHub Issues](https://github.com/schmitech/orbit/issues) — Bug reports and feature requests

---

### Roadmap

- More ready-to-run adapter templates for common business systems
- More MCP recipes for agent platforms and desktop clients
- Expanded evaluation, tracing, and observability workflows
- Admin UI improvements for configuration, diagnostics, and operations
- Additional deployment templates for private cloud and regulated environments

---

### Contributing

Contributions are welcome! Check the [issues](https://github.com/schmitech/orbit/issues) for good first tasks, or open a new one to discuss your idea.

If ORBIT helps you build private RAG, agent tools, or AI gateway infrastructure, a **[star](https://github.com/schmitech/orbit)** helps others find the project and follow its development.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
