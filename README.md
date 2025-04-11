# ORBIT - Open Retrieval-Based Inference Toolkit

ORBIT is a modular, self-hosted service that provides a unified API for interacting with various open-source AI inference models without relying on paid API subscriptions. It allows you to run AI models on your own infrastructure, maintaining full control over your data and eliminating dependency on commercial AI services.

## Why ORBIT?

As commercial AI services continue to evolve, they often introduce limitations, pricing changes, or policy restrictions that can impact your applications. This platform gives you independence by:

- Running entirely on your own infrastructure
- Supporting both high-performance and smaller, more efficient models
- Keeping your data private and secure
- Allowing complete customization of the inference pipeline
- Avoiding vendor lock-in with a modular, open design

Most commercial generative AI tools present several challenges for organizations:

| Challenge | Impact | Solution |
|-----------|--------|--------------|
| **Privacy Risks** | Organizations with strict data regulations cannot send sensitive data to external APIs | All data stays within your infrastructure |
| **Vendor Lock-in** | Dependency on proprietary APIs limits control over models and data | Complete control over inference models |
| **Limited Deployment** | Lack of flexibility for diverse infrastructure requirements | Deploy anywhere - cloud, on-premise, or hybrid |
| **Reduced Customization** | Inability to fine-tune inference for domain-specific needs | Fully customizable for your specific use case |

### Use Cases

- **Customer Support**: Deploy AI-powered support systems with your company's knowledge base
- **Internal Knowledge Management**: Create intelligent Q&A systems for employee documentation
- **Educational Platforms**: Build interactive learning assistants with custom course materials
- **Healthcare**: Develop HIPAA-compliant medical information systems
- **Financial Services**: Create secure financial advisory chatbots
- **Legal Services**: Build confidential legal information retrieval systems

### Technical Highlights

- **Stack**: Python, FastAPI, TypeScript, and React
- **Vector Search**: Semantic search using ChromaDB (support for Milvus coming soon)
- **Real-time Processing**: Stream responses for better user experience
- **Modular Design**: Easy to extend and customize for specific needs
- **Production Ready**: Includes error handling, logging, and monitoring
- **Cross-Platform**: Works on any infrastructure (cloud, on-premise, hybrid)

## 🏗️ Architecture

### System Overview
![Architecture Overview](ORBIT.png)


## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- Ollama Server (local or remote)
- MongoDB for API Key Management
- ChromaDB (local or remote)

### Server Setup

```bash
# Navigate to server directory
cd /backend/server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create configuration file
cp .env.example .env
# Edit .env with your configuration
```

### ChromaDB Setup

```bash
# Navigate to ChromaDB directory
cd chroma

# Create virtual environment
python -m venv venv 
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

> **Note:** If using Conda and seeing `(base)` in your terminal, run `conda deactivate` before creating venv or use `conda config --set auto_activate_base false` to prevent automatic activation.

#### Running ChromaDB

```bash
chroma run --host localhost --port 8000 --path ./chroma_db
```

The Chroma dashboard will be available at `http://localhost:8000`.

#### Verify ChromaDB Version

```bash
python -c "import chromadb; print(chromadb.__version__)"
```

#### Ingesting Data

```bash
python create-chroma-collection.py qa-pairs.json
```

Test your ingested data:
```bash
python query-chroma-collection.py "Your test query here"
```

### Running the Server

```bash
cd server
uvicorn server:app --reload --host 0.0.0.0 --port 3000
```

### API Setup

The API is a JavaScript/TypeScript client library for applications to communicate with the server.

```bash
cd api
npm install
npm run build
```

The API will be available at `http://localhost:3000`.

### Widget Setup

The widget provides a ready-to-use UI component for website integration.

```bash
cd widget
npm install
npx vite build
```

### Example Applications

Simple web chatbots demonstrating server integration:

```bash
cd examples/simple-chatbot
npm install
npm run dev
```

The example will be available at `http://localhost:5173`.

## 💻 Development Workflow

To run the entire system locally for development:

1. Start Chroma: 
   ```bash
   cd chroma && chroma run --host localhost --port 8000 --path ./chroma_db
   ```

2. Start the Server: 
   ```bash
   cd server && uvicorn server:app --reload --host 0.0.0.0 --port 3000
   ```

3. Build the API: 
   ```bash
   cd api && npm run build
   ```

4. Build the Widget: 
   ```bash
   cd widget && npm run build
   ```

5. Start the Example App: 
   ```bash
   cd examples/web-widget && npm run dev
   ```

There is a python CLI example to under /examples/simple-cli if you prefer to test on the command line. 

## 📄 License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.
