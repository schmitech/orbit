<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT" width="160" />
  </a>

  # ORBIT
  ### Open Retrieval-Based Inference Toolkit

  Connect your data (files, databases, APIs, and MCP tools) to any local or cloud LLM. Exposes a unified endpoint for your apps, with built-in authentication and observability.
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars" /></a>
  <a href="https://orbit.schmitech.ca/"><img src="https://img.shields.io/badge/Live_Sandbox-Try_Orbit-7C3AED?logo=playstation&logoColor=white" alt="Live Sandbox" /></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit?color=red" alt="Last commit" /></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/badge/version-2.15.3-blue" alt="Version 2.15.3" /></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache 2.0 license" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+" /></a>
</p>

<p align="center">
  <a href="https://orbit.schmitech.ca/"><strong>⚡ Try Live Sandbox</strong></a>
  &nbsp;•&nbsp;
  <a href="#-quick-start"><strong>Quick start</strong></a>
  &nbsp;•&nbsp;
  <a href="#see-orbit-in-action"><strong>Watch the demo</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/tutorial.md"><strong>Tutorial</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/"><strong>Documentation</strong></a>
</p>

<br>

<div id="see-orbit-in-action" align="center">
  <video src="https://github.com/user-attachments/assets/4af9005e-a9c9-4f37-8f6a-84d86e6f6dde" controls muted playsinline width="85%"></video>
  <br />
  <em>Ask database questions in plain language, in any language.<br />ORBIT picks a reviewed query template, runs its parameterized query, and charts the result in chat.</em>
  <br />
  👉 <strong><a href="https://orbit.schmitech.ca/intent-sql-postgres">Try the SQL Database query demo live →</a></strong>
</div>

> [!NOTE]
> **Deterministic structured retrieval:** For intent-based SQL and API adapters, ORBIT uses
> embeddings and reranking to select from reviewed, predefined query templates, then executes
> the template's predefined, parameterized SQL or query DSL. It does not use an LLM to generate
> arbitrary datasource queries.

<br>

<div align="center">
  <video src="https://github.com/user-attachments/assets/29bd32ae-8849-4b5e-a669-e6442b30a8b8" controls muted playsinline width="85%"></video>
  <br />
  <em>Chat with a private HR database using Ollama models.<br />Uses a deterministic retrieval adapter to select a reviewed query template with embeddings, then returns the answer in chat.</em>
  <br />
  👉 <strong><a href="https://orbit.schmitech.ca/hr-db-chatbot">Try the HR database demo live →</a></strong>
</div>

<br>

> ⭐ **Cloning ORBIT?** If it looks useful, [star the repository](https://github.com/schmitech/orbit). It helps other developers discover the project and signals that we should keep investing in new model, datasource, and agent integrations.

---

## One backend for private AI applications

| | What ORBIT gives you |
| :---: | :--- |
| **Connect anything** | Query files, SQL, NoSQL, vector stores, Elasticsearch, REST/GraphQL APIs, and MCP tools in natural language across multiple languages. |
| **Use any model** | Route one API contract across local models such as Ollama, llama.cpp, and vLLM or cloud providers such as OpenAI, Anthropic, Gemini, Bedrock, and Azure. |
| **Operate it safely** | Ship with API keys, RBAC, SSO, quotas, moderation, fallbacks, metrics, audit logs, and an admin panel instead of assembling them yourself. |

ORBIT sits between your applications and the models, data, and tools they need. Define adapters in YAML, expose them through one OpenAI-compatible endpoint, and move from a local prototype to a governed deployment without replacing the architecture.

> **Where does it fit?** Open WebUI gives you a chat UI. LiteLLM routes model calls. ORBIT is the layer underneath both: it turns a natural-language question into a governed, auditable query against your own databases, APIs, and tools — and ships the auth, quotas, moderation, and audit trail that requires. [See the head-to-head comparison ↓](#how-orbit-differs-from-open-webui-and-litellm)

ORBIT is actively maintained. See the [release history](https://github.com/schmitech/orbit/releases), [changelog](CHANGELOG.md), and [commit history](https://github.com/schmitech/orbit/commits/main).

## 🚀 Quick Start

<div align="center">
  <a href="https://orbit.schmitech.ca/"><img src="https://img.shields.io/badge/TRY%20ORBIT%20LIVE-Explore%20the%20Sandbox%20%E2%86%92-7C3AED?style=for-the-badge" alt="Try ORBIT live — explore the sandbox" /></a>
  <br />
  <strong>See what ORBIT can do before you install:</strong> explore the live sandbox instantly—no download, Docker, or setup required.
</div>

<br />

Otherwise, skip the clone and config-file editing — pull a flavor image and run it. ORBIT, the orbitchat web UI, and a minimalistic document-chat setup are all inside to get you started in minutes.

**Prerequisites:** Docker, 4 GB of free RAM, and 3 GB of disk space.

<details open>
<summary><strong>Option 1: Local / Offline (Ollama)</strong></summary>

```bash
docker pull schmitech/orbit-ollama:latest
docker run -d --name orbit -p 5173:5173 -p 3000:3000 \
  -v orbit-data:/orbit/data \
  -v orbit-models:/orbit/models \
  schmitech/orbit-ollama:latest
```

The first run downloads the local chat/vision model (`gemma4:e2b`, ~7.2 GB) inside the container and will take some time to complete startup depending on your internet connection speed. Once pulled, open [http://localhost:5173](http://localhost:5173) and start chatting — upload a PDF, a spreadsheet, or an image and ask about it. No cloud account or API key required.

| | Model |
| :--- | :--- |
| Chat | `gemma4:e2b` (Ollama) |
| Vision | `gemma4:e2b` (Ollama) |
| Embeddings | `nomic-embed-text` (Ollama) |
</details>

<details>
<summary><strong>Option 2: OpenAI Hosted Model</strong></summary>

```bash
export OPENAI_API_KEY=sk-...

docker pull schmitech/orbit-openai:latest
docker run -d --name orbit -p 5173:5173 -p 3000:3000 \
  -e OPENAI_API_KEY \
  -v orbit-data:/orbit/data \
  schmitech/orbit-openai:latest
```

| | Model |
| :--- | :--- |
| Chat | `gpt-5.4-mini` (also selectable: `gpt-5.4`, `gpt-5.4-nano`) |
| Vision | `gpt-5.5` |
| Embeddings | `text-embedding-3-small` |
</details>

<details>
<summary><strong>Option 3: Gemini Hosted Model</strong></summary>

```bash
export GOOGLE_API_KEY=...

docker pull schmitech/orbit-gemini:latest
docker run -d --name orbit -p 5173:5173 -p 3000:3000 \
  -e GOOGLE_API_KEY \
  -v orbit-data:/orbit/data \
  schmitech/orbit-gemini:latest
```

| | Model |
| :--- | :--- |
| Chat | `gemini-3.1-pro-preview` (also selectable: `gemini-3.6-flash`) |
| Vision | `gemini-3.6-flash` |
| Embeddings | `gemini-embedding-2-preview` |
</details>

> [!TIP]
> These are just the defaults. Change the active model per adapter from the Admin Panel's adapter settings (persists across restarts, stored in the `orbit-data` volume), or inspect/edit the resolved YAML directly at `/orbit/config-runtime/adapters/multimodal.yaml` inside the running container (`docker exec -it orbit sh`) — note that a container restart regenerates this file from the image default, so edits there don't survive a restart on their own.

> [!NOTE]
> `-e OPENAI_API_KEY` (no `=value`) passes through whatever that variable is already set to in your shell — export it first, don't paste the key inline as `-e OPENAI_API_KEY=sk-...`, which would leave it sitting in your shell history. Each cloud flavor needs exactly one credential — the same key powers chat, vision, and embeddings, so nothing silently falls back to a different provider. `docker pull` never needs, receives, or persists a credential; only `docker run` does.

Port `5173` is the chat UI, `3000` is the OpenAI-compatible API if you want to call ORBIT directly:

```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: multimodal' \
  -H 'X-Session-ID: local-test' \
  -d '{"messages":[{"role":"user","content":"What can ORBIT connect to?"}]}'
```

You can also access the Admin Panel at [http://localhost:3000/admin](http://localhost:3000/admin) (default credentials: username `admin`, password `admin123` — which can be changed inside the admin panel).

<br>
<div align="center">
  <video src="https://github.com/user-attachments/assets/13f03f18-8421-48a1-8643-fd6a488fdec7" controls muted playsinline width="85%"></video>
  <br />
  <em>Monitor health, latency, usage, costs, feedback, sessions, and audit events; manage users, API keys, quotas, adapters settings, MCP servers, and logs in one place.</em>
</div>
<br>

> [!IMPORTANT]
> These images ship with a default database and API key for first-run convenience. Rotate the default API key/admin password before exposing ORBIT beyond localhost.

For production deployments, **ALWAYS** use the latest stable [release](https://github.com/schmitech/orbit/releases).

You can also follow the [Docker guide](docker/README.md), [tutorial](docs/tutorial.md), or [Windows guide](install/windows.md).

---

## What you can build

| Goal | ORBIT handles |
| :--- | :--- |
| **Chat with private documents** | Upload PDFs, office documents, spreadsheets, images, and audio; retrieve relevant context across a conversation. [Try the tutorial →](docs/tutorial/chat-with-files.md) |
| **Query databases in multiple languages** | Generate and execute safe queries across SQL, MongoDB, Elasticsearch, and composite datasources. [Try the SQL demo →](docs/tutorial/sql-database-sqlite.md) |
| **Build tool-using agents** | Give models scoped access to MCP servers with bounded, multi-step server-side tool loops. [Read the MCP guide →](docs/adapters/mcp-agent.md) |
| **Offer one governed AI endpoint** | Route local and cloud models with per-key access, quotas, fallbacks, moderation, metrics, and auditability. [Create your first key →](docs/tutorial/creating-api-keys.md) |

<details>
<summary><strong>Chat with private documents</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/9d09fb57-ed65-4426-857c-cd2f76a58c8c" controls muted playsinline width="80%"></video>
  <br />
  <em>Upload PDFs, spreadsheets, and images, then query them together with context preserved across the conversation.</em>
  <br />
  👉 <a href="https://orbit.schmitech.ca/chat-with-files/"><strong>Try this live in your browser →</strong></a>
</p>
</details>

<details>
<summary><strong>Talk to a real-time voice assistant grounded in your data</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/d1214904-267e-4295-8a0c-246dd37b7e56" controls muted playsinline width="80%"></video>
  <br />
  <em>Speech-to-speech voice grounded in SQL databases, APIs, or data lakes — interrupt it mid-answer and it stops and responds immediately.</em>
</p>
</details>

<details>
<summary><strong>Let the model use internal tools</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/a57ff84e-db9d-466d-8f82-e23473b745fb" controls muted playsinline width="80%"></video>
  <br />
  <em>Connect filesystem, Slack, Postgres, GitHub, Jira, and other MCP servers without adding an agent framework.</em>
  <br />
  👉 <a href="https://orbit.schmitech.ca/mcp-business-sample"><strong>Try the MCP tool calling demo live →</strong></a>
</p>
</details>

<details>
<summary><strong>Real-Time Business & Revenue Intelligence (MCP Tool Calling)</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/b177b234-e64f-491a-8c3e-8294774c548c" controls muted playsinline width="80%"></video>
  <br />
  <em>Multi-step agent reasoning across 9 synthetic MCP tools: CRM health, telemetry seat utilization, P1 support escalations, and churn risk simulation.</em>
  <br />
  👉 <a href="https://orbit.schmitech.ca/mcp-business-sample"><strong>Try the Business & Revenue Intelligence MCP demo live →</strong></a>
</p>
</details>

## How ORBIT differs from Open WebUI and LiteLLM

Open WebUI is a chat application. LiteLLM is a model router. ORBIT is neither — it is the layer where a question becomes a **governed query against your own systems of record**, and it ships the production controls that decision requires.

| | Open WebUI | LiteLLM | ORBIT |
| :--- | :--- | :--- | :--- |
| **Structured data (SQL, Mongo, Elasticsearch, REST, GraphQL)** | Vector stores only | None | First-class datasources |
| **How database queries are produced** | n/a | n/a | Reviewed, parameterized templates selected by embeddings + reranking — the LLM never emits SQL |
| **Natural-language intent routing** | Model/pipeline routing | Model-selection routing | Routes the query to the right datasource and skill |
| **MCP** | Client | Client | **Server _and_ client** — with lifecycle management, pooling, and circuit breaking |
| **Cost attribution** | Provider-dependent | Per LLM call | Per call type: inference, embeddings, image/video/audio, OCR, realtime voice, MCP tool loops, reranking |
| **Deny-by-identity** | Requires an existing account row | Virtual keys are allow-list only | Wildcard blacklist on email/user_id/username — blocks external SSO users who have never logged in, revokes live sessions immediately |
| **File encryption at rest** | Not available | AWS KMS on S3 only | AES-256-GCM on any backend, no cloud KMS required |
| **Async ingestion** | HTTP/WebSocket only | OpenAI Batches (submit/poll) | Broker-native RabbitMQ, at-least-once, dead-lettering, same pipeline as `/v1/chat` |
| **Fault tolerance** | Fallback routing | Cooldowns | Circuit breakers across providers, datasources, and MCP servers |
| **Licensing** | Open source | Open core — some features are commercial | Apache 2.0, no paywalled features |

**The one that matters most:** for intent-based SQL and API adapters, ORBIT does not ask an LLM to write a query. It selects from reviewed, predefined templates and executes the template's parameterized statement. The same question produces the same statement every time — you can unit-test it, review it in a pull request, and show an auditor exactly what ran. An unmatched intent fails visibly instead of inventing a number. That tradeoff is why ORBIT can be pointed at a production database.

Full breakdowns: [ORBIT vs. Open WebUI](docs/openwebui/orbit-vs-openwebui.md) · [ORBIT vs. LiteLLM](docs/litellm/orbit-vs-litellm.md)

## Capabilities

| Capability | Included |
| :--- | :--- |
| **Model gateway** | 37+ local and cloud providers, OpenAI-compatible APIs, per-key routing, model switching, retries, and fallbacks. |
| **Retrieval** | Vector RAG, file and multimodal RAG, SQL, MongoDB, Elasticsearch, REST, GraphQL, web search, and multi-source answers. |
| **Agents and protocols** | MCP tool calling, bounded multi-step loops, natural-language skill routing, A2A, and asynchronous RabbitMQ requests. |
| **Media** | Image, video, speech, PDF, Word, Excel, PowerPoint, CSV, and markdown generation. |
| **Security** | API keys, RBAC, Entra ID and Auth0 SSO, rate limits, quotas, moderation, AES-256-GCM file encryption, and cloud secret managers. |
| **Operations** | Admin UI, health checks, metrics, audit logs, per-request token and estimated-cost tracking, spend analytics, circuit breakers, datasource pooling, and hot adapter reloads. |

[Browse all adapters](docs/adapters/adapters.md) · [See provider configuration](config/inference.yaml) · [Read the configuration reference](install/default-config/config.yaml)

## Architecture

<p align="center">
  <img src="https://github.com/user-attachments/assets/b2fcbed3-5c28-4d1a-85bd-edc3b7299f6d" alt="ORBIT request and integration architecture" width="700" />
  <br />
  <em>Authenticate and route REST, OpenAI-compatible, MCP, A2A, or message-queue requests to models, private data, and tools.</em>
</p>

## Clients and documentation

| Start here | Resource |
| :--- | :--- |
| **Learn ORBIT** | [Tutorial](docs/tutorial.md) · [Your first chat](docs/tutorial/first-chat.md) · [HTTP APIs](docs/tutorial/http-apis.md) |
| **Configure adapters** | [Adapter overview](docs/adapters/adapters.md) · [Configuration guide](docs/adapters/adapter-configuration.md) |
| **Connect private data** | [Files](docs/adapters/file-adapter-guide.md) · [Vector stores](docs/vector-stores/vector_store_integration_guide.md) · [SQL](docs/sql-retriever-architecture.md) |
| **Build agents** | [MCP tools](docs/tutorial/mcp-tool-calling.md) · [Auto skill routing](docs/tutorial/auto-skill-routing.md) · [A2A](docs/a2a-protocol.md) |
| **Run in production** | [Authentication](docs/authentication.md) · [Usage and cost tracking](docs/token-usage-and-cost-tracking.md) · [Rate limiting](docs/rate-limiting-architecture.md) · [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md) |
| **Use a client** | [ORBIT Chat](clients/orbitchat/) · [Node.js SDK](clients/node-api/) · [API key and Python examples](docs/api-keys.md) |

## Contributing

Contributions are welcome: new retrievers and provider integrations, deployment guides, tests, fixes, and documentation. Read [CONTRIBUTING.md](CONTRIBUTING.md), pick an [open issue](https://github.com/schmitech/orbit/issues), or start a discussion.

Maintained by [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/).

## License

ORBIT is licensed under the [Apache License 2.0](LICENSE).
