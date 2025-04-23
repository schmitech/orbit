<div align="center">
  <img src="orbit.png" width="200" height="200" alt="ORBIT">
  
  # ORBIT: Open Retrieval-Based Inference Toolkit
</div>

ORBIT is a modular, self-hosted toolkit that provides a unified API for open-source AI inference models, enabling you to operate without paid APIs. Host AI models on your infrastructure, maintain control over your data, and eliminate commercial dependency.

---

## 🌟 Why Choose ORBIT?

Commercial AI services often introduce limitations, pricing fluctuations, and policy changes impacting your operations. ORBIT gives you:

- 🔐 **Privacy:** Data remains within your infrastructure.
- 🔄 **Flexibility:** Deploy on cloud, on-premise, or hybrid environments.
- 🔧 **Customization:** Fully adaptable to your specific domain needs.
- 🚫 **No Vendor Lock-in:** Full control over your inference models and data.

---

## 🎯 Key Use Cases

- **Customer Support:** Integrate AI with your organization's knowledge base.
- **Internal Knowledge Management:** Intelligent document-based Q&A systems.
- **Education:** Interactive learning assistants tailored to course materials.
- **Healthcare:** HIPAA-compliant medical information systems.
- **Financial Services:** Secure financial advisory assistants.
- **Legal Services:** Confidential legal research tools.

---

## 🛠️ Technical Highlights

- **Tech Stack:** Python, FastAPI, TypeScript, React
- **Vector Search:** Semantic search with ChromaDB (Milvus support coming soon)
- **Real-Time Responses:** Streamlined user experience
- **Modular & Extensible:** Easily adapt or expand functionalities
- **Production Ready:** Robust error handling, logging, and monitoring
- **Cross-Platform Support:** Compatible with diverse infrastructures

---

## 🏗️ Architecture Overview

![Architecture Overview](architecture.png)

---

## 📌 Quick Start Guide

### ✅ Prerequisites

- Python 3.12+
- Ollama Server
- MongoDB (API Key management)
- ChromaDB

### ⚙️ Server Setup

```bash
cd server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Edit configurations
```

### 📚 ChromaDB Setup

```bash
cd chroma
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run ChromaDB
chroma run --host localhost --port 8000 --path ./chroma_db
```

Access dashboard at: `http://localhost:8000`

Verify ChromaDB:
```bash
python -c "import chromadb; print(chromadb.__version__)"
```

**Ingest Data:**

```bash
python ./qa-assistant/create_qa_pairs_collection.py city ../datasets/city-qa-pairs.json
python query-chroma-collection.py "Test query"
```

### 🌐 Launch Server

```bash
cd server
uvicorn server:app --reload --host 0.0.0.0 --port 3000
```

API available at `http://localhost:3000`

### 🔑 API Key Setup

You need an API key to use the client APIs. A key will be associated with a prompt and a collection (i.e. Database, Vector DB, Elasticsearch index, etc.).

```bash
python ./admin/api_key_manager.py --url http://localhost:3000 create --collection city --name "City Assistant" --prompt-file ../examples/chroma/qa-assistant/qa-assistant-prompt.txt  --prompt-name "City Assistant Prompt"
```

### 📡 API Setup
```bash
cd api
npm install
npm run build

# Test API
# Batch queries:
npm run test-query-from-pairs ../examples/datasets/city-qa-pairs.json  "http://localhost:3000"  "api_123456789" 5

# or a single Query:
npm run test-query "What is the process for getting a sidewalk repaired?" "http://localhost:3000"  "api_123456789"
```

### 🎨 Widget Setup

```bash
cd widget
npm install
npx vite build
```

---

## 🔍 Example Applications

### Web Chatbot

```bash
cd examples/simple-chatbot
npm install
npm run dev
```

Access at: `http://localhost:5173`

### CLI Example

Check out the Python CLI example at `/examples/simple-cli`.

---

## 🧑‍💻 Development Workflow

Run locally for development:

1. **Start ChromaDB:**
    ```bash
    cd chroma && chroma run --host localhost --port 8000 --path ./chroma_db
    ```

2. **Start MongoDB:**
    ```bash
    # If using MongoDB Atlas, ensure your IP is whitelisted
    # If using local MongoDB:
    mongod --dbpath /path/to/data/directory
    ```

3. **Create API Key:**
    ```bash
    cd server/admin
    python3 api_key_manager.py --url http://localhost:3000 create --collection default --name "Development" --notes "Development API Key"
    ```
    Save the generated API key for the next steps.

4. **Launch Server:**
    ```bash
    cd server && start.sh
    ```