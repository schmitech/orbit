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

## What you can build

ORBIT agents can be exposed or integrated through several interfaces: ORBIT can
act as an [MCP server](docs/mcp_protocol.md), connect to external MCP servers as
a [tool-using client](docs/tutorial/mcp-tool-calling.md), provide an [A2A endpoint](docs/a2a-protocol.md),
serve requests through its [REST and OpenAI-compatible APIs](docs/tutorial/http-apis.md),
support [real-time speech-to-speech over WebSocket](clients/realtime-voice/README.md),
be integrated asynchronously through the [message-queue interface](docs/tutorial/message-queue-async.md),
or be called from the [Node.js client](clients/node-api/). The demos below use
the [OrbitChat client](https://www.npmjs.com/package/orbitchat) to showcase these
capabilities through a conversational interface.

| Goal | ORBIT handles |
| :--- | :--- |
| **Chat with private documents** | Upload PDFs, office documents, spreadsheets, images, and audio, then retrieve relevant context across the conversation. [Try the file and multimodal demo →](https://orbit.schmitech.ca/chat-with-files) |
| **Query databases in natural language** | Run parameterized queries across SQL, MongoDB, Elasticsearch, and composite data sources. [Try the SQL demo →](https://orbit.schmitech.ca/intent-sql-postgres) |
| **Analyze business data** | Explore sales and operational data with natural-language analytics over DuckDB. [Try the DuckDB analytics demo →](https://orbit.schmitech.ca/ecomm-analytics) |
| **Query HR data** | Ask natural-language questions over a SQLite HR database using reviewed intent templates. [Try the HR SQLite demo →](https://orbit.schmitech.ca/hr-db-chatbot) |
| **Query a MongoDB database** | Explore the sample MFlix movie database through natural-language intent queries. [Try the MongoDB MFlix demo →](https://orbit.schmitech.ca/intent-mongodb-mflix) |
| **Join data and tools across systems** | Combine billing data from SQL, support SLA data from HTTP, and live CRM context from MCP tools in one place. [Try the Customer 360 demo →](https://orbit.schmitech.ca/composite-customer-360) |
| **Talk to a grounded virtual assistant** | Use low-latency, natural speech-to-speech voice chat with responses grounded in knowledge sources. [Try the real-time voice demo →](https://orbit.schmitech.ca/real-time-voice-chat) |
| **Query public data** | Ask natural-language questions against the City of Paris open-data events and activities API. [Try the Paris open-data demo →](https://orbit.schmitech.ca/intent-http-paris-opendata) |
| **Build tool-using agents** | Give models scoped access to MCP servers with procedural skills, and bounded tool loops. [Try the MCP agent live →](https://orbit.schmitech.ca/mcp-business-sample) |

⭐ **Finding ORBIT useful?** [Star the repository](https://github.com/schmitech/orbit) to help other developers discover it.

## Why ORBIT

| | What you get |
| :---: | :--- |
| **Connect anything** | Bring files, SQL, NoSQL, vector stores, Elasticsearch, REST/GraphQL APIs, and MCP tools together through YAML-configured adapters. |
| **Use any model** | Keep one API contract while routing to Ollama, llama.cpp, vLLM, OpenAI, Anthropic, Gemini, Bedrock, Microsoft Foundry, OpenRouter, and more. |
| **Keep data under your control** | Deploy on-premises, in a private cloud, or in an air-gapped environment while choosing local, self-hosted, or hosted models. |
| **Govern AI operations** | RBAC, OIDC/SSO, identity allowlisting, per-key quotas, audit logs, moderation, and file encryption. |
| **Stay resilient in production** | Use provider fallbacks, retries, circuit breakers, health checks, metrics, hot adapter reloads, and an integrated admin panel for day-to-day operations. |

ORBIT sits between your applications and the models, data, and tools they need. Move from a local prototype to a governed deployment without replacing the architecture. For technical and security assessments, see [platform comparison and capability matrix](docs/ORBIT_CAPABILITY_MATRIX.md), and [NIST SP 800-53 and OWASP Top 10 mapping](docs/security/nist-sp800-53-and-ai-security.md).

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
