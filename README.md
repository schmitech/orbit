<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo-github.png" alt="ORBIT Logo" width="200"/>
  </a>

  <p>ORBIT — Open Retrieval-Based Inference Toolkit</p>
  <h3>One API for 29 LLM providers, 17 data sources, and your files.</h3>
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
  <a href="https://orbit.schmitech.ai/redoc"><strong>API Reference</strong></a>
  &nbsp;|&nbsp;
  <a href="docker/README.md"><strong>Docker Guide</strong></a>
  &nbsp;|&nbsp;
  <a href="docs/cookbook/"><strong>Cookbook</strong></a>
</p>

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

### What's in the box

| Layer | Coverage |
| :--- | :--- |
| **LLM & inference** | 29 providers — OpenAI, Anthropic, Gemini, Cohere, Groq, DeepSeek, Mistral, xAI, AWS Bedrock, Azure, Vertex, Together, Fireworks, Perplexity, Replicate, OpenRouter, Watson, NVIDIA, Hugging Face, Ollama (local/cloud/remote), vLLM, TensorRT-LLM, llama.cpp, Shimmy, BitNet (1.58-bit), Transformers, Z.ai |
| **Data sources** | 17 — Postgres, MySQL, MariaDB, SQL Server, Oracle, SQLite, MongoDB, Redis, Cassandra, DuckDB, Athena, Elasticsearch, Supabase + HTTP/REST, GraphQL, Firecrawl |
| **Vector stores** | Chroma, Qdrant, Pinecone, Milvus, Weaviate, Elasticsearch |
| **Embeddings** | 10 providers — OpenAI, Cohere, Jina, Voyage, Mistral, Gemini, OpenRouter, Ollama, llama.cpp, Sentence-Transformers |
| **Rerankers** | 6 providers — Cohere, Jina, Voyage, OpenAI, Anthropic, Ollama |
| **Moderation / guardrails** | OpenAI, Anthropic, Llama Guard (local), pluggable chain |
| **Voice** | Full-duplex speech-to-speech via **PersonaPlex**; STT (Whisper, Google, Gemini), TTS (OpenAI, ElevenLabs, Coqui) |
| **Protocols** | OpenAI-compatible chat API + **MCP** — drop-in tool server for [OpenClaw](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md), Claude Desktop, Cursor, or any MCP client |

---

### Why ORBIT stands out

Most AI gateways stop at provider routing. ORBIT is built for the messy parts of production RAG.

- **Intent-based retrieval, not just vector search** — ship real queries, not vector guesses. Users ask in natural language; ORBIT picks the right template and runs the query against your data. [Learn more](docs/intent-sql-rag-system.md).
- **Cross-adapter RAG across mixed databases + APIs** — one question, many sources. Fan a query out to SQL, MongoDB, HTTP, and more in parallel and let the LLM merge the answers. [Learn more](config/adapters/composite.yaml).
- **Template diagnostics** — iterate on intent templates without burning LLM tokens. [Learn more](docs/template-diagnostics.md).
- **Conversation threading with cached datasets** — branch off any turn; follow-ups reuse the retrieved data instead of re-querying the DB. [Learn more](docs/conversation-threading-architecture.md).
- **Circuit breakers + parallel fan-out** — resilient adapter orchestration that survives provider hiccups. [Learn more](docs/fault-tolerance/).
- **Autocomplete that knows your data** — fuzzy-matched suggestions sourced from your intent templates. [Learn more](docs/autocomplete-architecture.md).
- **Two-layer rate limiting** — IP limits plus per-API-key quotas with progressive throttling. [Learn more](docs/rate-limiting-architecture.md).
- **Multilingual by default** — 100+ languages with conversation stickiness so the model doesn't flap between turns. [Learn more](docs/language-detection-architecture.md).
- **OpenClaw / MCP integration** — drop ORBIT into any OpenClaw agent as a tool server with a single config entry. [Learn more](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md).

---

### What can you build with ORBIT?

- **Ask your database questions in any language** — connect Postgres, MySQL, MongoDB, DuckDB, Elasticsearch, or any of the other 12 sources and query them with natural language.
- **Query across Postgres + MongoDB + a REST API in one prompt** — true multi-source RAG, no pipeline glue.
- **Switch LLM providers without changing code** — swap between 29 providers with a single config line.
- **Build full-duplex voice agents** — speech-to-speech with interruption handling via PersonaPlex.
- **Plug ORBIT into OpenClaw in minutes** — one config entry turns ORBIT into a tool server for any OpenClaw agent. [Walkthrough](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md).
- **Power agentic workflows** — MCP-compatible with Claude Desktop, Cursor, and custom agents.
- **Upload files and get answers** — RAG over PDFs, images, and documents out of the box.
- **Add guardrails and moderation** — chain OpenAI, Anthropic, or local Llama Guard moderators.
- **Keep everything private** — self-host on your own infrastructure with RBAC, audit logs, and two-layer rate limiting.

---

### Real-world example: PoliceStats.ca

ORBIT is used in production at [PoliceStats.ca](https://policestats.ca), a public-facing AI search and analytics site for Canadian municipal police open data.

PoliceStats uses ORBIT to:
- Route users across many dataset-specific adapters for cities like Toronto, Ottawa, Montreal, Edmonton, Hamilton, Winnipeg, Saskatoon, Vancouver, and Canada-wide statistics
- Query structured public-safety datasets using natural language
- Return grounded answers with source citations back to the relevant open data portal
- Support both broad city assistants and narrow subdomain assistants
- Power a production web chat experience with typed and voice interaction

PoliceStats is a useful reference if you want to see ORBIT applied to a real vertical product instead of only toy examples: one OpenAI-compatible API, many adapters, structured retrieval over public data, and answers designed for end users rather than internal analysts.

---

### Why ORBIT?

| Without ORBIT | With ORBIT |
| :--- | :--- |
| One SDK per provider, rewrites when you switch | One OpenAI-compatible API across 29 providers |
| Separate pipelines for retrieval and inference | Unified model + retrieval + tooling gateway |
| Fragile glue scripts between data sources and LLMs | 9 intent-adapter archetypes with template diagnostics |
| Separate tools for each database — no way to combine them | Composite adapters fan one prompt across SQL + NoSQL + HTTP, merged by the LLM |
| Cascading failures when a provider hiccups | Circuit breakers, parallel fan-out, progressive throttling |
| No visibility into what models are doing | Built-in RBAC, quota-aware rate limiting, and audit logging |

---

### Clients

| Client | Description |
| :--- | :--- |
| **[Web Chat](clients/orbitchat/)** | React UI |
| **CLI** | `pip install schmitech-orbit-client` |
| **[Mobile](clients/orbit-mobile/)** | iOS & Android (Expo) |
| **[Node SDK](clients/node-api/)** | Or use any OpenAI-compatible SDK |

---

### Deployment options

<details>
<summary><strong>Docker Compose (fastest path)</strong></summary>

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

Starts ORBIT + Ollama with SmolLM2, auto-pulls models, and exposes the API on port 3000. The web admin UI is at `/admin` on the same host. Connect [orbitchat](https://www.npmjs.com/package/orbitchat) from your host:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat
```

See the full [Docker Guide](docker/README.md) for GPU mode, volumes, and configuration.

</details>

<details>
<summary><strong>Pre-built image (server only)</strong></summary>

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 3000:3000 schmitech/orbit:basic
```

If Ollama runs on your host, add `-e OLLAMA_HOST=host.docker.internal:11434` so the container can reach it. Includes simple-chat only.

</details>

<details>
<summary><strong>From release tarball (production)</strong></summary>

```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.6.6/orbit-2.6.6.tar.gz -o orbit-2.6.6.tar.gz
tar -xzf orbit-2.6.6.tar.gz && cd orbit-2.6.6

cp env.example .env && ./install/setup.sh
source venv/bin/activate
./bin/orbit.sh start && cat ./logs/orbit.log
```

</details>

---

### Resources

- [Step-by-Step Tutorial](docs/tutorial.md) — Chat with your own data in minutes
- [Cookbook](docs/cookbook/) — 20+ recipes: database copilots, voice assistants, fault tolerance, MCP agents, private gateways
- [Documentation](docs/) — Full architecture and setup guides
- [GitHub Issues](https://github.com/schmitech/orbit/issues) — Bug reports and feature requests

---

### Contributing

Contributions are welcome! Check the [issues](https://github.com/schmitech/orbit/issues) for good first tasks, or open a new one to discuss your idea.

If you find ORBIT useful, a **[star](https://github.com/schmitech/orbit)** helps others discover the project.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
