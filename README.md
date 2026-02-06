<div align="center">
  <a href="https://github.com/schmitech/orbit">
    <img src="docs/images/orbit-logo-transparent.png" alt="ORBIT Logo" width="500" style="border: none; outline: none; box-shadow: none;"/>
  </a>
</div>
  
<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://github.com/schmitech/orbit/releases"><img src="https://img.shields.io/github/v/release/schmitech/orbit" alt="Release"></a>
  <a href="https://pypi.org/project/schmitech-orbit-client/"><img src="https://img.shields.io/pypi/v/schmitech-orbit-client?label=PyPI%20client" alt="PyPI"></a>
  <a href="https://www.npmjs.com/package/@schmitech/chatbot-widget"><img src="https://img.shields.io/npm/v/@schmitech/chatbot-widget.svg?logo=npm&label=Widget%20NPM" alt="NPM"></a>
  <a href="https://github.com/schmitech/orbit" target="_blank">
    <img src="https://img.shields.io/github/stars/schmitech/orbit?style=social&label=Star" alt="GitHub stars">
  </a>
</p>

</div>

# ORBIT – One gateway for every model and data source.
**Open Retrieval-Based Inference Toolkit**

Stop rewriting your app every time you switch LLMs. ORBIT unifies **20+ AI providers** with your databases, vector stores, and APIs—all through one self-hosted gateway.

**Ship faster. Stay portable. Keep your data private.**

> ⭐ **Help ORBIT grow:** Star + watch the repo so other builders can find it and we can keep funding new adapters, tutorials, and sandbox credits.

<div align="center">
  <video src="https://github.com/user-attachments/assets/bdb0330d-b03a-44ba-ad97-c3a363a45a7d" controls width="100%">
    Your browser does not support the video tag.
  </video>
  <br/>
  <em>See ORBIT's unified LLM workspace in action.</em>
</div>

---

## 🎯 Why ORBIT?

**The Problem:** Building AI apps means choosing between vendor lock-in, complex integrations, and privacy concerns.

- **Vendor lock-in:** Switching from OpenAI to Anthropic means rewriting your code
- **Complex RAG:** Connecting databases, vector stores, and APIs requires custom glue code
- **Privacy concerns:** Sending sensitive data to third-party APIs
- **Fragmented tools:** Different SDKs, auth methods, and APIs for each provider

**The Solution:** ORBIT is a **self-hosted, unified gateway** that gives you:

✅ **Portability** — Switch LLM providers with a config change, not code changes  
✅ **Built-in RAG** — Connect SQL databases, vector stores, and APIs through natural language  
✅ **Full-Duplex Voice** — Real-time speech-to-speech conversations with natural dynamics  
✅ **Data sovereignty** — Keep your data on your infrastructure  
✅ **One API** — OpenAI-compatible interface that works with any provider  
✅ **Production-ready** — Rate limiting, security, monitoring, and fault tolerance built-in
****
**Who it's for:** Developers building AI applications who want flexibility, privacy, and control without the complexity of managing multiple integrations.

- **Questions?** Open an [issue](https://github.com/schmitech/orbit/issues)
- **Updates:** Check the [changelog](CHANGELOG.md)
- **Commercial Support:** [OrbitPods.io](https://orbitpods.io/)
- **Maintained by:** [Schmitech.ai](https://schmitech.ai/en/)

## At a Glance

- [ORBIT – One gateway for every model and data source.](#orbit--one-gateway-for-every-model-and-data-source)
  - [🎯 Why ORBIT?](#-why-orbit)
  - [At a Glance](#at-a-glance)
  - [⭐ Help ORBIT Grow](#-help-orbit-grow)
  - [🚀 Highlights](#-highlights)
  - [🧩 Supported Integrations](#-supported-integrations)
  - [🛠️ Common Use Cases](#️-common-use-cases)
  - [⚡ Getting Started](#-getting-started)
    - [1. Explore the sandbox](#1-explore-the-sandbox)
    - [2. Run the Docker demo](#2-run-the-docker-demo)
    - [3. Install the latest release](#3-install-the-latest-release)
    - [4. Build from source](#4-build-from-source)
  - [💬 Clients \& SDKs](#-clients--sdks)
  - [🗃️ Chat with Your Data](#️-chat-with-your-data)
  - [📐 Math \& Scientific Rendering](#-math--scientific-rendering)
  - [📚 Resources](#-resources)
  - [🧠 Need help?](#-need-help)
  - [📄 License](#-license)

---

## ⭐ Help ORBIT Grow

Open-source traction is the fuel that keeps ORBIT's sandbox, docs, adapters, and demos free for everyone.

- ⭐ **Star + watch** the repo to surface ORBIT in GitHub search and get notified when a new release drops.
- ✉️ **Share** the sandbox or demo video with the teammate who's still wiring SDKs by hand.
- 📣 **Tell us what to build next** in [Discussions](https://github.com/schmitech/orbit/discussions); upvotes there help us prioritize the roadmap you care about.

## 🚀 Highlights

- **Unified API for 20+ AI providers** – Swap between OpenAI, Anthropic, Gemini, Groq, DeepSeek, Cohere, Mistral, AWS Bedrock, Azure OpenAI, Together, xAI/Grok, and any local stack (Ollama, llama.cpp, vLLM, Hugging Face) via config only.
- **Full-duplex speech-to-speech** – Build voice assistants with real-time, bidirectional audio using NVIDIA's PersonaPlex integration. Natural conversations with interruptions and backchannels—no STT→LLM→TTS cascade needed.
- **Adapters for every data shape** – Intent + QA retrievers cover Postgres/MySQL/DuckDB/SQLite, MongoDB, Elasticsearch, HTTP APIs, and the major vector stores (Chroma, Qdrant, Pinecone, Milvus, Weaviate).
- **Batteries included** – Per-key RBAC, rate limits/quotas, audit logging (SQLite or MongoDB + optional Elasticsearch), content safety providers, retries/circuit breakers, and observability dashboards ship by default.
- **Multimodal + widgets** – Ship chat UIs via orbitchat CLI, React widget, or OpenAI-compatible API; render charts, math, and audio/video streams out of the box.
- **Zero lock-in deployments** – Try it in the hosted sandbox, run a Docker preset in under 60 seconds, or install the full server with TLS + GPU detection when you're ready for production.

## 🧩 Supported Integrations

No more glue code—connect everything through adapters and declarative config.

**Inference & embeddings**
- LLM providers: OpenAI, Anthropic, Google Gemini/Vertex, Groq, DeepSeek, Mistral, Cohere, AWS Bedrock, Azure OpenAI, Together, xAI, OpenRouter, IBM watsonx, plus local engines (Ollama, vLLM, llama.cpp, Hugging Face).
- Embeddings & rerankers: OpenAI, Jina, Cohere, Mistral, Ollama, llama.cpp, and any custom GGUF via the embeddings service.
- Vision/speech: Gemini, OpenAI, Anthropic, plus audio adapters documented in [`docs/audio/`](docs/audio/).
- **Speech-to-speech:** Full-duplex voice with PersonaPlex—real-time bidirectional audio, interruption handling, and backchannels.

**Data & knowledge sources**
- SQL + analytics: PostgreSQL, MySQL, SQL Server, DuckDB, SQLite, and intent-based adapters for customer schemas.
- NoSQL & search: MongoDB aggregation pipelines, Elasticsearch, Redis JSON/hashes.
- Vector stores: Chroma, Qdrant, Pinecone, Milvus, Weaviate (with QA + intent specializations).
- Files & APIs: PDF/Markdown/CSV ingestion, HTTP/REST connectors, and composite adapters that orchestrate multiple sources with guardrails.
- Infra glue: Redis caching, MongoDB or SQLite backends, optional Elasticsearch auditing.

## 🛠️ Common Use Cases

- **Voice assistants & IVR** – Deploy full-duplex voice agents for customer service, city hotlines, or internal helpdesks powered by PersonaPlex full-duplex speech-to-speech.
- **Analytics copilots** – Turn "How many signups came from APAC last week?" into SQL, MongoDB, or DuckDB queries with safety filters.
- **Enterprise knowledge chat** – Blend product docs, support tickets, and vector embeddings into a single chat endpoint with automatic citations.
- **Provider gateways** – Route traffic between OpenAI/Anthropic/local Ollama with fallbacks, budgets, and tenant-specific presets.
- **Agentic workflows** – Chain adapters that hit REST APIs, trigger automations, or fan out to multiple retrievers before summarizing responses.

## ⚡ Getting Started

### 1. Explore the sandbox

<p align="center">
  <a href="https://orbitsandbox.dev/" target="_blank"><img src="https://img.shields.io/badge/🚀_Try_ORBIT_Sandbox-Interactive_Examples-brightgreen?style=for-the-badge" alt="Try ORBIT Sandbox"></a>
</p>

Browse interactive examples showcasing ORBIT's adapters, prompts, and capabilities—no install required.

### 2. Run the Docker demo

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 5173:5173 -p 3000:3000 schmitech/orbit:basic
```

- Auto-detects CPU/GPU via `ORBIT_PRESET=auto` (override with `smollm2-1.7b-gpu` or `-cpu`).
- Includes ORBIT server, orbitchat UI, and an Ollama preset so you can chat instantly.
- More options live in [docker/README.md](docker/README.md).

### 3. Install the latest release

- **Prereqs:** Python 3.12+, Node 18+, npm, and any AI-provider keys (OpenAI, Anthropic, Cohere, Gemini, Mistral, etc.).
- **Optional deps:** MongoDB, Redis, and a vector DB (Chroma, Qdrant, Pinecone, etc.).

```bash
curl -L https://github.com/schmitech/orbit/releases/download/v2.4.0/orbit-2.4.0.tar.gz -o orbit-2.4.0.tar.gz
tar -xzf orbit-2.4.0.tar.gz && cd orbit-2.4.0

cp env.example .env && ./install/setup.sh
source venv/bin/activate

./bin/orbit.sh start && cat ./logs/orbit.log
```

- To use local models with Ollama, first install it: `curl -fsSL https://ollama.com/install.sh | sh`, then pull a model such as `ollama pull granite4:1b` or another of your choice.
- Default adapters live in `config/adapters/passthrough.yaml` and `config/adapters/multimodal.yaml`; update `config/ollama.yaml` for model changes.
- Visit [`http://localhost:3000/dashboard`](http://localhost:3000/dashboard) to monitor the ORBIT server.

<div align="center">
  <video src="https://github.com/user-attachments/assets/ec9bda9b-3b86-488f-af16-ec8e9d964697" controls width="100%">
    Your browser does not support the video tag.
  </video>
  <br/>
  <em>The ORBIT dashboard for adapter management and monitoring.</em>
</div>

### 4. Build from source

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit && cp env.example .env
./install/setup.sh && source venv/bin/activate
./bin/orbit.sh start && ./bin/orbit.sh key create
```

- Bring your own API keys (OpenAI, Anthropic, Cohere, Gemini, Mistral, etc.).
- Works great with Ollama, vLLM, llama.cpp, Redis, MongoDB, and vector DBs.
- Check logs via `tail -f ./logs/orbit.log` and open [`http://localhost:3000/dashboard`](http://localhost:3000/dashboard).

---

## 💬 Clients & SDKs

- **`orbit-chat` CLI:** `pip install schmitech-orbit-client && orbit-chat --api-key <KEY>`
- **React web app:** `npm install -g orbitchat && orbitchat --api-url http://localhost:3000 --api-key <KEY> --open`
- **Embeddable widget:** Drop [@schmitech/chatbot-widget](clients/chat-widget/README.md) into any site for floating or inline chat.
- **Node SDK:** `npm install @schmitech/chatbot-api` and stream responses in TypeScript/JavaScript apps.
- **OpenAI-compatible API:** Point the official `openai` Python client at `base_url="http://localhost:3000/v1"` to reuse existing code.

<div align="center">
  <video src="https://github.com/user-attachments/assets/97a872f3-0752-4c22-a690-bd75635a0741" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Using the <code>orbit-chat</code> CLI. Run <code>orbit-chat -h</code> for options.</i>
</div>

---

## 🗃️ Chat with Your Data

See the **[tutorial](docs/tutorial.md)** for step-by-step instructions on connecting your data, performing retrieval, and watching as ORBIT converts natural language into SQL queries and API calls.

<div align="center">
  <video src="https://github.com/user-attachments/assets/34ee6047-73b0-4ab6-bb0a-9af99bfe962e" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Electric Vehicle Population Data through natural language (Data Source: <a href="https://data.wa.gov/Transportation/Electric-Vehicle-Population-Data/f6w7-q2d2/about_data">data.wa.gov</a>).</i>
</div>

---

## 📐 Math & Scientific Rendering

ORBIT's built-in adapters and clients support advanced rendering for mathematical notation (KaTeX) and interactive charts, perfect for educational and scientific applications.

<div align="center">
  <video src="https://github.com/user-attachments/assets/38630cdc-ed1b-46cd-a804-35850837e9d0" controls width="100%">
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Demo of the Math Tutor adapter showcasing KaTeX and interactive graphing.</i>
</div>

---

## 📚 Resources

- [Installation guide](docs/server.md)
- [Configuration reference](docs/configuration.md)
- [Authentication & API keys](docs/authentication.md)
- [RAG adapters](docs/adapters/adapters.md)
- [Voice & audio adapters](docs/audio/)
- [PersonaPlex speech-to-speech](docs/personaplex-integration.md)
- [Roadmap](docs/roadmap/README.md)
- [Contributing](CONTRIBUTING.md) & [Code of Conduct](CODE_OF_CONDUCT.md)

## 🧠 Need help?

- Open an [issue](https://github.com/schmitech/orbit/issues) or [discussion](https://github.com/schmitech/orbit/discussions).
- Commercial support + managed hosting: [OrbitPods.io](https://orbitpods.io/).
- Say hi on [Schmitech.ai](https://schmitech.ai/en/).

## 📄 License

Apache 2.0 – see [LICENSE](LICENSE).
