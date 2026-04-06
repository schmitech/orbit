<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo-github.png" alt="ORBIT Logo" width="250"/>
  </a>

  <h3>One API for 20+ LLM providers, your databases, and your files.</h3>
  <p>Self-hosted. Open-source. Production-ready.</p>
</div>

<br/>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/github/v/release/schmitech/orbit" alt="Latest release"></a>
  <a href="https://github.com/schmitech/orbit/commits/main"><img src="https://img.shields.io/github/last-commit/schmitech/orbit" alt="Last commit"></a>
  <a href="https://github.com/schmitech/orbit" target="_blank">
    <img src="https://img.shields.io/github/stars/schmitech/orbit?style=social&label=Star" alt="GitHub stars">
  </a>
</p>

<p align="center">
  <a href="https://orbitsandbox.dev/"><strong>Live Sandbox</strong></a>
  &nbsp;|&nbsp;
  <a href="https://orbit.schmitech.ai/redoc"><strong>API Reference</strong></a>
  &nbsp;|&nbsp;
  <a href="docker/README.md"><strong>Docker Guide</strong></a>
  &nbsp;|&nbsp;
  <a href="docs/cookbook/"><strong>Cookbook</strong></a>
</p>

---

### Get running in 60 seconds

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

Then test it:

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

That's it. ORBIT is listening on port 3000 with an admin panel at [localhost:3000/admin](http://localhost:3000/admin) (default login: `admin` / `admin123`).

For GPU acceleration: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`

---

### What can you build with ORBIT?

- **Ask your database questions in any language** — Connect Postgres, MySQL, MongoDB, DuckDB, or Elasticsearch and query them with natural language. Built-in language detection responds in the user's language automatically.
- **Switch LLM providers without changing code** — Swap between OpenAI, Anthropic, Gemini, Groq, Ollama, vLLM, and more with a config change.
- **Build voice agents** — Full-duplex speech-to-speech with interruption handling via PersonaPlex.
- **Power agentic workflows** — MCP-compatible, so AI agents can use ORBIT as a tool.
- **Upload files and get answers** — RAG over PDFs, images, and documents out of the box.
- **Add guardrails and content moderation** — Built-in safety layer with OpenAI, Anthropic, or local (Llama Guard) moderators to filter harmful content before it reaches users.
- **Go from text to speech and back** — Plug in STT (Whisper, Google, Gemini) and TTS (OpenAI, ElevenLabs, Coqui) providers for voice-enabled applications.
- **Keep everything private** — Self-host on your own infrastructure with RBAC, rate limiting, and audit logging.

---

### Supported integrations

**LLM Providers:** OpenAI, Anthropic, Google Gemini, Cohere, Groq, DeepSeek, Mistral, AWS Bedrock, Azure, Together, Ollama, vLLM, llama.cpp

**Data Sources:** PostgreSQL, MySQL, MongoDB, Elasticsearch, DuckDB, SQLite, HTTP/REST APIs, GraphQL

**Vector Stores:** Chroma, Qdrant, Pinecone, Milvus, Weaviate

---

### Why ORBIT?

| Without ORBIT | With ORBIT |
| :--- | :--- |
| One SDK per provider, rewrites when you switch | One OpenAI-compatible API across all providers |
| Separate pipelines for retrieval and inference | Unified model + retrieval + tooling gateway |
| Fragile glue scripts between data sources and LLMs | Production-ready connectors with policy controls |
| No visibility into what models are doing | Built-in RBAC, rate limiting, and audit logging |

---

### Try it live

The <a href="https://orbitsandbox.dev/" target="_blank" rel="noopener noreferrer">public sandbox</a> hosts one chat workspace per adapter. Pick a demo to see ORBIT in action.

| Demo | Data Source | Try it |
| :--- | :--- | :--- |
| Simple Chat | LLM | <a href="https://orbitsandbox.dev/simple-chat" target="_blank">simple-chat</a> |
| Multimodal Chat | LLM + Files | <a href="https://orbitsandbox.dev/chat-with-files" target="_blank">chat-with-files</a> |
| Customer Orders | PostgreSQL | <a href="https://orbitsandbox.dev/intent-sql-postgres" target="_blank">intent-sql-postgres</a> |
| HR Database | SQLite | <a href="https://orbitsandbox.dev/intent-sql-sqlite-hr" target="_blank">intent-sql-sqlite-hr</a> |
| DuckDB Analytics | DuckDB | <a href="https://orbitsandbox.dev/intent-duckdb-analytics" target="_blank">intent-duckdb-analytics</a> |
| EV Population Stats | DuckDB | <a href="https://orbitsandbox.dev/intent-duckdb-ev-population" target="_blank">intent-duckdb-ev-population</a> |
| JSONPlaceholder REST API | HTTP (JSON) | <a href="https://orbitsandbox.dev/intent-http-jsonplaceholder" target="_blank">intent-http-jsonplaceholder</a> |
| Paris Open Data API | HTTP (JSON) | <a href="https://orbitsandbox.dev/intent-http-paris-opendata" target="_blank">intent-http-paris-opendata</a> |
| MFlix Sample Collection | MongoDB | <a href="https://orbitsandbox.dev/intent-mongodb-mflix" target="_blank">intent-mongodb-mflix</a> |
| SpaceX GraphQL | GraphQL | <a href="https://orbitsandbox.dev/intent-graphql-spacex" target="_blank">intent-graphql-spacex</a> |

Adapter wiring and sample domains live in [`config/adapters/`](config/adapters/) and [`examples/intent-templates/`](examples/intent-templates/).

---

### Built with ORBIT

- **[PoliceStats.ca](https://policestats.ca)** — Public chat over Canadian municipal police open data. Users ask about auto theft, break-ins, crime by neighbourhood, and cross-city comparisons.

Using ORBIT in production? [Let us know](https://schmitech.ai/en/contact) and we'll add your project here.

---

### Clients

| Client | Description |
| :--- | :--- |
| **[Web Chat](clients/orbitchat/)** | React UI |
| **CLI** | `pip install schmitech-orbit-client` |
| **[Mobile](clients/orbit-mobile/)** | iOS & Android (Expo) |
| **[Node SDK](clients/node-api/)** | Or use any OpenAI-compatible SDK |

---

### Deployment options

<details>
<summary><strong>Docker Compose (fastest path)</strong></summary>

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```

Starts ORBIT + Ollama with SmolLM2, auto-pulls models, and exposes the API on port 3000. The web admin UI is at `/admin` on the same host. Connect [orbitchat](https://www.npmjs.com/package/orbitchat) from your host:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat
```

See the full [Docker Guide](docker/README.md) for GPU mode, volumes, and configuration.

</details>

<details>
<summary><strong>Pre-built image (server only)</strong></summary>

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 3000:3000 schmitech/orbit:basic
```

If Ollama runs on your host, add `-e OLLAMA_HOST=host.docker.internal:11434` so the container can reach it. Includes simple-chat only.

</details>

<details>
<summary><strong>From release tarball (production)</strong></summary>

```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.6.5/orbit-2.6.5.tar.gz -o orbit-2.6.5.tar.gz
tar -xzf orbit-2.6.5.tar.gz && cd orbit-2.6.5

cp env.example .env && ./install/setup.sh
source venv/bin/activate
./bin/orbit.sh start && cat ./logs/orbit.log
```

</details>

---

### Resources

- [Step-by-Step Tutorial](docs/tutorial.md) — Chat with your own data in minutes
- [Cookbook](docs/cookbook/) — Recipes for real-world use cases
- [Documentation](docs/) — Full architecture and setup guides
- [GitHub Issues](https://github.com/schmitech/orbit/issues) — Bug reports and feature requests

---

### Contributing

Contributions are welcome! Check the [issues](https://github.com/schmitech/orbit/issues) for good first tasks, or open a new one to discuss your idea.

If you find ORBIT useful, a **[star](https://github.com/schmitech/orbit)** helps others discover the project.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
