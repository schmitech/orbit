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
cd /backend/server
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

## 📌 Dependencies
- FastAPI
- Uvicorn
- ChromaDB
- Langchain-Ollama
- Pydantic
- PyYAML
- aiohttp
- python-json-logger

---

## 📃 License

Apache 2.0 License - See [LICENSE](LICENSE).

