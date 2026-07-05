<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT Logo" width="200"/>
  </a>

  # ORBIT

  ### Open Retrieval-Based Inference Toolkit
  **A self-hosted, OpenAI-compatible AI gateway for private RAG, natural-language data access, and tool-calling agents — run it in your own environment across 37+ model providers.**
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars"></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit?color=red" alt="Last commit"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12+-blue.svg?logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/badge/version-2.8.2-blue" alt="Version"></a>
</p>

<p align="center">
  <a href="#-quick-start"><strong>Quick Start</strong></a>
  &nbsp;•&nbsp;
  <a href="#-features"><strong>Features</strong></a>
  &nbsp;•&nbsp;
  <a href="#-use-cases"><strong>Use Cases</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/tutorial.md"><strong>Tutorial</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/"><strong>Docs</strong></a>
</p>

---

## What is ORBIT?

ORBIT is a single API gateway that puts production controls in front of any AI model and connects it to your private data. Point one OpenAI-compatible `/v1/chat` endpoint at local or cloud models, ask natural-language questions over your databases and documents, and give models controlled access to tools — all behind API keys, quotas, rate limits, and audit logs you host yourself.

**Reach for ORBIT when you need to:**

- 💬 Query SQL, NoSQL, vector stores, REST/GraphQL APIs, Elasticsearch, and files in plain English
- 🔀 Route one API contract across local (Ollama, llama.cpp, vLLM) and cloud models
- 🛠️ Give models scoped access to MCP tools and multi-step agent workflows
- 🔒 Ship private RAG with auth, quotas, moderation, metrics, and admin controls
- 🧪 Prototype locally, then keep the same architecture in production

> Comparisons: [ORBIT vs. Open WebUI](docs/openwebui/orbit-vs-openwebui.md) · [ORBIT vs. LiteLLM](docs/litellm/orbit-vs-litellm.md)
>
> ⭐ If ORBIT is useful to you, a star helps more developers find it.

---

## 🚀 Quick Start

> [!WARNING]
> **Do not clone and deploy the `main` branch in production.**
> Use the latest stable release tarball from
> [GitHub Releases](https://github.com/schmitech/orbit/releases) instead.
> The `main` branch is intended for development and testing and may include
> unreleased changes.

**Latest stable release tarball** (Linux/macOS):

```bash
curl -LO https://github.com/schmitech/orbit/releases/download/v2.8.2/orbit-2.8.2.tar.gz
tar -xzf orbit-2.8.2.tar.gz && cd orbit-2.8.2
./install/setup.sh        # add --wizard for interactive setup
./bin/orbit.sh start
```

**Docker Compose from `main`** — for local development/testing with Ollama and a
lightweight local model:

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit/docker
docker compose up -d
# NVIDIA GPU: docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

**Windows (native):** see the [Windows installation guide](install/windows.md).

**Verify the gateway:**

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: local-test' \
  -d '{"messages": [{"role": "user", "content": "Summarize ORBIT in one sentence."}], "stream": false}'
```

Then open the admin dashboard at **[http://localhost:3000/admin](http://localhost:3000/admin)** (`admin` / `admin123`) for metrics, latency, sessions, adapters, logs, and health.

📖 Full setup: [Docker Guide](docker/README.md) · [Tutorial](docs/tutorial.md)

---

## ✨ Features

| Capability | What you get |
| :--- | :--- |
| **OpenAI-compatible gateway** | One `/v1/chat` interface across local, self-hosted, and cloud providers. |
| **Model routing (37+ providers)** | Local: Ollama, llama.cpp, vLLM, TensorRT-LLM, Transformers, LM Studio, BitNet. Cloud: OpenAI, Anthropic, Gemini, Bedrock, Vertex, Azure, Groq, Mistral, DeepSeek, xAI, and [many more](docs/configuration.md). |
| **Natural-language data access** | Plain English → SQL, MongoDB, Elasticsearch DSL, REST, GraphQL across Postgres, MySQL, Oracle, SQL Server, DuckDB, Athena, Supabase, Cassandra, Redis, and composite multi-source answers. |
| **Vector RAG** | Chroma, Qdrant, Pinecone, Milvus, Weaviate, Marqo, pgvector, FAISS, DuckDB, Redis, Elasticsearch. |
| **File & multimodal RAG** | PDFs, DOCX, spreadsheets, CSVs, markdown, images, and audio — with cached file context across conversations. |
| **Pluggable file storage** | Store uploads and generated media on local disk (default) or in the cloud — AWS S3, MinIO / SeaweedFS (S3-compatible), Azure Blob, or Google Cloud Storage — selected with one config key. |
| **Web search** | Provider-agnostic real-time context via DuckDuckGo (free), Brave, SearXNG, Serper, Tavily, Google PSE, Perplexity — decoupled from synthesis so any LLM can answer. |
| **MCP tool agents** | Connect MCP servers (filesystem, GitHub, Slack, Postgres, Jira, Notion, and more) over stdio/SSE with bounded, server-side agent loops. |
| **A2A peer protocol** | [Google Agent-to-Agent](https://google.github.io/A2A/) support — discovery via `/.well-known/agent.json` and task delegation over JSON-RPC. [Guide](docs/a2a-protocol.md). |
| **Media generation** | Image, video, PDF, Word, Excel, PowerPoint, CSV, and markdown generation adapters in the same chat flow. |
| **Voice (STT/TTS)** | OpenAI, Whisper, Google, Gemini, ElevenLabs, Coqui, and more. |
| **Production controls** | API keys, RBAC, SSO via Entra ID & Auth0 (OIDC), per-key routing, rate limits, token quotas, moderation, circuit breakers, fallback routing, metrics, audit logs, and hot adapter reloads. |
| **Config-first** | Define adapters, providers, datasources, prompts, and guardrails in YAML — no application code. |

📚 Deep dive: [Docs index](docs/README.md) · [Adapter guide](docs/adapters/adapters.md) · [Configuration](docs/configuration.md) · [Cookbook](docs/cookbook/README.md)

---

## 💡 Use Cases

Same gateway, different jobs. Each use case below maps to a recurring pain that
teams across industries are trying to solve with AI — with a short demo as proof.

| Business outcome | Who feels the pain | What it replaces |
| :--- | :--- | :--- |
| **Answers from scattered documents** | Insurance, legal, finance, research | Hours spent manually cross-referencing PDFs, spreadsheets, and scans |
| **Self-service data access** | Retail, operations, finance, SaaS | BI ticket backlogs and waiting on the data team to write SQL |
| **Faster incident response** | SRE, DevOps, security ops | Bottlenecks where only a few specialists can write query DSL |
| **Automated internal workflows** | IT ops, support, back-office | Manual glue work across databases, Slack, files, and tickets |
| **Conversational tool use, zero orchestration code** | Product, support, SaaS builders | Bolt-on agent frameworks (LangChain, AutoGen) just to get tool calling |
| **AI on regulated data** | Healthcare, government, legal, banking | Compliance blocks on sending sensitive data to cloud LLMs |
| **Governed AI rollout** | Any regulated or enterprise org | Shadow AI with no audit trail, cost control, or visibility |
| **In-flow content generation** | Marketing, e-learning, communications | Slow, fragmented media-production tooling |

<details open>
<summary><strong>Turn scattered documents into instant answers</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/bc85d24a-72dd-4a71-8c3d-017e5fadd219" controls muted playsinline width="80%"></video>
  <br />
  <em>Analysts stop hunting across files: upload PDFs, spreadsheets, and images, then query them together in one thread with context cached across the conversation.</em>
</p>
</details>

<details>
<summary><strong>Let business teams answer their own data questions</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/4af9005e-a9c9-4f37-8f6a-84d86e6f6dde" controls muted playsinline width="80%"></video>
  <br />
  <em>No SQL and no ticket queue: ask in plain English, and ORBIT generates the query, runs it against your database, and charts the result in chat.</em>
</p>
</details>

<details>
<summary><strong>Cut incident response time by searching logs in plain English</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/e7fd2834-e438-4ac1-9173-0c0d56ca562b" controls muted playsinline width="80%"></video>
  <br />
  <em>Investigations no longer stall on DSL expertise: ask operational questions naturally, and ORBIT compiles the Elasticsearch Query DSL and returns the answer.</em>
</p>
</details>

<details>
<summary><strong>Automate multi-step workflows across your internal tools</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/a57ff84e-db9d-466d-8f82-e23473b745fb" controls muted playsinline width="80%"></video>
  <br />
  <em>Replace manual glue work: give models scoped, server-side access to MCP tools — filesystem, Slack, Postgres, GitHub, Jira — with bounded agent loops.</em>
</p>
</details>

<details>
<summary><strong>Let the model call tools on its own, like ChatGPT or Claude</strong></summary>
<p>
  Beyond explicit, client-requested tool skills, any conversational adapter can
  opt into <strong>opportunistic MCP tool calling</strong>: the model decides,
  turn by turn, whether an external tool is needed and calls it inline — no
  <code>skill</code> field, no adapter swap, same thread throughout. Multi-step
  chains, self-correction from tool errors, and mixing several tools in one turn
  all work out of the box, powered by providers' native function calling with
  <strong>no LangChain, AutoGen, or CrewAI dependency</strong> — just a small,
  bounded, fully-owned server-side loop. See the
  <a href="docs/adapters/mcp-agent.md#opportunistic-mode-mcp_tools-capability">opportunistic mode guide</a>.
</p>
</details>

<details>
<summary><strong>Keep regulated data in-house by running AI fully offline</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/565275fa-8f54-4bd6-94de-3fb27a66a5ab" controls muted playsinline width="80%"></video>
  <br />
  <em>Meet data-residency and compliance rules: run local llama.cpp/Ollama models so sensitive PII never leaves your environment.</em>
</p>
</details>

<details>
<summary><strong>Govern and audit every AI interaction</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/f85fb880-9f76-471a-8875-a16d615c3aa8" controls muted playsinline width="80%"></video>
  <br />
  <em>End shadow AI: monitor health, latency, tokens, sessions, adapters, and logs from one dashboard — behind API keys, quotas, and rate limits.</em>
</p>
</details>

<details>
<summary><strong>Generate on-brand media inside the same chat flow</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/0f0c88f2-20b2-4617-9e5f-7efd823fc164" controls muted playsinline width="80%"></video>
  <br />
  <em>Produce content without leaving the conversation: generate images and video as cross-adapter skills that carry conversation context.</em>
</p>
</details>

<details>
<summary><strong>More capabilities</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/1c7b4bb6-4067-40f5-982c-c9ad6faf663d" controls muted playsinline width="80%"></video>
  <br /><em>Render dynamic LLM-generated SVGs inline.</em>
</p>
<p align="center">
  <video src="https://github.com/user-attachments/assets/a3fd7308-64be-4216-823b-954e2e37bad2" controls muted playsinline width="80%"></video>
  <br /><em>Switch inference models mid-conversation without breaking chat history.</em>
</p>
<p align="center">
  <video src="https://github.com/user-attachments/assets/55a1f582-5ea4-411d-bbfc-4ccffbd6f81a" controls muted playsinline width="80%"></video>
  <br /><em>Sub-conversation threading and document caching for faster retrieval.</em>
</p>
</details>

---

## 🏗️ Architecture

```text
Client / Chat UI  |  OpenAI SDK  |  MCP agent  |  A2A peer agent
                           |
                           v
              ORBIT API  (REST · OpenAI-compat · MCP · A2A)
                           |
      +--> API keys, auth, quotas, rate limits, metrics, audit logs
      |
      +--> Adapter router
             +--> Passthrough chat
             +--> File and vector RAG
             +--> SQL / NoSQL / DuckDB / Athena
             +--> REST / GraphQL / Elasticsearch
             +--> MCP tool agents
             +--> Web search
             +--> Image / video / document generation
      |
      v
Inference, embedding, reranking, vision, STT, TTS, and moderation providers
```

The core idea: an **adapter** maps an API key or route to a model, prompt, retriever, datasource, provider override, and capabilities. That makes ORBIT practical for many specialized assistants without a new backend for each.

---

## 🔌 Clients & Docs

| Client | Description |
| :--- | :--- |
| [**ORBIT Chat**](clients/orbitchat/) | React web chat client. Run it: `ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat` |
| [**Node.js SDK**](clients/node-api/) | Node library for integrating ORBIT into apps. |
| [**Python client**](docs/api-keys.md) | CLI and API examples for key management and chat. |

| Topic | Start here |
| :--- | :--- |
| **Getting started** | [Tutorial](docs/tutorial.md) · [First chat](docs/tutorial/first-chat.md) |
| **Configuration** | [Configuration guide](docs/configuration.md) · [Adapter config](docs/adapters/adapter-configuration.md) |
| **Adapters & RAG** | [Adapters overview](docs/adapters/adapters.md) · [File adapter](docs/adapters/file-adapter-guide.md) |
| **NL data access** | [SQL retriever architecture](docs/sql-retriever-architecture.md) · [Intent SQL RAG](docs/intent-sql-rag-system.md) |
| **MCP agents** | [MCP agent guide](docs/adapters/mcp-agent.md) |
| **Production ops** | [Rate limiting](docs/rate-limiting-architecture.md) · [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md) · [Deployment](docs/cookbook/orbit-server-production-deployment.md) |
| **Auth & SSO** | [Authentication guide](docs/authentication.md) — built-in users, Entra ID & Auth0 |
| **Cookbook** | [Recipe index](docs/cookbook/README.md) |

---

## Contributing

Contributions are welcome — new retrievers, adapters, and provider integrations; better examples and deployment guides; tests, bug fixes, and docs. Start with [CONTRIBUTING.md](CONTRIBUTING.md), open an [issue](https://github.com/schmitech/orbit/issues), or send a PR. Roadmap and active work live in [GitHub Issues](https://github.com/schmitech/orbit/issues).

Maintained by [**Remsy Schmilinsky**](https://www.linkedin.com/in/remsy/).

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
