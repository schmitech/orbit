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

<p align="center">
  <a href="https://github.com/schmitech/orbit/stargazers"><img src="https://img.shields.io/github/stars/schmitech/orbit?style=for-the-badge&logo=github&label=Star%20on%20GitHub&color=yellow" alt="Star on GitHub"></a>
</p>

<div align="center">
  <video src="https://github.com/user-attachments/assets/b188a903-c6b0-44a9-85ad-5191f36778dc" controls width="100%">
    Your browser does not support the video tag.
  </video>
  <br/>
  <em>See ORBIT’s unified LLM workspace in action.</em>
</div>

- **Questions?** Open an [issue](https://github.com/schmitech/orbit/issues)
- **Updates:** Check the [changelog](CHANGELOG.md)
- **Commercial Support:** [OrbitPods.io](https://orbitpods.io/)
- **Maintained by:** [Schmitech.ai](https://schmitech.ai/en/)

## At a Glance

- [ORBIT – One gateway for every model and data source.](#orbit--one-gateway-for-every-model-and-data-source)
  - [At a Glance](#at-a-glance)
  - [✨ Highlights](#-highlights)
  - [⚡ Start in Minutes](#-start-in-minutes)
    - [1. Explore the sandbox](#1-explore-the-sandbox)
    - [2. Run the Docker demo](#2-run-the-docker-demo)
    - [3. Install the latest release](#3-install-the-latest-release)
    - [4. Build from source](#4-build-from-source)
  - [💬 Clients \& SDKs](#-clients--sdks)
  - [🗃️ Chat with Your Data](#️-chat-with-your-data)
  - [📚 Resources](#-resources)
  - [🧠 Need help?](#-need-help)
  - [📄 License](#-license)

---

## ✨ Highlights

- **One control plane** for 20+ LLM providers, plus Ollama, llama.cpp, and vLLM for local inference.
- **First-class RAG adapters** for SQL, MongoDB, Elasticsearch, Pinecone, Qdrant, Chroma, Redis, HTTP APIs, and file uploads.
- **Intent-aware routing** that converts natural language to SQL queries, Elasticsearch DSL, Mongo filters, and custom API calls.
- **Multimodal** support across OpenAI, Gemini, Anthropic, Ollama and vLLM.
- **Built-in security** with API keys and moderation hooks.

---

## ⚡ Start in Minutes

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

## 📚 Resources

- [Installation guide](docs/server.md)
- [Configuration reference](docs/configuration.md)
- [Authentication & API keys](docs/authentication.md)
- [RAG adapters](docs/adapters/adapters.md)
- [Roadmap](docs/roadmap/README.md)
- [Contributing](CONTRIBUTING.md) & [Code of Conduct](CODE_OF_CONDUCT.md)

## 🧠 Need help?

- Open an [issue](https://github.com/schmitech/orbit/issues) or [discussion](https://github.com/schmitech/orbit/discussions).
- Commercial support + managed hosting: [OrbitPods.io](https://orbitpods.io/).
- Say hi on [Schmitech.ai](https://schmitech.ai/en/).

## 📄 License

Apache 2.0 – see [LICENSE](LICENSE).
