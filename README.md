<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT Logo" width="200"/>
  </a>

  # ORBIT

  ### Open Retrieval-Based Inference Toolkit
  **A self-hosted AI gateway for private RAG, natural-language data access, tool-calling agents, and multi-model applications.**
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars"></a>
  <a href="https://github.com/schmitech/orbit/fork"><img src="https://img.shields.io/github/forks/schmitech/orbit?style=social" alt="GitHub forks"></a>
  <a href="https://github.com/schmitech/orbit/watchers"><img src="https://img.shields.io/github/watchers/schmitech/orbit?style=social" alt="GitHub watchers"></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit?color=red" alt="Last commit"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12+-blue.svg?logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/badge/version-2.7.9-blue" alt="Version"></a>
</p>

<p align="center">
  <a href="#start-in-minutes"><strong>Start in Minutes</strong></a>
  &nbsp;•&nbsp;
  <a href="#why-orbit"><strong>Why ORBIT</strong></a>
  &nbsp;•&nbsp;
  <a href="#key-features"><strong>Features</strong></a>
  &nbsp;•&nbsp;
  <a href="#demos"><strong>Demos</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/tutorial.md"><strong>Tutorial</strong></a>
  &nbsp;•&nbsp;
  <a href="docker/README.md"><strong>Docker</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/"><strong>Docs</strong></a>
</p>

<p align="center">
  Maintained by <a href="https://www.linkedin.com/in/remsy/"><strong>Remsy Schmilinsky</strong></a>
</p>

---

## Why ORBIT?

ORBIT is built for teams that need self-hosted AI connected to private data systems, production controls, tool workflows, and an OpenAI-compatible gateway they can run in their own environment.

Use ORBIT when you need to:

- Ask natural-language questions over SQL, NoSQL, vector stores, REST APIs, GraphQL, DuckDB, Elasticsearch logs, and files.
- Route traffic across local and cloud models through one API contract.
- Give models controlled access to MCP tools and multi-step agent workflows.
- Ship private RAG with API keys, quotas, rate limits, moderation, audit logs, metrics, and admin controls.
- Prototype locally with Ollama or llama.cpp, then keep the same architecture for production deployments.

For a comparison of ORBIT and Open WebUI, see the [ORBIT and Open WebUI Comparison Guide](docs/orbit-vs-openwebui.md).

If ORBIT is useful to you, starring the repo helps more developers discover it.

---

## Start in Minutes

### Docker Compose

Clone the repo and boot ORBIT with Ollama and a lightweight local model:

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit/docker
docker compose up -d
```

For NVIDIA GPU acceleration:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

See the [Docker Guide](docker/README.md) for GPU setup, model configuration, volumes, and troubleshooting.

### Release Tarball

Install ORBIT directly into a local Python environment on Linux or macOS:

```bash
curl -LO https://github.com/schmitech/orbit/releases/download/v2.7.9/orbit-2.7.9.tar.gz
tar -xzf orbit-2.7.9.tar.gz
cd orbit-2.7.9

./install/setup.sh
./bin/orbit.sh start
```

Use `./install/setup.sh --wizard` for interactive setup.

### Windows (Native)

```bat
git clone https://github.com/schmitech/orbit.git
cd orbit
install\setup.bat --profile default
bin\orbit.bat start
```

For profiles, GGUF model downloads, PyTorch backend selection, PowerShell setup, and troubleshooting, see the [Windows installation guide](install/windows.md).

### Verify the Gateway

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

Open the admin dashboard at [http://localhost:3000/admin](http://localhost:3000/admin):

- Username: `admin`
- Password: `admin123`

The dashboard shows API metrics, latency, active sessions, configured adapters, logs, and system health.

---

## Key Features

- **OpenAI-compatible AI gateway:** Expose one `/v1/chat` interface across local, self-hosted, and cloud-backed model providers.

- **Local-first inference:** Run with Ollama, Ollama Cloud, remote Ollama, llama.cpp, vLLM, TensorRT-LLM, Transformers, LM Studio, BitNet, and other self-hosted runtimes.

- **Cloud model routing:** Connect OpenAI, Azure OpenAI, Anthropic, Gemini, Vertex AI, AWS Bedrock, Groq, Mistral, DeepSeek, Together, xAI, OpenRouter, Cohere, Perplexity, Fireworks, Replicate, NVIDIA, Cerebras, DeepInfra, Moonshot, MiniMax, Nebius, Venice, Scaleway, Watson, Hugging Face, and more.

- **Natural-language database copilots:** Query PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, SQLite, DuckDB, Supabase, Athena, MongoDB, Cassandra, and Redis-backed data through adapter-driven retrieval.

- **Vector RAG with real store choice:** Use Chroma, Qdrant, Pinecone, Milvus, Weaviate, Marqo, pgvector, FAISS, DuckDB, Redis, and Elasticsearch-backed retrieval.

- **Structured data beyond document chat:** Turn plain English into SQL, Elasticsearch Query DSL, REST API calls, GraphQL requests, MongoDB queries, and cross-source composite answers.

- **File upload and multimodal RAG:** Process PDFs, DOCX, spreadsheets, CSVs, markdown, text, images, and audio, then reuse cached file context across conversations.

- **Provider-agnostic web search:** Bring real-time web context to any LLM using dedicated search backends — DuckDuckGo (free, no key), Brave, SearXNG (self-hosted), Serper, Tavily, Google PSE, and Perplexity. The `web-search` adapter type fetches and injects results so any inference provider (Anthropic, Ollama, OpenAI, …) can synthesize the answer. Gemini, OpenAI, and xAI also support single-call provider-native grounded search.

- **MCP tool-calling agents:** Connect to Model Context Protocol servers over stdio or SSE. Examples include filesystem, GitHub, GitLab, Jira, Confluence, Sentry, Slack, Postgres, Brave Search, Fetch, Google Drive, Notion, Docker, AWS, browser automation, and SharePoint-style remote tools.

- **A2A peer agent protocol:** ORBIT implements the [Google Agent-to-Agent (A2A) protocol](https://google.github.io/A2A/), exposing `/.well-known/agent.json` for discovery and a `POST /a2a` JSON-RPC 2.0 endpoint for task delegation. Other A2A-compatible agents and orchestrators can discover ORBIT's skills, send tasks, and stream responses — using the same API keys as the REST and OpenAI-compatible interfaces. See the [A2A integration guide](docs/a2a-protocol.md).

- **Media and document generation:** Add image, video, PDF, Word, Excel, PowerPoint, CSV, and markdown generation adapters to the same chat workflow.

- **Voice-ready services:** Configure STT and TTS across OpenAI, Whisper, Google, Gemini, ElevenLabs, Ollama, vLLM, Coqui, Anthropic, Cohere, and xAI-style providers.

- **Reranking and embeddings:** Choose embedding and reranking providers independently, including Ollama, OpenAI, Cohere, Jina, Mistral, Gemini, Voyage, OpenRouter, NVIDIA, sentence-transformers, Anthropic, and llama.cpp.

- **Production controls included:** API keys, optional user auth and RBAC, per-key routing, rate limits, token quotas, request throttling, content moderation, circuit breakers, fallback routing, metrics, audit logs, datasource pooling, and hot adapter reloads.

- **Configuration-first architecture:** Define adapters, providers, datasources, prompts, guardrails, and capabilities in YAML without rewriting application code.

Want the deep dive? See the [documentation index](docs/README.md), [adapter guide](docs/adapters/adapters.md), [configuration guide](docs/configuration.md), and [cookbook](docs/cookbook/README.md).

---

## Built for Real Data and Real Operations

ORBIT combines the pieces required to turn private AI experiments into durable applications: data connectors, retrieval strategies, provider routing, tool execution, security controls, and operational visibility.

| Need | ORBIT provides |
| :--- | :--- |
| **Private business data** | SQL, NoSQL, vector, REST, GraphQL, Elasticsearch, DuckDB, files, and composite multi-source retrieval. |
| **Production API layer** | OpenAI-compatible gateway with API keys, quotas, rate limits, routing, metrics, and audit logs. |
| **Domain copilots** | Configured adapters for natural-language database, API, log, file, procurement, HR, analytics, and customer-order workflows. |
| **Real-time web context** | External search backends (DuckDuckGo, Brave, SearXNG, Serper, Tavily, Google PSE, Perplexity) decoupled from synthesis — any LLM can answer from fresh web results. |
| **Tool execution** | MCP-connected agent loops with bounded iterations, timeouts, result limits, and server-side orchestration. |
| **Provider independence** | Separate routing for inference, embeddings, rerankers, vision, image, video, STT, TTS, and moderation providers. |
| **Operational resilience** | Circuit breakers, fallback routing, datasource pooling, hot reloads, and request-level observability. |

---

## Demos

<details open>
<summary><strong>Multi-source RAG and file chat</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/bc85d24a-72dd-4a71-8c3d-017e5fadd219" controls muted playsinline width="80%"></video>
  <br />
  <em>Upload PDFs, spreadsheets, and images, then query them together in a unified thread. ORBIT chunks, embeds, and retrieves documents locally.</em>
</p>
</details>

<details>
<summary><strong>Natural language to database queries</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/745a0635-fe17-432b-9b36-c7b22adcdfcc" controls muted playsinline width="80%"></video>
  <br />
  <em>Translate plain English into SQL, query structured databases, and generate dynamic visualizations directly in chat.</em>
</p>
</details>

<details>
<summary><strong>Agentic MCP and tool-calling loops</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/a57ff84e-db9d-466d-8f82-e23473b745fb" controls muted playsinline width="80%"></video>
  <br />
  <em>Expose local filesystem commands, Slack APIs, Postgres tools, and other MCP servers to multi-step model workflows.</em>
</p>
</details>

<details>
<summary><strong>Elasticsearch log translation</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/e7fd2834-e438-4ac1-9173-0c0d56ca562b" controls muted playsinline width="80%"></video>
  <br />
  <em>Ask operational questions in natural language and let ORBIT compile Elasticsearch Query DSL for logs, error rates, and latency analysis.</em>
</p>
</details>

<details>
<summary><strong>Media and video generation</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/0f0c88f2-20b2-4617-9e5f-7efd823fc164" controls muted playsinline width="80%"></video>
  <br />
  <em>Generate videos with provider-backed generation adapters while keeping orchestration inside the chat workflow.</em>
</p>
<p align="center">
  <video src="https://github.com/user-attachments/assets/268801ff-5e17-4358-9e69-b2667851d611" controls muted playsinline width="80%"></video>
  <br />
  <em>Generate images as a cross-adapter skill using provider-backed image services with conversation context.</em>
</p>
</details>

<details>
<summary><strong>Admin panel and monitoring dashboard</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/f85fb880-9f76-471a-8875-a16d615c3aa8" controls muted playsinline width="80%"></video>
  <br />
  <em>Monitor health, logs, adapter status, tokens, sessions, and query latency from the web dashboard.</em>
</p>
</details>

<details>
<summary><strong>Additional demos</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/565275fa-8f54-4bd6-94de-3fb27a66a5ab" controls muted playsinline width="80%"></video>
  <br />
  <em>Analyze sensitive PII data offline using local llama.cpp models.</em>
</p>
<p align="center">
  <video src="https://github.com/user-attachments/assets/1c7b4bb6-4067-40f5-982c-c9ad6faf663d" controls muted playsinline width="80%"></video>
  <br />
  <em>Render dynamic SVGs generated by LLMs inline.</em>
</p>
<p align="center">
  <video src="https://github.com/user-attachments/assets/a3fd7308-64be-4216-823b-954e2e37bad2" controls muted playsinline width="80%"></video>
  <br />
  <em>Switch inference models mid-conversation without breaking chat history.</em>
</p>
<p align="center">
  <video src="https://github.com/user-attachments/assets/55a1f582-5ea4-411d-bbfc-4ccffbd6f81a" controls muted playsinline width="80%"></video>
  <br />
  <em>Use sub-conversation threading and document caching for faster retrieval.</em>
</p>
</details>

---

## Common Use Cases

- **Internal knowledge assistants:** Query policies, PDFs, spreadsheets, tickets, runbooks, and documentation from a private chat UI.
- **Database copilots:** Convert natural language into SQL, DuckDB, Athena, MongoDB, or Elasticsearch-backed answers.
- **API copilots:** Add a conversational layer to REST and GraphQL systems such as ServiceNow, GitHub, custom business APIs, or public datasets.
- **Local-first AI labs:** Develop against Ollama, llama.cpp, vLLM, TensorRT-LLM, or Transformers before moving selected workloads to cloud models.
- **Tool-using agents:** Give models controlled access to MCP tools while keeping auth, logs, quotas, and policies in one gateway.
- **Customer-facing AI products:** Put stable API keys, request controls, fallback routing, and observability in front of model providers.
- **Regulated data workflows:** Keep sensitive data inside your own deployment while using local embeddings, local models, audit logs, and optional moderation.

---

## Architecture

```text
Client or Chat UI  |  OpenAI SDK  |  MCP agent  |  A2A peer agent
                           |
                           v
              ORBIT API  (REST · OpenAI-compat · MCP · A2A)
                           |
      +--> API keys, auth, quotas, rate limits, metrics, audit logs
      |
      +--> Adapter router
             |
             +--> Passthrough chat
             +--> File and vector RAG
             +--> SQL / NoSQL / DuckDB / Athena
             +--> REST / GraphQL / Elasticsearch
             +--> MCP tool agents
             +--> Web search (DuckDuckGo, Brave, SearXNG, Serper, Tavily, Google PSE, Perplexity)
             +--> Image / video / document generation
      |
      v
Inference, embedding, reranking, vision, STT, TTS, and moderation providers
```

The core idea is simple: an adapter maps an API key or route to a model, prompt, retriever, datasource, provider override, and optional capabilities. That makes ORBIT practical for many specialized assistants without creating a new backend for each one.

---

## Client Integrations

| Client | Path / package | Description |
| :--- | :--- | :--- |
| **ORBIT Chat** | [clients/orbitchat/](clients/orbitchat/) | React web chat client for ORBIT-backed conversations. |
| **Node.js SDK** | [clients/node-api/](clients/node-api/) | Node library for integrating ORBIT backend features into apps. |
| **Python client** | [docs/api-keys.md](docs/api-keys.md) | CLI and API examples for key management and chat requests. |

Run the chat client against a local ORBIT adapter:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat
```

---

## Documentation

| Topic | Start here |
| :--- | :--- |
| **Getting started** | [Tutorial](docs/tutorial.md), [Before you start](docs/tutorial/before-you-start.md), [First chat](docs/tutorial/first-chat.md) |
| **Configuration** | [Configuration guide](docs/configuration.md), [Adapter configuration](docs/adapters/adapter-configuration.md) |
| **Adapters and RAG** | [Adapters overview](docs/adapters/adapters.md), [File adapter](docs/adapters/file-adapter-guide.md), [Multimodal adapter](docs/adapters/multimodal-conversational-adapter.md) |
| **Natural-language data access** | [SQL retriever architecture](docs/sql-retriever-architecture.md), [Intent SQL RAG system](docs/intent-sql-rag-system.md), [DuckDB analytics](docs/tutorial/duckdb-analytics.md) |
| **MCP agents** | [MCP agent guide](docs/adapters/mcp-agent.md), [Use ORBIT with OpenClaw](docs/cookbook/use-orbit-with-openclaw-as-mcp-agent.md) |
| **Production operations** | [Rate limiting](docs/rate-limiting-architecture.md), [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md), [Server deployment](docs/cookbook/orbit-server-production-deployment.md) |
| **Vector stores** | [Vector store integration](docs/vector-stores/vector_store_integration_guide.md), [Embeddings setup](docs/cookbook/orbit-vector-store-embeddings-setup.md) |
| **Cookbook** | [Recipe index](docs/cookbook/README.md) |

---

## Roadmap

Roadmap items and active development tasks are tracked in [GitHub Issues](https://github.com/schmitech/orbit/issues). Requests for new adapters, model providers, deployment patterns, or examples are welcome.

---

## Contributing

Contributions are welcome, especially:

- New retrievers, adapters, and provider integrations.
- Better examples and deployment guides.
- Tests, bug fixes, and documentation improvements.
- Real-world feedback from teams running private RAG, natural-language data access, or model gateway workloads.

Start with [CONTRIBUTING.md](CONTRIBUTING.md), open an [issue](https://github.com/schmitech/orbit/issues), or send a pull request.

---

## Star History

<a href="https://star-history.com/#schmitech/orbit&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=schmitech/orbit&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=schmitech/orbit&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=schmitech/orbit&type=Date" />
  </picture>
</a>

---

## License

ORBIT is licensed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.
