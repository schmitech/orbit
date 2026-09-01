<div align="center">
  <a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=logo">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT" width="160" />
  </a>

  # ORBIT
  ### Open Retrieval-Based Inference Toolkit

  Connect your data (files, databases, APIs, and MCP tools) to any local or cloud LLM. Exposes a unified endpoint for your apps, with built-in authentication and observability.

  <p><strong><a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=hero">Try ORBIT in your browser — no installation required →</a></strong></p>
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars" /></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit?color=red" alt="Last commit" /></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/badge/version-2.17.2-blue" alt="Version 2.17.2" /></a>
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

<br>

<div id="see-orbit-in-action" align="center">
  <video src="https://github.com/user-attachments/assets/4af9005e-a9c9-4f37-8f6a-84d86e6f6dde" controls muted playsinline width="85%"></video>
  <br />
  <em>Ask database questions in plain language, in any language.<br />ORBIT picks a reviewed query template, runs its parameterized query, and charts the result in chat.</em>
  <br />
  👉 <strong><a href="https://orbit.schmitech.ca/intent-sql-postgres?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=sql_demo">Try the SQL Database query demo live →</a></strong>
</div>

<br>

<div align="center">
  <video src="https://github.com/user-attachments/assets/9d09fb57-ed65-4426-857c-cd2f76a58c8c" controls muted playsinline width="80%"></video>
  <br />
  <em>Upload PDFs, spreadsheets, and images, then query them together with context preserved across the conversation.</em>
  <br />
  👉 <a href="https://orbit.schmitech.ca/chat-with-files/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=multimodal_demo"><strong>Try the multimodal agent demo live →</strong></a>
</div>

<br>

## Architecture

<div align="center">
<p>
  <img src="https://github.com/user-attachments/assets/8de74ddc-15b1-45f4-8837-45195ae67fe5" alt="ORBIT request and integration architecture" width="600" />
  <br />
  <em>Authenticate and route REST, OpenAI-compatible, MCP, A2A, or message-queue requests to models, private data, and tools.</em>
</p>
</div>

## One backend for private AI applications

| | What ORBIT gives you |
| :---: | :--- |
| **Connect anything** | Query files, SQL, NoSQL, vector stores, Elasticsearch, REST/GraphQL APIs, and MCP tools with procedural playbooks (`SKILL.md`) in natural language across multiple languages. |
| **Use any model** | Route one API contract across local models such as Ollama, llama.cpp, and vLLM or cloud providers such as OpenAI, Anthropic, Gemini, Bedrock, MS Foundry, and OpenRouter. |
| **Operate it safely** | Ship with API keys, RBAC, SSO, deny-by-default identity allowlists, Presidio PII moderation, quotas, fallbacks, metrics, audit logs, and an admin panel instead of assembling them yourself. |

ORBIT sits between your applications and the models, data, and tools they need. Define adapters in YAML, expose them through one OpenAI-compatible endpoint, and move from a local prototype to a governed deployment without replacing the architecture.

ORBIT is actively maintained. See the [release history](https://github.com/schmitech/orbit/releases), [changelog](CHANGELOG.md), and [commit history](https://github.com/schmitech/orbit/commits/main).

## Capabilities

| Capability | Included |
| :--- | :--- |
| **Model gateway** | 41 configured inference backends and providers, OpenAI-compatible APIs, Azure OpenAI presets (`config/azure.yaml`), per-key routing, model switching, retries, and fallbacks. |
| **Retrieval** | Vector RAG, file/multimodal RAG, SQL, MongoDB, Elasticsearch, REST, GraphQL, web search. |
| **Agents and protocols** | MCP tool calling, file- & DB-authored procedural tool skills (`SKILL.md`), progressive disclosure, priority token budgeting, bounded multi-step loops, natural-language skill routing, and A2A. |
| **Media** | Image (OpenAI, Gemini, xAI, Azure OpenAI, OpenRouter), video, speech, PDF, Word, Excel, PowerPoint, CSV, and markdown generation. |
| **Security** | API keys, RBAC, Entra ID and Auth0 SSO, deny-by-default identity allowlists, session withdrawal, external JWT role capping, rate limits, quotas, moderation, file encryption, and cloud secret managers. |
| **Operations** | Admin UI, Skills tab for MCP playbooks, retrieval misses triage view, health checks, metrics, audit logs, per-request token and estimated-cost tracking, spend analytics, circuit breakers, datasource pooling, and hot adapter reloads. |

[Browse all adapters](docs/adapters/adapters.md) · [See provider configuration](config/inference.yaml) · [Read the configuration reference](install/default-config/config.yaml) · [Full capability matrix & platform comparison](docs/ORBIT_CAPABILITY_MATRIX.md)

For organizations evaluating an AI gateway for adoption, the [capability matrix](docs/ORBIT_CAPABILITY_MATRIX.md) provides a sourced platform comparison, while the detailed [NIST SP 800-53 and AI security mapping](docs/security/nist-sp800-53-and-ai-security.md) covers ORBIT's documented relationships to NIST SP 800-53 Rev. 5, the NIST AI Risk Management Framework (AI RMF 1.0), and OWASP LLM risk mitigations. These documents help structure technical due diligence and deployment planning; they are not a certification, compliance determination, or substitute for a deployment-specific assessment.

⭐ **Finding ORBIT useful?** [Star the repository](https://github.com/schmitech/orbit) to help other developers discover it and support continued investment in new model, datasource, and agent integrations.

## 🚀 Quick Start

<div align="center">
  <a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=quick_start"><img src="https://img.shields.io/badge/TRY%20ORBIT%20LIVE-Explore%20the%20Sandbox%20%E2%86%92-7C3AED?style=for-the-badge" alt="Try ORBIT live — explore the sandbox" /></a>
  <br />
  <em>Explore the live sandbox instantly—no download, Docker, or setup required.</em>
</div>

### Install ORBIT

#### Option 1 (Preferred): Stable release tarball

**Prerequisites:** Linux or macOS, Python 3.12+, and an internet connection for downloading dependencies.

Download and install the latest stable release:

```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.17.2/orbit-2.17.2.tar.gz -o orbit-2.17.2.tar.gz
tar -xzf orbit-2.17.2.tar.gz
cd orbit-2.17.2
./install/setup.sh --profile default
./bin/orbit.sh start
```

ORBIT starts on [http://localhost:3000](http://localhost:3000). For Windows, follow the [Windows installation guide](install/windows.md).

ORBIT is highly configurable. The main server settings live in `./config/config.yaml`; inference providers, adapters, models, data sources, and other capabilities are configured in the other files under `./config/`.

See the [server management guide](docs/server.md#server-management) for commands to start, stop, restart, pause, and monitor ORBIT.

To use the optional ORBIT chatbot web interface, install and run `orbitchat` from your host machine:

```bash
npm install -g orbitchat
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' orbitchat
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

See the [OrbitChat project and documentation](clients/orbitchat/README.md) for configuration, custom adapters, authentication, and advanced usage.

#### Option 2: Docker

**Prerequisites:** Docker, 4 GB of free RAM, and 3 GB of disk space.

<details>
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

</br>

Port `5173` is the chat UI, `3000` is the OpenAI-compatible API if you want to call ORBIT directly:

```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: multimodal' \
  -H 'X-Session-ID: local-test' \
  -d '{"messages":[{"role":"user","content":"What can ORBIT connect to?"}]}'
```

Python and Node.js versions of this call using the official OpenAI SDK, including streaming, are in [`examples/openai-compatible-api/`](examples/openai-compatible-api/).

For peer-agent orchestration using Google's A2A protocol, see the blocking and streaming Python/Node.js clients in [`examples/a2a-protocol/`](examples/a2a-protocol/).

Using Claude with ORBIT? See [Using ORBIT from Claude](docs/claude-agent-integration.md) for both connection options — Claude calling ORBIT as an MCP tool, or a Claude agent addressing ORBIT as a peer via A2A.

Admin Panel at [http://localhost:3000/admin](http://localhost:3000/admin) (default credentials: username `admin`, password `ChangeMe!2026`, set via `ORBIT_DEFAULT_ADMIN_PASSWORD` — change this immediately after first login).

For custom Docker deployments, follow [Docker guide](docker/README.md).

Continue with the [tutorial's fastest path](docs/tutorial.md#fastest-path): [verify your installation](docs/tutorial/before-you-start.md), then [create your first chat](docs/tutorial/first-chat.md) with a persona, API key, and OrbitChat.

**Before you go further, read this:** adapters — not the server code — are what define what ORBIT can actually do (retrieval sources, models, voice, file/multimodal handling, and more). They're configured entirely in YAML under `config/adapters/` and registered in `config/adapters.yaml`. See the [Adapter overview](docs/adapters/adapters.md) to understand this system before customizing your deployment.

---

## What you can build

| Goal | ORBIT handles |
| :--- | :--- |
| **Chat with private documents** | Upload PDFs, office documents, spreadsheets, images, and audio; retrieve relevant context across a conversation with fallback file-retrieval routing. [Try the tutorial →](docs/tutorial/chat-with-files.md) |
| **Query databases in multiple languages** | Generate and execute safe queries across SQL, MongoDB, Elasticsearch, and composite datasources with retrieval telemetry. [Try the SQL demo →](docs/tutorial/sql-database-sqlite.md) |
| **Build tool-using agents** | Give models scoped access to MCP servers with custom skills, priority token budgets, and bounded tool loops. [Read the MCP guide →](docs/adapters/mcp-agent.md) |
| **Offer one governed AI endpoint** | Route local and cloud models with per-key access, quotas, identity allow/deny lists, moderation, fallbacks, metrics, and auditability. [Create your first key →](docs/tutorial/creating-api-keys.md) |

<details>
<summary><strong>Talk to a real-time voice assistant grounded in your data</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/9c6530be-1116-4a14-aa82-321448ea5a8d" controls muted playsinline width="60%"></video>
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
  👉 <a href="https://orbit.schmitech.ca/mcp-business-sample?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=mcp_demo"><strong>Try the MCP tool calling demo live →</strong></a>
</p>
</details>

<details>
<summary><strong>Real-Time Business & Revenue Intelligence (MCP Tool Calling)</strong></summary>
<p align="center">
  <video src="https://github.com/user-attachments/assets/b177b234-e64f-491a-8c3e-8294774c548c" controls muted playsinline width="80%"></video>
  <br />
  <em>Multi-step agent reasoning across 9 synthetic MCP tools: CRM health, telemetry seat utilization, P1 support escalations, and churn risk simulation.</em>
  <br />
  👉 <a href="https://orbit.schmitech.ca/mcp-business-sample?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=business_intelligence_demo"><strong>Try the Business & Revenue Intelligence MCP demo live →</strong></a>
</p>
</details>

## Clients and documentation

| Start here | Resource |
| :--- | :--- |
| **Learn ORBIT** | [Tutorial](docs/tutorial.md) · [Your first chat](docs/tutorial/first-chat.md) · [HTTP APIs](docs/tutorial/http-apis.md) |
| **Configure adapters** | [Adapter overview](docs/adapters/adapters.md) · [Configuration guide](docs/adapters/adapter-configuration.md) |
| **Connect private data** | [Files](docs/adapters/file-adapter-guide.md) · [Vector stores](docs/vector-stores/vector_store_integration_guide.md) · [SQL](docs/sql-retriever-architecture.md) |
| **Build agents** | [MCP tools](docs/tutorial/mcp-tool-calling.md) · [Auto skill routing](docs/tutorial/auto-skill-routing.md) · [A2A](docs/a2a-protocol.md) |
| **Add voice** | [Real-time voice (speech-to-speech)](docs/adapters/grounded-realtime-voice.md) · [Audio services & STT/TTS adapters](docs/audio/audio-services-adapter-guide.md) |
| **Run in production** | [Authentication](docs/authentication.md) · [Usage and cost tracking](docs/token-usage-and-cost-tracking.md) · [Rate limiting](docs/rate-limiting-architecture.md) · [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md) |
| **Use a client** | [ORBIT Chat](clients/orbitchat/) · [Node.js SDK](clients/node-api/) · [API key and Python examples](docs/api-keys.md) |
| **Evaluate ORBIT** | [Capability matrix & platform comparison](docs/ORBIT_CAPABILITY_MATRIX.md) — a sourced feature-by-feature comparison against LiteLLM, Open WebUI, and commercial AI gateways |

See the [full documentation index](docs/README.md) for architecture deep-dives, vector store setup, security hardening, and every other guide under `docs/`.

## Contributing

Contributions are welcome: new retrievers and provider integrations, deployment guides, tests, fixes, and documentation. Read [CONTRIBUTING.md](CONTRIBUTING.md), pick an [open issue](https://github.com/schmitech/orbit/issues), or start a discussion.

Maintained by [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/).

## License

ORBIT is licensed under the [Apache License 2.0](LICENSE).
