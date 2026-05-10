<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/e7beb0b9-59a2-4c0c-afaf-a72d445a264c" alt="ORBIT Logo" width="200"/>
  </a>

  <p>ORBIT — Open Retrieval-Based Inference Toolkit</p>
  <h3>A self-hosted AI gateway for private, production-ready RAG across LLMs, databases, APIs, and files.</h3>
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
  &nbsp;|&nbsp;
  <a href="docs/"><strong>Docs</strong></a>
</p>

<p align="center">
  Maintained by <a href="https://schmitech.ca/en/about"><strong>Remsy Schmilinsky</strong></a>
</p>

Teams want AI connected to real business data without sending everything to a SaaS vendor, rewriting applications for every model provider, or maintaining fragile glue code between LLMs, databases, APIs, and files.

ORBIT gives you one OpenAI-compatible gateway for private RAG, model routing, retrieval adapters, conversations, tools, and production controls. Run it on your infrastructure, connect the systems you already use, and choose local or hosted models per workload.

**You can build:**

- Private RAG over documents, databases, APIs, and internal knowledge sources.
- OpenAI-compatible applications that can switch between local models and hosted providers.
- Agent and MCP tools that expose controlled access to business data and actions.

---

## Get Running In 60 Seconds

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

Then test the OpenAI-compatible chat API:

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

ORBIT listens on port 3000. The admin panel is available at [localhost:3000/admin](http://localhost:3000/admin) with the default login `admin` / `admin123`.

For GPU acceleration:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Adapter wiring and sample domains live in [`config/adapters/`](config/adapters/) and [`examples/intent-templates/`](examples/intent-templates/). See the full [Docker Guide](docker/README.md) for GPU mode, volumes, and configuration.

---

## Demo

<p align="center">
  <video src="https://github.com/user-attachments/assets/bc85d24a-72dd-4a71-8c3d-017e5fadd219" controls muted playsinline width="75%"></video>
  <br />
  <em>Upload PDFs, documents, and images, then ask questions across all of them in a single conversation. Context is preserved across turns, and local model deployments keep files and queries on your infrastructure.</em>
</p>

<p align="center">
  <img width="1773" alt="admin panel dashboard" src="https://github.com/user-attachments/assets/87593829-ef9e-4306-b090-780e34ea47d9" />
  <br />
  <em>Admin dashboard for managing ORBIT locally.</em>
</p>

---

## Why ORBIT?

| Common problem | What ORBIT provides |
| :--- | :--- |
| One SDK per provider, with rewrites when you switch | One OpenAI-compatible API across local and hosted providers |
| Separate systems for inference, retrieval, tools, and chat history | One gateway for model calls, adapters, tools, conversations, and clients |
| RAG limited to vector search over clean documents | Retrieval over SQL, NoSQL, HTTP, GraphQL, files, web content, and vector stores |
| Glue scripts between prompts and business systems | Intent adapters, composite adapters, diagnostics, and reusable templates |
| Privacy-sensitive data sent through third-party services by default | Self-hosted deployment with local models, local embeddings, API keys, RBAC, audit logs, and rate limits |
| Provider failures cascading into application failures | Circuit breakers, failover, parallel fan-out, and quota-aware throttling |

---

## Core Capabilities

### AI Gateway

- OpenAI-compatible chat API for existing clients and SDKs.
- Runtime model selection across local models and hosted providers.
- Streaming, provider failover, moderation hooks, and rate limiting.
- Web chat, Node SDK, and compatibility with OpenAI-style clients.

### Retrieval And Adapters

- Intent-based retrieval for natural-language questions over structured data.
- SQL, NoSQL, REST, GraphQL, file, web, vector store, embedding, and reranker integrations.
- Composite adapters that fan one prompt across multiple sources and merge the answer.
- Template diagnostics and autocomplete for building reliable data-backed assistants.

### Private RAG And Conversations

- File-upload RAG for PDFs, documents, images, manuals, contracts, and knowledge bases.
- Conversation threading with cached datasets so follow-ups can reuse retrieved context.
- Multilingual conversation handling across 100+ languages.
- Self-hosted operation for privacy-sensitive and regulated environments.

### Tools, Agents, And Production Controls

- MCP endpoint for OpenClaw, Hermes, Claude Desktop, Cursor, and other MCP clients.
- Cross-adapter skills that can invoke specialized adapters during a conversation.
- API keys, RBAC, quotas, audit logging, admin UI, and circuit breakers.
- Voice assistant support through audio adapters.

---

## Who Is ORBIT For?

- Developers building internal AI apps that need real company data, not isolated chat.
- Teams that need private RAG over documents, databases, APIs, and operational systems.
- Companies avoiding long-term lock-in to a single LLM provider or hosted AI platform.
- Engineers connecting AI to SQL, NoSQL, REST, GraphQL, files, and document stores.
- Builders who want OpenAI-compatible APIs with self-hosted control.

ORBIT is probably more than you need if you only want a thin wrapper around one LLM provider.

---

## What Makes ORBIT Different?

ORBIT is not only a model router. It handles the layers that usually become custom infrastructure in production RAG systems: retrieval, tools, adapters, conversations, access control, and operational safeguards.

- **Retrieval beyond vector search:** use intent templates and adapters for structured databases, APIs, files, web content, and vector stores. [Intent SQL RAG](docs/intent-sql-rag-system.md)
- **Real-world data source support:** query SQL, MongoDB, Elasticsearch, REST, GraphQL, DuckDB, files, and composite sources through one gateway. [Composite adapters](docs/adapters/composite-intent-retriever.md)
- **Local and hosted models:** run private workloads on Ollama, llama.cpp, vLLM, or other local providers, while still supporting hosted LLMs where appropriate.
- **Production controls included:** use API keys, RBAC, quotas, audit logging, moderation, rate limits, and circuit breakers. [Rate limiting](docs/rate-limiting-architecture.md)
- **Agent-ready protocol support:** expose ORBIT-backed chat, RAG, and adapter tools through MCP. [MCP / OpenClaw walkthrough](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md)

---

## Example Use Cases

| Use case | Start here |
| :--- | :--- |
| Chat with a local model through an OpenAI-compatible API | [Step-by-step tutorial](docs/tutorial.md) |
| Ask Postgres, MySQL, MongoDB, DuckDB, or Elasticsearch questions in natural language | [Database copilot](docs/cookbook/build-natural-language-database-copilot-with-orbit.md) |
| Query SQL + NoSQL + REST APIs in one prompt | [Composite adapters](docs/adapters/composite-intent-retriever.md) |
| Upload files and get grounded answers | [File-upload RAG](docs/cookbook/orbit-file-upload-rag.md) |
| Deploy a private AI gateway for regulated data | [Private gateway cookbook](docs/cookbook/deploy-private-ai-gateway-for-regulated-data-with-orbit.md) |
| Run ORBIT as an MCP tool server for agents | [MCP / OpenClaw walkthrough](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md) |
| Build a full-duplex voice assistant | [PersonaPlex voice assistant](docs/cookbook/orbit-personaplex-full-duplex-voice-assistant.md) |

---

## Architecture And Adapters

ORBIT sits between clients, models, and data sources. Clients call the OpenAI-compatible API, ORBIT authenticates and routes the request, adapters retrieve or act on external data, and the selected model generates the response with the retrieved context.

| Layer | Coverage |
| :--- | :--- |
| **Clients and protocols** | Web chat, Node SDK, OpenAI-compatible SDKs, MCP |
| **Model routing** | Hosted providers, local providers, streaming, failover, runtime model selection |
| **Retrieval adapters** | SQL, NoSQL, REST, GraphQL, files, web content, vector stores, composite adapters |
| **RAG workflow** | Intent templates, diagnostics, autocomplete, cached datasets, conversation threading |
| **Operations** | API keys, RBAC, audit logs, quotas, rate limits, moderation, circuit breakers, admin UI |

<details>
<summary><strong>Full provider and integration list</strong></summary>

| Layer | Coverage |
| :--- | :--- |
| **LLM and inference** | 37 providers — OpenAI, Anthropic, Gemini, Cohere, Groq, DeepSeek, Mistral, xAI, AWS Bedrock, Azure, Vertex, Together, Fireworks, Perplexity, Replicate, OpenRouter, Watson, NVIDIA, Hugging Face, Ollama (local/cloud/remote), vLLM, TensorRT-LLM, llama.cpp, Shimmy, BitNet (1.58-bit), Transformers, Z.ai, Cerebras, DeepInfra, LM Studio, Moonshot AI, MiniMax, Nebius, Venice AI, Scaleway |
| **Data sources** | 17 — Postgres, MySQL, MariaDB, SQL Server, Oracle, SQLite, MongoDB, Redis, Cassandra, DuckDB, Athena, Elasticsearch, Supabase + HTTP/REST, GraphQL, Firecrawl |
| **Vector stores** | Chroma, Qdrant, Pinecone, Milvus, Weaviate, Elasticsearch |
| **Embeddings** | 10 providers — OpenAI, Cohere, Jina, Voyage, Mistral, Gemini, OpenRouter, Ollama, llama.cpp, Sentence-Transformers |
| **Rerankers** | 6 providers — Cohere, Jina, Voyage, OpenAI, Anthropic, Ollama |
| **Moderation and guardrails** | OpenAI, Anthropic, Llama Guard (local), pluggable chain |
| **Voice** | Full-duplex speech-to-speech via PersonaPlex; STT with Whisper, Google, Gemini; TTS with OpenAI, ElevenLabs, Coqui |
| **Protocols** | OpenAI-compatible chat API and MCP for OpenClaw, Hermes, Claude Desktop, Cursor, or any MCP client |

</details>

---

## More Demos

<details>
<summary><strong>Show videos</strong></summary>

<p align="center">
  <video src="https://github.com/user-attachments/assets/565275fa-8f54-4bd6-94de-3fb27a66a5ab" controls muted playsinline width="75%"></video>
  <br />
  <em>Private local AI model analyzing sensitive PII data offline.</em>
</p>

<p align="center">
  <video src="https://github.com/user-attachments/assets/a3fd7308-64be-4216-823b-954e2e37bad2" controls muted playsinline width="75%"></video>
  <br />
  <em>Runtime model switching during a conversation, including chat history.</em>
</p>

<p align="center">
  <video src="https://github.com/user-attachments/assets/55a1f582-5ea4-411d-bbfc-4ccffbd6f81a" controls muted playsinline width="75%"></video>
  <br />
  <em>Conversation threading with multi-turn follow-ups on the same result set. Source: <a href="examples/intent-templates/duckdb-intent-template/examples/analytics/">examples/intent-templates/duckdb-intent-template/examples/analytics</a>.</em>
</p>

<p align="center">
  <video src="https://github.com/user-attachments/assets/73671841-392f-47e6-9554-d97f975f0b75" controls muted playsinline width="75%"></video>
  <br />
  <em>Cross-adapter skills for tasks such as image generation during a conversation. <a href="docs/adapters/skills.md">Learn more</a>.</em>
</p>

<p align="center">
  <video src="https://github.com/user-attachments/assets/0f178992-ee7d-4347-b41a-ab27b4ab5709" controls muted playsinline width="75%"></video>
  <br />
  <em>OrbitChat rendering live charts from LLM output with no client-side charting code required.</em>
</p>

<p align="center">
  <video src="https://github.com/user-attachments/assets/268801ff-5e17-4358-9e69-b2667851d611" controls muted playsinline width="75%"></video>
  <br />
  <em>Image generation as a cross-adapter skill with conversation and thread context.</em>
</p>

</details>

---

## Deployment Options

### Docker Compose

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

This starts ORBIT with Ollama and SmolLM2, pulls models automatically, and exposes the API on port 3000. The web admin UI is at `/admin` on the same host.

Connect [orbitchat](https://www.npmjs.com/package/orbitchat) from your host:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat
```

### Pre-Built Image

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 3000:3000 schmitech/orbit:basic
```

If Ollama runs on your host, add `-e OLLAMA_HOST=host.docker.internal:11434` so the container can reach it. The basic image includes `simple-chat` only.

### Release Tarball

Download the current release from [GitHub Releases](https://github.com/schmitech/orbit/releases), then install:

```bash
tar -xzf orbit-<version>.tar.gz && cd orbit-<version>
cp env.example .env && ./install/setup.sh
./bin/orbit.sh start && tail -f ./logs/orbit.log
```

---

## Clients

| Client | Description |
| :--- | :--- |
| **[Web Chat](clients/orbitchat/)** | React chat UI |
| **[Node SDK](clients/node-api/)** | Node client, or use any OpenAI-compatible SDK |

---

## Documentation

- [Step-by-Step Tutorial](docs/tutorial.md) — Chat with your own data in minutes.
- [Cookbook](docs/cookbook/) — Recipes for database copilots, private gateways, file RAG, voice assistants, fault tolerance, and MCP agents.
- [Adapter Configuration](docs/adapters/adapter-configuration.md) — Configure adapters, models, and routing behavior.
- [Server Documentation](docs/server.md) — API, server setup, and MCP protocol details.
- [Docker Guide](docker/README.md) — Docker Compose, GPU mode, volumes, and configuration.

---

## Roadmap

- More ready-to-run adapter templates for common business systems.
- More MCP recipes for agent platforms and desktop clients.
- Expanded evaluation, tracing, and observability workflows.
- Admin UI improvements for configuration, diagnostics, and operations.
- Additional deployment templates for private cloud and regulated environments.

---

## Contributing

Contributions are welcome. Check the [issues](https://github.com/schmitech/orbit/issues) for good first tasks, or open a new issue to discuss your idea.

ORBIT is Apache 2.0, so you can build commercial products on top of it. If ORBIT helps you build private RAG, agent tools, or AI gateway infrastructure, a **[star](https://github.com/schmitech/orbit)** helps others find the project and follow its development.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
