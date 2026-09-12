<div align="center">
  <a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=logo">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT" width="160" />
  </a>

  # ORBIT

  **The self-hosted AI backend for private data and tool-using agents.**

  Connect files, databases, APIs, and MCP tools to local or hosted models behind one OpenAI-compatible API—with authentication, observability, and an admin UI built in.

  <p>
    <a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=hero">
      <img src="https://img.shields.io/badge/Try_ORBIT_Sandbox-Open_live_demo_%E2%86%92-2563eb?style=for-the-badge" alt="Try ORBIT Sandbox →" />
    </a>
    <br />
    <sub>Explore interactive demos in your browser. No installation or account required.</sub>
  </p>

  <p>
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
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit" alt="Last commit" /></a>
</p>

<div id="multimodal-demo" align="center">
  <video src="https://github.com/user-attachments/assets/9d09fb57-ed65-4426-857c-cd2f76a58c8c" controls muted playsinline width="85%"></video>
  <br />
  <em>Upload PDFs, documents, and images, then ask questions across all of them in one conversation. Context is preserved across turns, and local models keep every file and query on your infrastructure.</em>
</div>

<br />

## Why ORBIT

| | What you get |
| :---: | :--- |
| **Connect anything** | Bring files, SQL, NoSQL, vector stores, Elasticsearch, REST/GraphQL APIs, and MCP tools together through YAML-configured adapters. |
| **Use any model** | Keep one API contract while routing to Ollama, llama.cpp, vLLM, OpenAI, Anthropic, Gemini, Bedrock, Microsoft Foundry, OpenRouter, and more. |
| **Keep data under your control** | Deploy on-premises, in a private cloud, or in an air-gapped environment while choosing local, self-hosted, or hosted models. |
| **Govern AI operations** | RBAC, OIDC/SSO, identity allowlisting, per-key quotas, audit logs, moderation, and file encryption. |
| **Stay resilient in production** | Use provider fallbacks, retries, circuit breakers, health checks, metrics, hot adapter reloads, and an integrated admin panel for day-to-day operations. |

ORBIT sits between your applications and the models, data, and tools they need. Move from a local prototype to a governed deployment without replacing the architecture. For technical and security assessments, see [platform comparison and capability matrix](docs/ORBIT_CAPABILITY_MATRIX.md), and [NIST SP 800-53 and OWASP Top 10 mapping](docs/security/nist-sp800-53-and-ai-security.md).

<p align="left">⭐ If ORBIT looks useful, <a href="https://github.com/schmitech/orbit">star the repo</a> — it helps others find it and tells us what to keep building.</p>

## Quick start

### Try it without installing

**[Try ORBIT Sandbox →](https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=quick_start)** Choose a demo and ask your first question—no download, Docker, or account required.

### Run it locally

**Prerequisites:** Python 3.12+ and an internet connection for dependencies. The default configuration uses [Ollama](https://ollama.com/) for inference, so install Ollama as well if you use the default provider. Windows users can follow the [Windows installation guide](install/windows.md).

1. Download the [ORBIT v2.17.8 tarball](https://github.com/schmitech/orbit/releases/download/v2.17.8/orbit-2.17.8.tar.gz).
2. Extract it, enter the release directory, and start ORBIT:

```bash
curl -LO https://github.com/schmitech/orbit/releases/download/v2.17.8/orbit-2.17.8.tar.gz
tar -xzf orbit-2.17.8.tar.gz && cd orbit-2.17.8
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

All ORBIT behavior is managed through YAML: use `config/config.yaml` for global
server settings, `config/inference.yaml` for provider enablement and credentials,
`config/ollama.yaml` for Ollama presets, and the files under `config/adapters/`
for adapter behavior.

To use another provider, enable it in `config/inference.yaml`, set its
credential in `.env`, and select it globally or on the adapter that should use it.

ORBIT starts at [http://localhost:3000](http://localhost:3000), and the dashboard at [http://localhost:3000/admin](http://localhost:3000/admin). Follow the tutorial to [verify the installation](docs/tutorial/before-you-start.md) and [create your first chat](docs/tutorial/first-chat.md).

<br />
<div id="admin-panel-demo" align="center">
  <video src="https://github.com/user-attachments/assets/e1f91fbb-f398-40f0-beb0-45129d4b0e34" controls muted playsinline width="85%"></video>
  <br />
  <em>The built-in admin panel is ORBIT's control plane—manage adapters, API keys, prompts, and system operations without touching server code.</em>
</div>

<br />

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

Test it from a terminal with [orbit-cli](clients/orbit-cli/):

```bash
npm install -g @schmitech/orbit-cli@latest
orbit-chat --url http://localhost:3000 --key default-key
```

<br />

<div id="multimodal-demo" align="left">
  <video src="https://github.com/user-attachments/assets/ba9a96dd-ef76-40d6-b129-3406d427cb81" controls muted playsinline width="85%"></video>
  <br />
  <em>The ORBIT chat CLI tool.</em>
</div>

<br />

Or test it from the browser with [orbitchat](clients/orbitchat/):

```bash
npm install -g orbitchat@latest
cat > orbitchat.yaml <<'EOF'
agentMode:
  mode: "single"
  defaultAdapterId: "simple-chat"
adapters:
  - id: "simple-chat"
EOF
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' orbitchat --config orbitchat.yaml
```

See [orbitchat.yaml.example](clients/orbitchat/orbitchat.yaml.example) for the full set of configuration options.

For API-key creation, file uploads, and browser-based testing, continue with
[Before you start](docs/tutorial/before-you-start.md).

Prefer containers or a bundled chat UI? Use the [Docker quick start](docker/README.md#flavor-images-recommended-pull-and-run), or install and configure [OrbitChat](clients/orbitchat/README.md).


## Explore more

| I want to… | Start here |
| :--- | :--- |
| **Try ORBIT in my browser** | [Try ORBIT Sandbox →](https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=explore_more) — explore the live demos before setting up your own instance. |
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
