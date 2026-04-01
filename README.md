<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo-transparent.png" alt="ORBIT Logo" width="500"/>
  </a>
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

# ORBIT: Open Retrieval-Based Inference Toolkit

**Connect 20+ LLM providers with your data through one API.**

ORBIT is a self-hosted gateway that unifies LLMs, files, databases, and APIs behind one MCP endpoint, letting teams standardize on one integration surface while keeping security, compliance, and operational controls under their watch.

<p align="center">
  <a href="https://orbitsandbox.dev/"><strong>Try the Sandbox</strong></a>
  &nbsp;|&nbsp;
  <a href="https://orbit.schmitech.ai/redoc"><strong>API Reference</strong></a>
  &nbsp;|&nbsp;
  <a href="docker/README.md"><strong>Docker Guide</strong></a>
  &nbsp;|&nbsp;
  <a href="docs/cookbook/"><strong>Cookbook</strong></a>
</p>

### Sandbox demos ([orbitsandbox.dev](https://orbitsandbox.dev/))

The public sandbox hosts one chat workspace per adapter. Each URL path is the adapter **`name`** from the bundled configs (`config/adapters/intent.yaml`, `hr.yaml`, `passthrough.yaml`, `multimodal.yaml`). Templates, domain definitions, and sample databases for these demos are in [`examples/`](examples/) in this repository.

| Sandbox | Datasource | What it shows |
| :--- | :--- | :--- |
| [intent-sql-sqlite-hr](https://orbitsandbox.dev/intent-sql-sqlite-hr) | SQLite | Reporting and lookups on a sample HR database |
| [intent-duckdb-analytics](https://orbitsandbox.dev/intent-duckdb-analytics) | DuckDB | Analytics questions on a sample DuckDB warehouse |
| [intent-duckdb-ev-population](https://orbitsandbox.dev/intent-duckdb-ev-population) | DuckDB | Large-scale EV registration–style stats (Washington sample data) |
| [intent-http-jsonplaceholder](https://orbitsandbox.dev/intent-http-jsonplaceholder) | HTTP (JSON) | REST-style JSON APIs (JSONPlaceholder demo) |
| [intent-http-paris-opendata](https://orbitsandbox.dev/intent-http-paris-opendata) | HTTP (JSON) | Paris open data — events and city datasets |
| [intent-mongodb-mflix](https://orbitsandbox.dev/intent-mongodb-mflix) | MongoDB | NL queries over the sample MFlix movies database |
| [intent-graphql-spacex](https://orbitsandbox.dev/intent-graphql-spacex) | GraphQL | Natural language against a public GraphQL API (SpaceX) |
| [simple-chat](https://orbitsandbox.dev/simple-chat) | Passthrough | Pure conversation — no retrieval layer |
| [simple-chat-with-files](https://orbitsandbox.dev/chat-with-files) | Multimodal | Upload documents or images; answers use RAG over your files |

**ORBIT in Production:** [PoliceStats.ca](https://policestats.ca) uses ORBIT to power a public chat over Canadian municipal police open data. Users ask in plain language about auto theft, break-ins, crime by neighbourhood, and cross-city comparisons.

If you or someone you know is using ORBIT in production, please [let us know](https://schmitech.ai/en/contact) and we will add the project here.

If you find ORBIT useful, please **[star the repo](https://github.com/schmitech/orbit)**—you'll see new releases in your feed and make the project easier for others to discover.

---

### 🧩 Supported Integrations

**Inference:** OpenAI, Anthropic, Google Gemini, Cohere, Groq, DeepSeek, Mistral, AWS Bedrock, Azure, Together, Ollama, vLLM, llama.cpp.

**Data Adapters:** PostgreSQL, MySQL, MongoDB, Elasticsearch, DuckDB, Chroma, Qdrant, Pinecone, Milvus, Weaviate.

---

### Quick start

Run ORBIT locally with Docker Compose:

```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d

# Wait for services to start, then test
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: local-test' \
  -d '{
    "messages": [{"role": "user", "content": "Summarize ORBIT in one sentence."}],
    "stream": false
  }'
```

**Admin panel:** When ORBIT is listening on port 3000, open [http://localhost:3000/admin](http://localhost:3000/admin) (or `https://<your-host>/admin` in production). Sign in with username **`admin`** and the password from **`ORBIT_DEFAULT_ADMIN_PASSWORD`** (`env.example` defaults to **`admin123`**). Change that password before exposing the server.

For GPU acceleration (NVIDIA): `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`

**C) Run ORBIT from the pre-built image** (server only; point it at your own Ollama)

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 3000:3000 schmitech/orbit:basic
```

If Ollama runs on your host (e.g. port 11434), add `-e OLLAMA_HOST=host.docker.internal:11434` so the container can reach it. The image includes simple-chat only; for the full stack (Ollama + models), use option B or the [Docker Guide](docker/README.md).

---

### 🚀 Key Capabilities

*   **Unified API:** Switch OpenAI, Anthropic, Gemini, Groq, or local models (Ollama/vLLM) by config.
*   **Agentic AI & MCP:** Compatible with **Model Context Protocol (MCP)** for tool-enabled agent workflows.
*   **Native RAG:** Connect Postgres, MongoDB, Elasticsearch, or Pinecone for natural-language data access.
*   **Voice-First:** Real-time, full-duplex speech-to-speech with interruption handling via PersonaPlex.
*   **Governance Built In:** RBAC, rate limiting, audit logging, and circuit breakers.
*   **Privacy First:** Self-host on your own infrastructure for full data control.

---

### 🆚 Why Enterprise Teams Choose ORBIT

| If you use... | You often get... | ORBIT gives you... |
| :--- | :--- | :--- |
| Single-provider SDKs | Vendor lock-in and provider-specific rewrites | One OpenAI-compatible API across providers |
| Basic LLM proxy only | Model routing, but no data connectivity | Unified model + retrieval + tooling gateway |
| RAG-only framework | Strong retrieval, weak multi-provider inference control | Native RAG with multi-provider and policy controls |
| In-house glue scripts | Fragile integrations and high ops cost | A production-ready gateway with RBAC, limits, and logs |

---

### 🏢 Enterprise Readiness

*   **Deployment Flexibility:** Run ORBIT in your own environment for strict data-boundary requirements.
*   **Operational Control:** Standardize access, traffic policies, and audit trails behind one gateway.
*   **Architecture Fit:** Integrates with existing data systems, identity patterns, and model providers.
*   **Service Backing:** [Schmitech](https://schmitech.ai/) provides enterprise onboarding, deployment support, and ongoing operations guidance.

---

### 🎯 Common Use Cases

*   **Enterprise RAG:** Query SQL, NoSQL, and vector stores with one natural-language API.
*   **Provider Failover:** Route between Ollama, vLLM, OpenAI, Anthropic, Gemini, Groq, etc. without rewrites.
*   **Voice Agents:** Build full-duplex speech-to-speech experiences with interruption handling.
*   **MCP Tooling Layer:** Expose data and actions to agentic apps through MCP compatibility.

---

### 🛠️ One Gateway, Many Clients

| Client | Link | Description |
| :--- | :--- | :--- |
| **Web Chat** | [ORBIT Chat](clients/orbitchat/) | React UI. |
| **CLI** | `pip install schmitech-orbit-client` | Chat directly from your terminal. |
| **Mobile** | [ORBIT Mobile](clients/orbit-mobile/) | iOS & Android app built with Expo. |
| **SDKs** | [Node SDK](clients/node-api/) | Or use any standard OpenAI-compatible SDK. |

---

### 📦 Deployment

**Docker Compose (Fastest Path)**
```bash
git clone https://github.com/schmitech/orbit.git && cd orbit/docker
docker compose up -d
```
This starts ORBIT + Ollama with SmolLM2, auto-pulls models, and exposes the API on port 3000. The web admin UI is at **`/admin`** on the same host (e.g. [http://localhost:3000/admin](http://localhost:3000/admin))—use **`admin`** and **`ORBIT_DEFAULT_ADMIN_PASSWORD`** (see `env.example`). Connect [orbitchat](https://www.npmjs.com/package/orbitchat) from your host: `ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' npx orbitchat`

**Pre-built image only** (server + your own Ollama): `docker pull schmitech/orbit:basic` then `docker run -d --name orbit-basic -p 3000:3000 -e OLLAMA_HOST=host.docker.internal:11434 schmitech/orbit:basic` if Ollama runs on the host.

See the full [Docker Guide](docker/README.md) for GPU mode, volumes, single-container run, and configuration.

**Stable Release (Recommended for Production)**
```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.6.4/orbit-2.6.4.tar.gz -o orbit-2.6.4.tar.gz
tar -xzf orbit-2.6.4.tar.gz && cd orbit-2.6.4

cp env.example .env && ./install/setup.sh
source venv/bin/activate
./bin/orbit.sh start && cat ./logs/orbit.log
```

The admin panel is at **`http://localhost:3000/admin`** by default (match **`API_SERVER_URL`** in `.env` if you changed the bind address). Sign in as **`admin`** with **`ORBIT_DEFAULT_ADMIN_PASSWORD`** from `env.example`.

---

### 📚 Resources & Support

*   [Step-by-Step Tutorial](docs/tutorial.md) – Learn how to chat with your own data in minutes.
*   [Cookbook](docs/cookbook/) – Recipes and how-tos for configuration and real-world use cases.
*   [Documentation](docs/) – Full architecture and setup guides.
*   [GitHub Issues](https://github.com/schmitech/orbit/issues) – Bug reports and feature requests.

## 📄 License

Apache 2.0 – see [LICENSE](LICENSE).
