# AI-Driven Q&A Assistant Framework

[![Node.js](https://img.shields.io/badge/Node.js-18%2B-brightgreen.svg)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

A customizable AI chatbot engine designed for organizations that need control over their data and inference models. This framework provides a complete solution for building, deploying, and managing AI-powered question-answering systems with a focus on privacy, customization, and ease of integration.

### Key Features

- **Privacy-First Architecture**: All data processing and model inference happens within your infrastructure
- **Multiple Backend Support**: Compatible with Ollama, vLLM and Hugging Face
- **Vector Database Integration**: Built-in support for ChromaDB for efficient semantic search
- **Text-to-Speech Capabilities**: Integrated ElevenLabs support for voice responses
- **Ready-to-Use Widget**: Easy-to-integrate UI component for any website
- **Customizable UI**: Fully customizable chat widget
- **Example Applications**: Complete working examples for quick start

### Use Cases

- **Customer Support**: Deploy AI-powered support systems with your company's knowledge base
- **Internal Knowledge Management**: Create intelligent Q&A systems for employee documentation
- **Educational Platforms**: Build interactive learning assistants with custom course materials
- **Healthcare**: Develop HIPAA-compliant medical information systems
- **Financial Services**: Create secure financial advisory chatbots
- **Legal Services**: Build confidential legal information retrieval systems

### Technical Highlights

- **Modern Stack**: Built with Node.js, Python, TypeScript, and React
- **Vector Search**: Efficient semantic search using ChromaDB
- **Real-time Processing**: Stream responses for better user experience
- **Modular Design**: Easy to extend and customize for specific needs
- **Production Ready**: Includes error handling, logging, and monitoring
- **Cross-Platform**: Works on any infrastructure (cloud, on-premise, hybrid)

## 📋 Table of Contents

- [AI-Driven Q\&A Assistant Framework](#ai-driven-qa-assistant-framework)
    - [Key Features](#key-features)
    - [Use Cases](#use-cases)
    - [Technical Highlights](#technical-highlights)
  - [📋 Table of Contents](#-table-of-contents)
  - [🎯 Why This Project Exists](#-why-this-project-exists)
  - [🧩 Project Components](#-project-components)
  - [🏗️ Architecture](#️-architecture)
    - [System Overview](#system-overview)
    - [How It Works](#how-it-works)
  - [🚀 Getting Started](#-getting-started)
    - [Prerequisites](#prerequisites)
    - [Server Setup](#server-setup)
    - [ChromaDB Setup](#chromadb-setup)
      - [Running ChromaDB](#running-chromadb)
      - [Verify ChromaDB Version](#verify-chromadb-version)
      - [Ingesting Data](#ingesting-data)
    - [Text-to-Speech Testing](#text-to-speech-testing)
    - [Running the Server](#running-the-server)
    - [API Setup](#api-setup)
    - [Widget Setup](#widget-setup)
    - [Example Applications](#example-applications)
  - [💻 Development Workflow](#-development-workflow)
  - [📄 License](#-license)

## 🎯 Why This Project Exists

Most commercial AI chatbots present several challenges for organizations:

| Challenge | Impact | Our Solution |
|-----------|--------|--------------|
| **Privacy Risks** | Organizations with strict data regulations cannot send sensitive data to external APIs | All data stays within your infrastructure |
| **Vendor Lock-in** | Dependency on proprietary APIs limits control over models and data | Complete control over inference models |
| **Limited Deployment** | Lack of flexibility for diverse infrastructure requirements | Deploy anywhere - cloud, on-premise, or hybrid |
| **Reduced Customization** | Inability to fine-tune inference for domain-specific needs | Fully customizable for your specific use case |

## 🧩 Project Components

This repository contains four interconnected projects:

1. **`server/`** - Backend server application handling inference and data management
2. **`examples/`** - Ready-to-use sample applications demonstrating integration
3. **`chroma/`** - Vector database configuration for managing embeddings
4. **`api/`** - JavaScript/TypeScript client library for easy integration
5. **`widget/`** - Ready-to-use UI component that can be embedded into any website

> **Note:** Each component has its own detailed README file with specific setup instructions and configuration details.

## 🏗️ Architecture

### System Overview
![Architecture Overview](architecture.png)

### How It Works
![How it Works](llm-chatbot-architecture.png)

## 🚀 Getting Started

### Prerequisites

- Node.js v16 or higher
- Python 3.12+ (for ChromaDB)
- Ollama installed locally
- ElevenLabs API key (for text-to-speech capabilities)
- ChromaDB installed locally or in a server/container

### Server Setup

```bash
# Navigate to server directory
cd server

# Install dependencies
npm install

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

### Text-to-Speech Testing

Test your ElevenLabs API key:

```bash
curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/XrExE9yKIg1WjnnlVkGX" \
  -H "xi-api-key: $ELEVEN_LABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test audio generation", "model_id": "eleven_monolingual_v1"}' \
  --output test.mp3
```

### Running the Server

```bash
cd server
npm run server -- ollama  # Use 'hf' for Hugging Face backend
```

### API Setup

The API is a JavaScript/TypeScript client library for applications to communicate with the server.

```bash
cd api
npm install
npm run build
```

The API will be available at `http://localhost:3001`.

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
   cd server && npm run server -- ollama
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
   cd examples/simple-chatbot && npm run dev
   ```

## 📄 License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.
