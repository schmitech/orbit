<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT Logo" width="250"/>
  </a>

  # ORBIT

  ### Open Retrieval-Based Inference Toolkit
  **A self-hosted AI gateway for private RAG, tool-calling agents, and multi-model applications.**
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12+-blue.svg?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/badge/version-2.7.7-blue?style=flat-square" alt="Version"></a>
  <a href="https://github.com/schmitech/orbit/pulls"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square" alt="PRs Welcome"></a>
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick Start</strong></a>
  &nbsp;•&nbsp;
  <a href="#demos"><strong>Demos</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/tutorial.md"><strong>Tutorial</strong></a>
  &nbsp;•&nbsp;
  <a href="docker/README.md"><strong>Docker</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/cookbook/"><strong>Cookbook</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/"><strong>Docs</strong></a>
</p>

<p align="center">
  Maintained by <a href="https://www.linkedin.com/in/remsy/"><strong>Remsy Schmilinsky</strong></a>
</p>

---

## Why ORBIT?

Most AI apps start simple, then quickly need retrieval, auth, model routing, file upload, observability, quotas, and a way to connect real business systems. ORBIT packages those pieces into one self-hosted gateway you can run locally, on-prem, or in your own cloud.

Use ORBIT when you want to:

- Build private RAG apps without sending sensitive data to a hosted AI platform by default.
- Switch between local and cloud models without rewriting your frontend.
- Connect LLMs to databases, vector stores, files, APIs, Elasticsearch, GraphQL, DuckDB, and MCP tools.
- Ship an OpenAI-compatible API with API keys, quotas, rate limits, moderation, audit logs, and an admin dashboard.
- Prototype quickly, then keep the same architecture for production.

If that matches a project you are building, starring the repo helps more developers find it.

---

## What You Get

| Capability | What ORBIT provides |
| :--- | :--- |
| **OpenAI-compatible gateway** | A unified chat API for local, self-hosted, and cloud-backed models. |
| **Private RAG infrastructure** | File chat, vector search, SQL/NoSQL retrieval, REST/GraphQL adapters, DuckDB analytics, and Elasticsearch query translation. |
| **Model flexibility** | Run with Ollama, llama.cpp, vLLM, and external model providers behind one gateway contract. |
| **Agentic tool loops** | Connect to Model Context Protocol servers and let models execute multi-step tool workflows inside chat sessions. |
| **Production controls** | API key validation, request limits, token quotas, content moderation, circuit breakers, fallback routing, metrics, and audit logging. |
| **Ready-to-use clients** | A React chat client, Node.js SDK, admin UI, Docker Compose setup, examples, and cookbook recipes. |

---

## Quick Start

### Option A: Release Tarball

Install ORBIT directly into a local Python environment on Linux or macOS:

```bash
curl -LO https://github.com/schmitech/orbit/releases/download/v2.7.7/orbit-2.7.7.tar.gz
tar -xzf orbit-2.7.7.tar.gz
cd orbit-2.7.7

./install/setup.sh
./bin/orbit.sh start

tail -f ./logs/orbit.log
```

Use `./install/setup.sh --wizard` for interactive setup. See the [Getting Started Tutorial](docs/tutorial.md) for configuration and customization.

### Option B: Docker Compose

Clone the repo and boot ORBIT with Ollama and a lightweight local model:

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit/docker
docker compose up -d
```

This starts ORBIT with a local Ollama instance and the `SmolLM2` model. For NVIDIA GPU acceleration:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

See the [Docker Guide](docker/README.md) for GPU setup, model configuration, volumes, and troubleshooting.

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

The dashboard shows API metrics, latency, active sessions, configured adapters, and system health.

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
  <em>Generate images as a cross-adapter skill using DALL-E or Stability AI with conversation context.</em>
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

- **Internal knowledge assistants:** Query policies, PDFs, spreadsheets, tickets, and documentation from a private chat UI.
- **Database copilots:** Convert natural language into SQL, DuckDB, Elasticsearch, REST, or GraphQL-backed answers.
- **Local-first AI labs:** Develop against Ollama, llama.cpp, or vLLM before moving selected workloads to cloud models.
- **Tool-using agents:** Give models controlled access to MCP tools while keeping auth, logs, and policies in one gateway.
- **Customer-facing AI products:** Put stable API keys, quotas, rate limits, and fallback routing in front of model providers.

---

## Client Integrations

| Client | Path / package | Description |
| :--- | :--- | :--- |
| **ORBIT Chat** | [clients/orbitchat/](clients/orbitchat/) | React web chat client for ORBIT-backed conversations. |
| **Node.js SDK** | [clients/node-api/](clients/node-api/) | Node library for integrating ORBIT backend features into apps. |

Run the chat client against a local ORBIT adapter:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat
```

---

## Compared to a Custom Stack

| Problem | Custom setup | ORBIT |
| :--- | :--- | :--- |
| **Provider lock-in** | One SDK and request shape per provider. | One OpenAI-compatible gateway across local and cloud providers. |
| **Glue code sprawl** | Separate auth, RAG, model routing, file handling, metrics, and storage code. | Integrated gateway, adapters, session management, safety controls, and admin UI. |
| **Narrow retrieval** | Vector search over static text chunks only. | Structured data, files, APIs, vector stores, Elasticsearch, DuckDB, and hybrid workflows. |
| **Privacy gaps** | Sensitive data often flows through hosted services by default. | Self-hosted deployment with local models, local embeddings, API keys, RBAC, and audit logs. |
| **Operational fragility** | Slow providers or broken adapters can affect the whole app. | Circuit breakers, fallback routing, rate limits, queues, and observability. |

---

## Learn More

- [Getting Started Tutorial](docs/tutorial.md)
- [Docker Guide](docker/README.md)
- [Cookbook](docs/cookbook/)
- [Docs](docs/)
- [API Keys](docs/api-keys.md)
- [Pipeline Architecture](docs/pipeline-inference-architecture.md)

---

## Roadmap

Roadmap items and active development tasks are tracked in [GitHub Issues](https://github.com/schmitech/orbit/issues). Requests for new adapters, model providers, deployment patterns, or examples are welcome.

---

## Contributing

Contributions are welcome, especially:

- New retrievers, adapters, and provider integrations.
- Better examples and deployment guides.
- Tests, bug fixes, and documentation improvements.
- Real-world feedback from teams running private RAG or model gateway workloads.

Start with [CONTRIBUTING.md](CONTRIBUTING.md), open an [issue](https://github.com/schmitech/orbit/issues), or send a pull request.

If ORBIT is useful to you, please star the repository. It is the simplest way to support the project and helps other developers discover it.

---

## License

ORBIT is licensed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.
