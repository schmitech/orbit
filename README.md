<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT" width="160" />
  </a>

  # ORBIT

  ## Connect private data and internal tools through one OpenAI-compatible API

  Connect files, databases, vector stores, models, APIs, and MCP tools. Run locally or in your cloud—with authentication, observability, and governance built in.
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars" /></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit?color=red" alt="Last commit" /></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/badge/version-2.11.0-blue" alt="Version 2.11.0" /></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache 2.0 license" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+" /></a>
</p>

<p align="center">
  <a href="#-quick-start"><strong>Quick start</strong></a>
  &nbsp;•&nbsp;
  <a href="#see-orbit-in-action"><strong>Watch the demo</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/tutorial.md"><strong>Tutorial</strong></a>
  &nbsp;•&nbsp;
  <a href="docs/"><strong>Documentation</strong></a>
</p>

<div id="see-orbit-in-action" align="center">
  <video src="https://github.com/user-attachments/assets/9d09fb57-ed65-4426-857c-cd2f76a58c8c" controls muted playsinline width="85%"></video>
  <br />
  <em>Upload PDFs, spreadsheets, and images, then query them together with context preserved across the conversation.</em>
</div>

> ⭐ **Cloning ORBIT?** If it looks useful, [star the repository](https://github.com/schmitech/orbit). It helps other developers discover the project and signals that we should keep investing in new model, datasource, and agent integrations.

---

## One backend for private AI applications

| | What ORBIT gives you |
| :---: | :--- |
| **Connect anything** | Query files, SQL, NoSQL, vector stores, Elasticsearch, REST/GraphQL APIs, and MCP tools in natural language across multiple languages. |
| **Use any model** | Route one API contract across local models such as Ollama, llama.cpp, and vLLM or cloud providers such as OpenAI, Anthropic, Gemini, Bedrock, and Azure. |
| **Operate it safely** | Ship with API keys, RBAC, SSO, quotas, moderation, fallbacks, metrics, audit logs, and an admin panel instead of assembling them yourself. |

ORBIT sits between your applications and the models, data, and tools they need. Define adapters in YAML, expose them through one OpenAI-compatible endpoint, and move from a local prototype to a governed deployment without replacing the architecture.

> **Where does it fit?** ORBIT combines an AI gateway with retrieval and tool execution. It is a backend API rather than just a chat UI, and it includes production controls rather than leaving them to application code. See [ORBIT vs. Open WebUI](docs/openwebui/orbit-vs-openwebui.md) and [ORBIT vs. LiteLLM](docs/litellm/orbit-vs-litellm.md).

## 🚀 Quick Start

No clone, no build, no config file to hand-edit. Pull a flavor image and run it — ORBIT, the orbitchat web UI, and a full multimodal document-chat setup (PDF, Word, Excel, images, Markdown) are all inside.

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

<details open>
<summary><strong>Ask database questions in multiple languages</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/4af9005e-a9c9-4f37-8f6a-84d86e6f6dde" controls muted playsinline width="80%"></video>
  <br />
  <em>ORBIT generates the query, runs it against the database, and charts the result in chat.</em>
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
</p>
</details>

<details>
<summary><strong>Operate the gateway</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/81730186-8dba-4cfa-8613-af5efd82e4c8" controls muted playsinline width="80%"></video>
  <br />
  <em>Monitor health, latency, tokens, sessions, adapters, and logs behind API keys, quotas, and rate limits.</em>
</p>
</details>

## Why ORBIT?

| If you need… | ORBIT gives you… |
| :--- | :--- |
| More than model routing | RAG, structured-data retrieval, web search, and tool execution behind the gateway. |
| More than a chat interface | A backend that works with ORBIT Chat or any client that can call an OpenAI-compatible API. |
| More than a prototype framework | Authentication, RBAC, SSO, quotas, moderation, circuit breakers, fallbacks, metrics, and audit logs. |
| Private deployment | Local inference, encrypted file storage, cloud secret managers, and fully offline operation. |
| Less orchestration code | YAML-defined adapters, datasources, prompts, provider routing, and guardrails. |

## Capabilities

| Capability | Included |
| :--- | :--- |
| **Model gateway** | 37+ local and cloud providers, OpenAI-compatible APIs, per-key routing, model switching, retries, and fallbacks. |
| **Retrieval** | Vector RAG, file and multimodal RAG, SQL, MongoDB, Elasticsearch, REST, GraphQL, web search, and multi-source answers. |
| **Agents and protocols** | MCP tool calling, bounded multi-step loops, natural-language skill routing, A2A, and asynchronous RabbitMQ requests. |
| **Media** | Image, video, speech, PDF, Word, Excel, PowerPoint, CSV, and markdown generation. |
| **Security** | API keys, RBAC, Entra ID and Auth0 SSO, rate limits, quotas, moderation, AES-256-GCM file encryption, and cloud secret managers. |
| **Operations** | Admin UI, health checks, metrics, audit logs, circuit breakers, datasource pooling, and hot adapter reloads. |

[Browse all adapters](docs/adapters/adapters.md) · [See provider configuration](config/inference.yaml) · [Read the configuration reference](install/default-config/config.yaml)

## Architecture

<p align="center">
  <img src="https://github.com/user-attachments/assets/b2fcbed3-5c28-4d1a-85bd-edc3b7299f6d" alt="ORBIT request and integration architecture" width="700" />
  <br />
  <em>Authenticate and route REST, OpenAI-compatible, MCP, A2A, or message-queue requests to models, private data, and tools.</em>
</p>

## Used in production

<p align="center">
  <video src="https://github.com/user-attachments/assets/82b92525-cc37-47af-bd47-b3ef9dd6ece8" controls muted playsinline width="80%"></video>
  <br />
  <em><a href="https://dialoga.ca">Dialoga</a>, a Canadian AI chat product, is built on ORBIT. The hosted service is currently limited to Canadian IP addresses.</em>
</p>

ORBIT is actively maintained, Apache 2.0 licensed, and developed in the open. See the [release history](https://github.com/schmitech/orbit/releases), [changelog](CHANGELOG.md), [security policy](SECURITY.md), and [commit history](https://github.com/schmitech/orbit/commits/main).

## Clients and documentation

| Start here | Resource |
| :--- | :--- |
| **Learn ORBIT** | [Tutorial](docs/tutorial.md) · [Your first chat](docs/tutorial/first-chat.md) · [HTTP APIs](docs/tutorial/http-apis.md) |
| **Configure adapters** | [Adapter overview](docs/adapters/adapters.md) · [Configuration guide](docs/adapters/adapter-configuration.md) |
| **Connect private data** | [Files](docs/adapters/file-adapter-guide.md) · [Vector stores](docs/vector-stores/vector_store_integration_guide.md) · [SQL](docs/sql-retriever-architecture.md) |
| **Build agents** | [MCP tools](docs/tutorial/mcp-tool-calling.md) · [Auto skill routing](docs/tutorial/auto-skill-routing.md) · [A2A](docs/a2a-protocol.md) |
| **Run in production** | [Authentication](docs/authentication.md) · [Rate limiting](docs/rate-limiting-architecture.md) · [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md) |
| **Use a client** | [ORBIT Chat](clients/orbitchat/) · [Node.js SDK](clients/node-api/) · [API key and Python examples](docs/api-keys.md) |

## Contributing

Contributions are welcome: new retrievers and provider integrations, deployment guides, tests, fixes, and documentation. Read [CONTRIBUTING.md](CONTRIBUTING.md), pick an [open issue](https://github.com/schmitech/orbit/issues), or start a discussion.

Maintained by [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/).

## License

ORBIT is licensed under the [Apache License 2.0](LICENSE).
