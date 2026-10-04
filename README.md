<div align="center">
  <a href="https://orbit.schmitech.ca/?utm_source=github&utm_medium=readme&utm_campaign=try_orbit&utm_content=logo">
    <img src="https://github.com/user-attachments/assets/565d48af-1dc5-49cb-a1d4-77f4e696662c" alt="ORBIT" width="160" />
  </a>

  # ORBIT

  **The self-hosted AI backend for private data and tool-using agents.**

  Connect your data and tools to local or hosted models through one OpenAI-compatible API.
  Configure with YAML. Deploy on your own infrastructure.

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

  <p>⭐ Building with private data or AI agents? <strong>Star ORBIT</strong> to bookmark it and help others discover it.</p>
</div>

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=social" alt="GitHub stars" /></a>
  <a href="https://github.com/schmitech/orbit/releases/latest"><img src="https://img.shields.io/github/v/release/schmitech/orbit?label=release" alt="Latest release" /></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache 2.0 license" /></a>
</p>

## Why ORBIT

Build a chat app over private documents, an agent that calls your tools, or a triage workflow—with the same backend.

| | What you get |
| :--- | :--- |
| **Your data, connected** | Files, SQL, NoSQL, vector stores, APIs, and MCP tools through YAML-configured adapters. |
| **Your choice of models** | Switch between local and hosted providers behind one OpenAI-compatible API. |
| **Your infrastructure** | Self-host on-premises or in a private cloud; use local models for air-gapped deployments. |
| **Operations built in** | Authentication, quotas, audit logs, provider fallbacks, monitoring, and an admin UI. |

Explore the [capability matrix](docs/ORBIT_CAPABILITY_MATRIX.md) for a detailed comparison.

## Quick start

### Run it locally

**Prerequisites:** Python 3.11+ (3.12 preferred), an internet connection for downloads, and [Ollama](https://ollama.com/) installed and running. If needed, run `ollama serve` in a separate terminal. On Windows, follow the [installation guide](install/windows.md).

```bash
curl -LO https://github.com/schmitech/orbit/releases/download/v2.18.0/orbit-2.18.0.tar.gz
tar -xzf orbit-2.18.0.tar.gz && cd orbit-2.18.0
./install/setup.sh --profile default

ollama pull gemma4:e2b
# Required for file/multimodal adapters:
ollama pull nomic-embed-text

./bin/orbit.sh start
./bin/orbit.sh status
```

Open the [admin dashboard](http://localhost:3000/admin) and sign in with `admin` / `ChangeMe!2026`.

### Send your first message

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

Continue with [your first chat](docs/tutorial/first-chat.md) to create an API key, or use the [Docker quick start](docker/README.md#flavor-images-recommended-pull-and-run) for containers.

<details>
<summary><strong>Configure models and data sources</strong></summary>

The default setup uses Ollama with the `gemma4-e2b-cpu` preset, which resolves to `gemma4:e2b`.

- **Server settings:** [`config/config.yaml`](config/config.yaml).
- **Providers:** Enable a provider in [`config/inference.yaml`](config/inference.yaml), set its credential in `.env`, and select it globally or per adapter.
- **Ollama presets:** [`config/ollama.yaml`](config/ollama.yaml).
- **Data and tools:** Configure adapters in [`config/adapters.yaml`](config/adapters.yaml) and [`config/adapters/`](config/adapters/). Start with the [adapter guide](docs/adapters/adapters.md) or [intent templates](examples/intent-templates/).

See [Before you start](docs/tutorial/before-you-start.md) for installation checks, file retrieval setup, and API-key management.

</details>

<details>
<summary><strong>Chat from a terminal or browser</strong></summary>

Use [orbit-cli](clients/orbit-cli/) from a terminal (Node.js 20+):

```bash
npm install -g @schmitech/orbit-cli@latest
orbit-chat --url http://localhost:3000 --key default-key
```

Or launch [OrbitChat](clients/orbitchat/) in your browser:

```bash
npm install -g orbitchat@latest

cat > orbitchat.yaml <<'EOF'
agentMode:
  mode: "single"
  defaultAdapterId: "simple-chat"
adapters:
  - id: "simple-chat"
EOF

ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' orbitchat --config orbitchat.yaml --open
```

OrbitChat opens at [http://localhost:5173](http://localhost:5173). See the [example configuration](clients/orbitchat/orbitchat.yaml.example) for more options.

</details>

## Explore more

| I want to… | Start here |
| :--- | :--- |
| **Learn ORBIT** | [Tutorial](docs/tutorial.md) · [First chat](docs/tutorial/first-chat.md) · [HTTP APIs](docs/tutorial/http-apis.md) |
| **Connect private data** | [Files](docs/adapters/file-adapter-guide.md) · [Vector stores](docs/vector-stores/vector_store_integration_guide.md) · [SQL](docs/sql-retriever-architecture.md) · [Intent templates](examples/intent-templates/) · [Adapter system overview](docs/adapters/adapters.md) |
| **Build agents** | [MCP tools](docs/tutorial/mcp-tool-calling.md) · [Automatic skill routing](docs/tutorial/auto-skill-routing.md) · [A2A](docs/a2a-protocol.md) · [Adapter creation](docs/adapters/adapter-creation.md) |
| **Make real-time decisions** | [Decision models](docs/adapters/decision-models.md) · [Triage Rush demo](examples/triage-rush-game/) · [Sentiment Pulse](examples/sentiment-pulse/) |
| **Run in production** | [Authentication](docs/authentication.md) · [Cost tracking](docs/token-usage-and-cost-tracking.md) · [Rate limiting](docs/rate-limiting-architecture.md) · [Fault tolerance](docs/fault-tolerance/fault-tolerance-architecture.md) |
| **Use a client** | [OrbitChat](clients/orbitchat/) · [Realtime Voice](clients/realtime-voice/) · [Node.js SDK](clients/node-api/) · [Python API example](examples/openai-compatible-api/chat_completions.py) |

See the [documentation index](docs/README.md) for every guide and architecture deep dive.

## Contributing

Contributions are welcome: new retrievers and provider integrations, deployment guides, tests, fixes, and documentation. Read [CONTRIBUTING.md](CONTRIBUTING.md), pick an [open issue](https://github.com/schmitech/orbit/issues), or start a discussion.

Maintained by [Remsy Schmilinsky](https://www.linkedin.com/in/remsy/).

## License

ORBIT (Open Retrieval-Based Inference Toolkit) is licensed under the [Apache License 2.0](LICENSE).
