<div align="center">
  <a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=logo">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT" width="160" />
  </a>

  # ORBIT

  **The self-hosted AI backend for private data and tool-using agents.**

  Connect files, databases, APIs, and MCP tools to local or hosted models behind one OpenAI-compatible API—with authentication, observability, and an admin UI built in.

  <p>
    <strong><a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=hero">Try ORBIT live →</a></strong>
    &nbsp;·&nbsp;
    <a href="#quick-start">Quick start</a>
    &nbsp;·&nbsp;
    <a href="docs/">Documentation</a>
  </p>
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars" /></a>
  <a href="https://github.com/schmitech/orbit/releases/latest"><img src="https://img.shields.io/github/v/release/schmitech/orbit?label=release" alt="Latest release" /></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache 2.0 license" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+" /></a>
</p>

<div align="center">
  <video src="https://github.com/user-attachments/assets/9d09fb57-ed65-4426-857c-cd2f76a58c8c" controls muted playsinline width="85%"></video>
  <br />
  <em>Upload PDFs, spreadsheets, and images, then query them together with context preserved across the conversation.</em>
  <br />
  <strong><a href="https://orbit.schmitech.ca/chat-with-files/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=multimodal_demo">Try the file and multimodal demo →</a></strong>
</div>

## What you can build

| Goal | ORBIT handles |
| :--- | :--- |
| **Chat with private documents** | Upload PDFs, office documents, spreadsheets, images, and audio, then retrieve relevant context across the conversation. [Try the tutorial →](docs/tutorial/chat-with-files.md) |
| **Query databases in natural language** | Run reviewed, parameterized queries across SQL, MongoDB, Elasticsearch, and composite data sources. [Try the SQL demo →](https://orbit.schmitech.ca/intent-sql-postgres?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=sql_demo) |
| **Build tool-using agents** | Give models scoped access to MCP servers with procedural skills, priority token budgets, and bounded tool loops. [Try the MCP agent live →](https://orbit.schmitech.ca/mcp-business-sample?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=mcp_demo) · [Read the MCP guide →](docs/adapters/mcp-agent.md) |
| **Offer one governed AI endpoint** | Route local and cloud models with per-key access, quotas, identity controls, moderation, fallbacks, metrics, and audit logs. [Create your first key →](docs/tutorial/creating-api-keys.md) |

## Why ORBIT

| | What you get |
| :---: | :--- |
| **Connect anything** | Bring files, SQL, NoSQL, vector stores, Elasticsearch, REST/GraphQL APIs, and MCP tools together through YAML-configured adapters. |
| **Use any model** | Keep one API contract while routing to Ollama, llama.cpp, vLLM, OpenAI, Anthropic, Gemini, Bedrock, Microsoft Foundry, OpenRouter, and more. |
| **Operate it safely** | Start with API keys, RBAC, SSO, identity allowlists, PII moderation, quotas, fallbacks, metrics, audit logs, and an admin panel already integrated. |

ORBIT sits between your applications and the models, data, and tools they need. Move from a local prototype to a governed deployment without replacing the architecture.

⭐ **Finding ORBIT useful?** [Star the repository](https://github.com/schmitech/orbit) to help other developers discover it.

## Quick start

### Try it without installing

Open the [live ORBIT sandbox](https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=quick_start)—no download, Docker, or account required.

### Run it locally

**Prerequisites:** Python 3.12+ and an internet connection for dependencies. The default configuration uses [Ollama](https://ollama.com/) for inference, so install Ollama as well if you use the default provider. Windows users can follow the [Windows installation guide](install/windows.md).

1. Download the [ORBIT v2.17.4 tarball](https://github.com/schmitech/orbit/releases/download/v2.17.4/orbit-2.17.4.tar.gz).
2. Extract it, enter the release directory, and start ORBIT:

```bash
mkdir orbit-release
tar -xzf orbit-*.tar.gz -C orbit-release --strip-components=1
cd orbit-release
./install/setup.sh --profile default

ollama pull gemma4:e2b
# Required for file/multimodal adapters:
ollama pull nomic-embed-text

./bin/orbit.sh start
```

The default setup enables Ollama in `config/inference.yaml`, selects it as the
global provider in `config/config.yaml`, and uses the `gemma4-e2b-cpu` Ollama
preset for the initial conversational adapter. Presets are defined in
`config/ollama.yaml`; this preset resolves to the `gemma4:e2b` model tag.

`setup.sh` does not install Ollama; install and start it separately before
running the model pull command (run `ollama serve` in another terminal if
Ollama is not already running).

If you plan to use the retrieval adapters (file, SQL, etc.), also enable Ollama
embeddings in `config/embeddings.yaml` and keep the model aligned with the
download above:

```yaml
embedding:
  provider: "ollama"
  enabled: true

embeddings:
  ollama:
    model: "nomic-embed-text"
```

All ORBIT behavior is managed through YAML: use `config/config.yaml` for global
server settings, `config/inference.yaml` for provider enablement and credentials,
`config/ollama.yaml` for Ollama presets, and the files under `config/adapters/`
for adapter behavior.

To use another provider, enable it in `config/inference.yaml`, set its
credential in `.env`, and select it globally or on the adapter that should use it.

If you prefer not to install a local model, the prebuilt Docker flavors provide
ready-to-run Ollama, OpenAI, and Gemini setups. See the [Docker flavor quick
start](docker/README.md#flavor-images-recommended-pull-and-run) for the exact
commands and required credentials.

ORBIT starts at [http://localhost:3000](http://localhost:3000). Follow the tutorial to [verify the installation](docs/tutorial/before-you-start.md) and [create your first chat](docs/tutorial/first-chat.md).

For a quick smoke test, the release seed includes `default-key` mapped to the
`simple-chat` adapter:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: readme-smoke-test' \
  -d '{
    "messages": [
      {"role": "user", "content": "Say hello in one sentence"}
    ],
    "stream": false
  }'
```

For API-key creation, file uploads, and browser-based testing, continue with
[Before you start](docs/tutorial/before-you-start.md).

Prefer containers or a bundled chat UI? Use the [Docker quick start](docker/README.md#flavor-images-recommended-pull-and-run), or install and configure [OrbitChat](clients/orbitchat/README.md).

## How it works

<div align="center">
  <img src="https://github.com/user-attachments/assets/8de74ddc-15b1-45f4-8837-45195ae67fe5" alt="ORBIT authenticates and routes application requests to models, private data, and tools" width="680" />
  <br />
  <em>Authenticate and route REST, OpenAI-compatible, MCP, A2A, or message-queue requests to models, private data, and tools.</em>
</div>

 <br />

Adapters—not server code—define what ORBIT can do. Configure models, retrieval sources, voice, file handling, and multimodal behavior in YAML under `config/adapters/`, then expose them through one endpoint. Start with the [adapter overview](docs/adapters/adapters.md).

## Batteries included

| Area | Highlights |
| :--- | :--- |
| **Model gateway** | OpenAI-compatible APIs, provider switching, per-key routing, retries, and fallbacks across local and hosted models. |
| **Retrieval** | Vector RAG, file and multimodal RAG, SQL, MongoDB, Elasticsearch, REST, GraphQL, and web search. |
| **Agents and protocols** | MCP tool calling, procedural `SKILL.md` playbooks, bounded multi-step loops, automatic skill routing, and A2A. |
| **Media** | Image, video, speech, PDF, Word, Excel, PowerPoint, CSV, and Markdown generation. |
| **Security** | API keys, RBAC, Entra ID and Auth0 SSO, identity allowlists, quotas, moderation, file encryption, and cloud secret managers. |
| **Operations** | Admin UI, health checks, metrics, audit logs, token and cost tracking, spend analytics, circuit breakers, and hot adapter reloads. |

[Browse all adapters](docs/adapters/adapters.md) · [Configure providers](config/inference.yaml) · [See the full capability matrix](docs/ORBIT_CAPABILITY_MATRIX.md)

For production evaluation, see the sourced [platform comparison](docs/ORBIT_CAPABILITY_MATRIX.md) and the [NIST SP 800-53, AI RMF, and OWASP security mapping](docs/security/nist-sp800-53-and-ai-security.md). These resources support technical due diligence; they are not a certification or substitute for a deployment-specific assessment.

## Explore more

| I want to… | Start here |
| :--- | :--- |
| **Learn ORBIT** | [Tutorial](docs/tutorial.md) · [First chat](docs/tutorial/first-chat.md) · [HTTP APIs](docs/tutorial/http-apis.md) |
| **Connect private data** | [Files](docs/adapters/file-adapter-guide.md) · [Vector stores](docs/vector-stores/vector_store_integration_guide.md) · [SQL](docs/sql-retriever-architecture.md) |
| **Build agents** | [MCP tools](docs/tutorial/mcp-tool-calling.md) · [Automatic skill routing](docs/tutorial/auto-skill-routing.md) · [A2A](docs/a2a-protocol.md) |
| **Run in production** | [Authentication](docs/authentication.md) · [Cost tracking](docs/token-usage-and-cost-tracking.md) · [Rate limiting](docs/rate-limiting-architecture.md) · [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md) |
| **Use a client** | [OrbitChat](clients/orbitchat/) · [Node.js SDK](clients/node-api/) · [Python API example](examples/openai-compatible-api/chat_completions.py) |

See the [documentation index](docs/README.md) for every guide and architecture deep dive.

## Contributing

Contributions are welcome: new retrievers and provider integrations, deployment guides, tests, fixes, and documentation. Read [CONTRIBUTING.md](CONTRIBUTING.md), pick an [open issue](https://github.com/schmitech/orbit/issues), or start a discussion.

Maintained by [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/).

## License

ORBIT is licensed under the [Apache License 2.0](LICENSE).
