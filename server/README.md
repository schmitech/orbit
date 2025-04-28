# 🚀 FastAPI Chat Server

A FastAPI server providing conversational AI with Ollama integration, ChromaDB for retrieval-augmented generation, safety checks, API key authentication, and elasticsearch logging.

---

## 🌟 Key Features

- **Context-Aware Chat**: Intelligent responses enhanced with retrieval-augmented generation (RAG).
- **ChromaDB & Ollama Integration**: Efficient vector database and embedding management.
- **API Key Authentication**: Secure access control for chat requests.
- **Safety Guardrails**: Configurable safety service for content moderation.
- **Real-time Streaming**: Support for streaming responses via Server-Sent Events (SSE).
- **Logging**: Detailed logging with Elasticsearch support.
- **HTTPS Support**: Secure communication using TLS.


## 🛠️ Installation

```bash
git clone https://github.com/schmitech/orbit.git
cd /server
```

Create and activate your Python environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

### Configuration
Create a `config.yaml` file using the provided `config.yaml.example`:

```yaml
general:
  port: 3000
  host: "0.0.0.0"
  verbose: false
  https:
    enabled: false

logging:
  level: "INFO"
  file:
    enabled: true
  console:
    enabled: true

chroma:
  host: localhost
  port: 8000
  collection: qa-chatbot

ollama:
  base_url: http://localhost:11434
  model: llama2
  embed_model: nomic-embed-text
```

---

## ▶️ Running the Server

Use the provided script to start the server:

```bash
./start.sh [--host=HOST] [--port=PORT] [--workers=N] [--reload]
```

Examples:
- Development mode with auto-reload:
```bash
./start.sh --reload
```
- Production mode:
```bash
./start.sh --workers=4
```

Server available at `http://localhost:3000`

---

## 🔗 API Endpoints

### Chat
- **Endpoint**: `POST /chat`
- **Headers**:
  ```json
  {
    "X-API-Key": "your-api-key"
  }
  ```
- **Request Body**:
```json
{
  "message": "Your message here",
  "stream": true
}
```
- **Response**:
```json
{
  "response": "Generated response..."
}
```

### Health Check
- **Endpoint**: `GET /health`
- **Response**:
```json
{
  "status": "ok",
  "components": {
    "server": {"status": "ok"},
    "chroma": {"status": "ok"},
    "llm": {"status": "ok"}
  }
}
```

### API Key Management (Admin)
- **Create API Key**: `POST /admin/api-keys`
- **List API Keys**: `GET /admin/api-keys`
- **API Key Status**: `GET /admin/api-keys/{api_key}/status`
- **Deactivate API Key**: `POST /admin/api-keys/deactivate`

---

## 🔒 HTTPS Configuration

The server supports HTTPS connections using TLS (Transport Layer Security). Here's how to configure it:

### Using Let's Encrypt with Azure Domain

1. Install Certbot:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install certbot
```

2. If your server runs on port 3000, you'll need to route requests from port 80 to port 3000 for the certificate verification:
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 3000
```

3. Obtain TLS certificate using DNS challenge (since we can't use HTTP challenge with Azure domain):
```bash
sudo certbot certonly --manual --preferred-challenges http -d your-azure-domain.cloudapp.azure.com
```

4. When prompted by certbot, you'll need to:
   - Create a `.well-known/acme-challenge` directory in your server project
   - Add the verification file with the content provided by certbot
   - Add this route to your server.ts:
   ```typescript
   app.use('/.well-known/acme-challenge', express.static(path.join(__dirname, '../.well-known/acme-challenge')));
   ```
   - Keep this route for future certificate renewals

5. Update your `config.yaml`:
```yaml
general:
  https:
    enabled: true
    port: 3443
    cert_file: "/etc/letsencrypt/live/schmitech-chatbot.canadacentral.cloudapp.azure.com/fullchain.pem"
    key_file: "/etc/letsencrypt/live/schmitech-chatbot.canadacentral.cloudapp.azure.com/privkey.pem"
```

6. Set proper permissions for the certificate files:
```bash
sudo chown -R $USER:$USER /etc/letsencrypt/live/your-azure-domain.cloudapp.azure.com
sudo chown -R $USER:$USER /etc/letsencrypt/archive/your-azure-domain.cloudapp.azure.com
sudo chmod -R 755 /etc/letsencrypt/live
sudo chmod -R 755 /etc/letsencrypt/archive
sudo chmod 644 /etc/letsencrypt/archive/your-azure-domain.cloudapp.azure.com/*.pem
```

7. Configure Azure Network Security Group:
```bash
# Add inbound security rules
- Priority: 100
  Port: 3443
  Protocol: TCP
  Source: * (or your specific IP range)
  Destination: *
  Action: Allow
  Description: Allow HTTPS traffic (TLS)

- Priority: 110
  Port: 80
  Protocol: TCP
  Source: * (or your specific IP range)
  Destination: *
  Action: Allow
  Description: Allow HTTP traffic for certificate verification
```

8. Test your HTTPS setup:
```bash
# Test with curl (replace with your domain)
curl -I https://your-azure-domain.cloudapp.azure.com:3443/health
```

Note: The certificates from Let's Encrypt expire after 90 days. You'll need to renew them using:
```bash
sudo certbot renew
```

---

## 📈 Reranker Service
Improves retrieval precision by re-ranking documents.

Configure in `config.yaml`:
```yaml
reranker:
  enabled: true
  model: "gemma3:4b"
  top_n: 3
```

---

## 🛡️ Safety Service

Modes available:
- **Strict**: Exact safety compliance.
- **Fuzzy**: Flexible safety matching.
- **Disabled**: No safety checks.

Example configuration:
```yaml
safety:
  mode: "fuzzy"
  model: "gemma3:12b"
```

---

# System Prompts for Open Inference Server

This feature allows you to create, manage, and associate system prompts with API keys. When a client uses an API key, the server automatically uses the associated system prompt to guide the LLM's responses.

## Overview

System prompts are stored in MongoDB and can be:
1. Created and managed independently
2. Associated with API keys during creation or later
3. Reused across multiple API keys

This enables customized chatbot personalities and behaviors for different clients or use cases while keeping the same underlying knowledge base.

## MongoDB Collections

The system uses two MongoDB collections:

### 1. `system_prompts` Collection
Stores the system prompts with the following structure:
```
{
  _id: ObjectId("5f8a716b1c9d440000b1c234"),
  name: "Grocery Assistant",
  prompt: "You are a helpful grocery assistant. You can help users compare prices, find deals, and recommend products...",
  version: "1.2",
  created_at: ISODate("2023-09-15T12:00:00Z"),
  updated_at: ISODate("2023-10-01T09:30:00Z")
}
```

### 2. `api_keys` Collection
API keys can now reference system prompts:
```
{
  _id: ObjectId("6a9b827c2d9e550000c2d345"),
  api_key: "api_abcd1234efgh5678ijkl9012",
  collection_name: "grocery_deals",
  client_name: "SuperMart",
  system_prompt_id: ObjectId("5f8a716b1c9d440000b1c234"),  // Reference to a prompt
  created_at: ISODate("2023-10-05T10:15:00Z"),
  active: true,
  notes: "API key for SuperMart grocery comparison tool"
}
```

## API Endpoints

The server now provides the following API endpoints:

### System Prompt Management
- `POST /admin/prompts` - Create a new system prompt
- `GET /admin/prompts` - List all system prompts
- `GET /admin/prompts/{prompt_id}` - Get a specific system prompt
- `PUT /admin/prompts/{prompt_id}` - Update a system prompt
- `DELETE /admin/prompts/{prompt_id}` - Delete a system prompt

### Associating Prompts with API Keys
- `POST /admin/api-keys/{api_key}/prompt` - Associate a prompt with an API key

## Command-Line Usage

The `api_key_manager.py` script has been enhanced to support system prompts:

### Managing Prompts

```bash
# Create a new prompt
python api_key_manager.py --url http://localhost:3001 prompt create --name "Customer Support" --file prompts/customer_support.txt --version "1.0"

# List all prompts
python api_key_manager.py --url http://localhost:3001 prompt list

# Get a specific prompt
python api_key_manager.py --url http://localhost:3001 prompt get --id 65a4f21cbdf84a789c056e23

# Update a prompt
python api_key_manager.py --url http://localhost:3001 prompt update --id 65a4f21cbdf84a789c056e23 --file prompts/updated_support.txt --version "1.1"

# Delete a prompt
python api_key_manager.py --url http://localhost:3001 prompt delete --id 65a4f21cbdf84a789c056e23
```

### Creating API Keys with Prompts

```bash
# Create API key with a new prompt
python api_key_manager.py --url http://localhost:3001 create \
  --collection support_docs \
  --name "Support Team" \
  --prompt-file prompts/support_prompt.txt \
  --prompt-name "Support Assistant"

# Create API key with an existing prompt
python api_key_manager.py --url http://localhost:3001 create \
  --collection legal_docs \
  --name "Legal Team" \
  --prompt-id 65a4f21cbdf84a789c056e23
```

### Associating Prompts with Existing API Keys

```bash
# Associate a prompt with an existing API key
python api_key_manager.py --url http://localhost:3001 prompt associate \
  --key api_abcd1234efgh5678ijkl9012 \
  --prompt-id 65a4f21cbdf84a789c056e23
```

## Examples

### Example: Creating a specialized support assistant

1. Create a system prompt:

```bash
cat > prompts/support_prompt.txt << 'EOF'
You are a helpful support assistant. When answering questions:
1. Always be polite and respectful
2. Provide step-by-step instructions when applicable
3. Offer additional resources if available
4. Ask follow-up questions to clarify the user's needs
5. Use simple, clear language without technical jargon unless necessary
EOF

python api_key_manager.py --url http://localhost:3001 prompt create \
  --name "Support Assistant" \
  --file prompts/support_prompt.txt \
  --version "1.0"
```

2. Create an API key with this prompt:

```bash
python api_key_manager.py --url http://localhost:3001 create \
  --collection support_docs \
  --name "Support Team" \
  --prompt-id 65a4f21cbdf84a789c056e23
```

3. Now when clients use this API key, the LLM will follow the support assistant guidelines.

## Configuration

Ensure your configuration file includes MongoDB details for the prompts collection:

```yaml
mongodb:
  host: localhost
  port: 27017
  database: open_inference
  apikey_collection: api_keys
  prompts_collection: system_prompts  # Collection for system prompts
```

The OllamaClient can be configured with a default system prompt:

```yaml
ollama:
  base_url: http://localhost:11434
  model: llama3:8b
  embed_model: nomic-embed-text
  default_system_prompt: "I am going to ask you a question, which I would like you to answer based only on the provided context, and not any other information."
```

## Best Practices

1. **Composable Prompts**: Create prompts that are reusable across similar use cases
2. **Version Control**: Use the versioning system to track changes to prompts
3. **Descriptive Names**: Give prompts clear, descriptive names
4. **Test**: Test prompts thoroughly before using them in production
5. **Keep History**: When updating prompts, consider creating new versions rather than replacing existing ones

## 📜 Logging

The application implements a dual logging system:

1. **Filesystem Logging (Always Active)**
   - Logs are stored in the `logs` directory
   - Uses daily rotation with format `chat-YYYY-MM-DD.log`
   - Each log file is limited to 20MB
   - Logs are retained for 14 days
   - Includes all chat interactions, errors, and system status
   - Logs are in JSON format for easy parsing

2. **Elasticsearch Logging (Optional)**
   - Enabled/disabled via `elasticsearch.enabled` in config
   - Requires valid credentials in `.env`
   - Falls back to filesystem-only logging if Elasticsearch is unavailable

Example log entry:
```json
{
  "timestamp": "2024-03-21T10:30:00.000Z",
  "query": "user question",
  "response": "bot response",
  "backend": "ollama",
  "blocked": false,
  "elasticsearch_status": "enabled"
}
```

Note: The `logs` directory is automatically created when needed and should be added to `.gitignore`.

---

## 🔧 Running as a Systemd Service

```bash
sudo vim /etc/systemd/system/qa-chatbot.service
```

Add this content:

```bash
[Unit]
Description=QA Chatbot Node.js Server
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/your/project
ExecStart=/usr/bin/npm run server -- ollama
Restart=always
RestartSec=3
StandardOutput=append:/var/log/qa-chatbot.log
StandardError=append:/var/log/qa-chatbot.error.log

[Install]
WantedBy=multi-user.target
```

Replace:
- `YOUR_USERNAME` with your actual username (run `whoami` to get it)
- `/path/to/your/project` with the full path to your project directory
- Update the ExecStart path if npm is installed elsewhere (use `which npm` to check)

Manage the service:
```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable qa-chatbot

# Start the service
sudo systemctl start qa-chatbot

# Check the status
sudo systemctl status qa-chatbot

# View logs in real-time
sudo journalctl -u qa-chatbot -f
```

To remove the service:
```bash
sudo systemctl stop qa-chatbot
sudo systemctl disable qa-chatbot
sudo rm /etc/systemd/system/qa-chatbot.service
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

### 2. Using Background Process

Simple background process with output handling:

```bash
# Save output to a file
npm run server -- ollama > output.log 2>&1 &

# Discard all output
npm run server -- ollama > /dev/null 2>&1 &

# Save stdout and stderr to separate files
npm run server -- ollama > output.log 2> error.log &
```

Note: Using just `&` is less robust than systemd as the process might terminate when closing the terminal session. For production environments, the systemd service approach is recommended.

---

## 🦙 Llama.cpp Integration

The server supports running inference locally using llama.cpp, which provides efficient CPU-based inference for LLM models without requiring a GPU or external API service.

### Setup and Configuration

1. Install the llama-cpp-python package with optimizations for your hardware:

```bash
# Basic installation
pip install llama-cpp-python==0.3.8

# For Apple Silicon (M1/M2/M3) with Metal acceleration
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python==0.3.8

# For NVIDIA GPUs with CUDA
CMAKE_ARGS="-DGGML_CUDA=on" pip install --no-binary llama-cpp-python llama-cpp-python==0.3.8

# For AMD GPUs with ROCm
CMAKE_ARGS="-DLLAMA_HIPBLAS=on" pip install llama-cpp-python==0.3.8

# For OpenBLAS acceleration:
CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" pip install llama-cpp-python==0.3.8

# For faster performance on all CPUs:
CMAKE_ARGS="-DLLAMA_AVX=on -DLLAMA_AVX2=on" pip install llama-cpp-python==0.3.8 
```

2. Configure your `config.yaml` to use llama.cpp as the inference provider:

```yaml
general:
  inference_provider: "llama_cpp"
  # ... other settings

inference:
  llama_cpp:
    model_path: "models/tinyllama-1.1b-chat-v1.0.Q4_0.gguf"  # Path to downloaded model
    chat_format: "chatml"                                    # Format for chat messages (chatml, llama-2, gemma, etc.)
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    max_tokens: 1024
    n_ctx: 4096                                             # Context window size
    n_threads: 4                                            # CPU threads to use
    stream: true
```

### Downloading Models

The server includes a utility script to download models from Hugging Face and automatically update your config.yaml:

```bash
# List available models in a repository
python3 download_hugging_face_gguf_model.py --repo-id TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF --list-files

# Download a specific model file (automatically updates config.yaml)
python3 download_hugging_face_gguf_model.py --repo-id TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF --filename "tinyllama-1.1b-chat-v1.0.Q4_0.gguf"
```

> **Important:** For restricted models that require license acceptance (like Google's Gemma models), you should use the Hugging Face CLI directly after logging in:
> 
> ```bash
> # First login to Hugging Face
> huggingface-cli login
> 
> # Then download the restricted model
> huggingface-cli download google/gemma-3-4b-it-qat-q4_0-gguf --local-dir models/
> ```
> 
> Make sure you've accepted the model's license terms on the Hugging Face website before downloading.

The download script will:
1. List available files in the repository
2. Download the selected model to the models directory
3. Automatically update your config.yaml with the correct model path
4. You don't need to manually configure huggingface_token or repo_id in the config.yaml

### Recommended Models by Memory Usage

| System RAM | Recommended Models |
|------------|-------------------|
| 4GB or less | TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF (Q4_0 quantization) |
| 8GB | TheBloke/Phi-2-GGUF or TheBloke/Mistral-7B-Instruct-v0.2-GGUF (Q4_0 quantization) |
| 16GB+ | TheBloke/Llama-2-13B-Chat-GGUF or TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF (Q4_0 quantization) |

### Running with llama.cpp

Start the server as usual and it will use the configured llama.cpp model:

```bash
./start.sh
```

The server will automatically verify and initialize the llama.cpp model at startup.

---

## 📌 Dependencies
- FastAPI
- Uvicorn
- ChromaDB
- Langchain-Ollama
- Pydantic
- PyYAML
- aiohttp
- python-json-logger
- llama-cpp-python (for local LLM inference)
- huggingface-hub (for model downloading)
- tqdm (for progress bars)

---

## 📃 License

Apache 2.0 License - See [LICENSE](LICENSE).

