# 🚀 ORBIT Server

## 🛠️ Installation

Follow the main installation guide in the project root:

```bash
# Download and extract the latest release
curl -L https://github.com/schmitech/orbit/releases/download/v1.2.0/orbit-1.2.0.tar.gz -o orbit-1.2.0.tar.gz
tar -xzf orbit-1.2.0.tar.gz
cd orbit-1.2.0

# Activate virtual environment
source venv/bin/activate

# Install ORBIT
./install.sh
```

---

## ▶️ Server Management

ORBIT uses a unified CLI tool for all server management operations. The `orbit` command provides server control, API key management, user management, system prompt management, and configuration management.

### Starting the Server

```bash
# Basic start (uses default config.yaml)
./bin/orbit.sh start

# Start with specific configuration
./bin/orbit.sh start --config config.yaml

# Start with custom host and port
./bin/orbit.sh start --host 0.0.0.0 --port 8000

# Development mode with auto-reload
./bin/orbit.sh start --reload

# Start and clear previous logs
./bin/orbit.sh start --delete-logs
```

### Stopping the Server

```bash
# Graceful stop
./bin/orbit.sh stop

# Stop with custom timeout
./bin/orbit.sh stop --timeout 60

# Stop and delete logs
./bin/orbit.sh stop --delete-logs

# Force stop without graceful shutdown
./bin/orbit.sh stop --force
```

### Restarting the Server

```bash
# Basic restart
./bin/orbit.sh restart

# Restart with new configuration
./bin/orbit.sh restart --config new-config.yaml

# Restart and clear logs
./bin/orbit.sh restart --delete-logs
```

### Checking Server Status

```bash
# Get detailed server status
./bin/orbit.sh status

# Continuously monitor status
./bin/orbit.sh status --watch

# Monitor with custom interval (seconds)
./bin/orbit.sh status --watch --interval 10
```

Example status output:
```json
{
  "status": "running",
  "pid": 12345,
  "uptime": 3600.5,
  "memory_mb": 245.8,
  "cpu_percent": 2.1,
  "message": "Server is running with PID 12345"
}
```

---

## 🔐 Authentication & User Management

### Login and Authentication

```bash
# Login with username and password
./bin/orbit.sh login --username admin --password secret

# Login with interactive prompts
./bin/orbit.sh login

# Login without saving credentials
./bin/orbit.sh login --no-save

# Check authentication status
./bin/orbit.sh auth-status

# Logout and clear credentials
./bin/orbit.sh logout

# Logout from all sessions
./bin/orbit.sh logout --all

# Show current user information
./bin/orbit.sh me
```

### User Registration (Admin Only)

```bash
# Register a new user
./bin/orbit.sh register --username newuser --password secret

# Register with specific role
./bin/orbit.sh register --username admin2 --password secret --role admin

# Register with email
./bin/orbit.sh register --username user1 --password secret --email user1@example.com
```

### User Management (Admin Only)

```bash
# List all users
./bin/orbit.sh user list

# List users with filtering
./bin/orbit.sh user list --role admin --active-only --limit 50

# Reset user password
./bin/orbit.sh user reset-password --user-id 12345 --password newpass

# Reset password by username
./bin/orbit.sh user reset-password --username john --password newpass

# Delete a user
./bin/orbit.sh user delete --user-id 12345

# Delete user without confirmation
./bin/orbit.sh user delete --user-id 12345 --force

# Deactivate a user
./bin/orbit.sh user deactivate --user-id 12345

# Activate a user
./bin/orbit.sh user activate --user-id 12345

# Change your own password
./bin/orbit.sh user change-password --current-password old --new-password new
```

---

## 🔑 API Key Management

The orbit CLI provides comprehensive API key management with adapter support:

### Creating API Keys

```bash
# Basic API key creation with adapter
./bin/orbit.sh key create --adapter docs --name "Customer Support"

# Create with notes
./bin/orbit.sh key create --adapter legal --name "Legal Team" --notes "Internal legal document access"

# Create with system prompt from file
./bin/orbit.sh key create --adapter support --name "Support Bot" \
  --prompt-file prompts/support.txt --prompt-name "Support Assistant"

# Create with existing prompt
./bin/orbit.sh key create --adapter sales --name "Sales Team" --prompt-id 612a4b3c78e9f25d3e1f42a7
```

### Managing API Keys

```bash
# List all API keys
./bin/orbit.sh key list

# List with filtering and pagination
./bin/orbit.sh key list --active-only --limit 50 --offset 0

# List in JSON format
./bin/orbit.sh key list --output json

# Check API key status
./bin/orbit.sh key status --key orbit_abcd1234

# Test an API key
./bin/orbit.sh key test --key orbit_abcd1234

# Deactivate an API key
./bin/orbit.sh key deactivate --key orbit_abcd1234

# Delete an API key
./bin/orbit.sh key delete --key orbit_abcd1234

# Delete without confirmation
./bin/orbit.sh key delete --key orbit_abcd1234 --force

# List available adapters
./bin/orbit.sh key list-adapters
```

---

## 📝 System Prompt Management

Manage system prompts that define AI behavior:

### Creating and Managing Prompts

```bash
# Create a new system prompt
./bin/orbit.sh prompt create --name "Customer Support" --file prompts/support.txt --version "1.0"

# List all prompts
./bin/orbit.sh prompt list

# List with filtering
./bin/orbit.sh prompt list --name-filter "support" --limit 50

# Get specific prompt details
./bin/orbit.sh prompt get --id 612a4b3c78e9f25d3e1f42a7

# Save prompt to file
./bin/orbit.sh prompt get --id 612a4b3c78e9f25d3e1f42a7 --save prompt.txt

# Update an existing prompt
./bin/orbit.sh prompt update --id 612a4b3c78e9f25d3e1f42a7 --file prompts/updated_support.txt --version "1.1"

# Delete a prompt
./bin/orbit.sh prompt delete --id 612a4b3c78e9f25d3e1f42a7

# Delete without confirmation
./bin/orbit.sh prompt delete --id 612a4b3c78e9f25d3e1f42a7 --force

# Associate a prompt with an API key
./bin/orbit.sh prompt associate --key orbit_abcd1234 --prompt-id 612a4b3c78e9f25d3e1f42a7
```

---

## ⚙️ Configuration Management

The CLI provides comprehensive configuration management:

### Viewing Configuration

```bash
# Show current configuration
./bin/orbit.sh config show

# Show specific configuration key
./bin/orbit.sh config show --key server_url

# Show effective configuration (CLI vs server config)
./bin/orbit.sh config effective

# Show only configuration sources
./bin/orbit.sh config effective --sources-only

# Show specific effective configuration key
./bin/orbit.sh config effective --key timeout
```

### Modifying Configuration

```bash
# Set a configuration value
./bin/orbit.sh config set server_url http://localhost:3000

# Set nested configuration
./bin/orbit.sh config set auth.storage_method keychain

# Reset configuration to defaults
./bin/orbit.sh config reset
```

### Global CLI Options

```bash
# Use specific server URL
./bin/orbit.sh --server-url http://remote-server:3000 status

# Use specific configuration file
./bin/orbit.sh --config custom-config.yaml start

# Enable verbose output
./bin/orbit.sh -v key list

# Set output format
./bin/orbit.sh --output json key list

# Disable colored output
./bin/orbit.sh --no-color key list

# Specify log file
./bin/orbit.sh --log-file orbit.log start
```

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

### MCP Protocol Chat
- **Endpoint**: `POST /v1/chat`
- **Headers**:
  ```json
  {
    "X-API-Key": "your-api-key"
  }
  ```
- **Request Body**:
```json
{
  "messages": [
    {
      "id": "msg_1234567890",
      "object": "thread.message",
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Your message here"
        }
      ],
      "created_at": 1683753347
    }
  ],
  "stream": true
}
```
- **Response**:
```json
{
  "id": "resp_1234567890",
  "object": "thread.message",
  "created_at": 1683753348,
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Generated response..."
    }
  ]
}
```
- **See documentation**: [MCP Protocol](mcp_protocol.md)

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

### User Management (Admin)
- **List Users**: `GET /admin/users`
- **Register User**: `POST /admin/users`
- **Reset Password**: `POST /admin/users/{user_id}/reset-password`
- **Delete User**: `DELETE /admin/users/{user_id}`
- **Deactivate User**: `POST /admin/users/{user_id}/deactivate`
- **Activate User**: `POST /admin/users/{user_id}/activate`

### System Prompt Management (Admin)
- **Create Prompt**: `POST /admin/prompts`
- **List Prompts**: `GET /admin/prompts`
- **Get Prompt**: `GET /admin/prompts/{prompt_id}`
- **Update Prompt**: `PUT /admin/prompts/{prompt_id}`
- **Delete Prompt**: `DELETE /admin/prompts/{prompt_id}`
- **Associate with API Key**: `POST /admin/api-keys/{api_key}/prompt`

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

The ORBIT CLI provides comprehensive system prompt management:

### Managing Prompts

```bash
# Create a new prompt
./bin/orbit.sh prompt create --name "Customer Support" --file prompts/customer_support.txt --version "1.0"

# List all prompts
./bin/orbit.sh prompt list

# Get a specific prompt
./bin/orbit.sh prompt get --id 65a4f21cbdf84a789c056e23

# Update a prompt
./bin/orbit.sh prompt update --id 65a4f21cbdf84a789c056e23 --file prompts/updated_support.txt --version "1.1"

# Delete a prompt
./bin/orbit.sh prompt delete --id 65a4f21cbdf84a789c056e23
```

### Creating API Keys with Prompts

```bash
# Create API key with a new prompt
./bin/orbit.sh key create \
  --adapter support_docs \
  --name "Support Team" \
  --prompt-file prompts/support_prompt.txt \
  --prompt-name "Support Assistant"

# Create API key with an existing prompt
./bin/orbit.sh key create \
  --adapter legal_docs \
  --name "Legal Team" \
  --prompt-id 65a4f21cbdf84a789c056e23
```

### Associating Prompts with Existing API Keys

```bash
# Associate a prompt with an existing API key
./bin/orbit.sh prompt associate \
  --key orbit_abcd1234efgh5678ijkl9012 \
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

./bin/orbit.sh prompt create \
  --name "Support Assistant" \
  --file prompts/support_prompt.txt \
  --version "1.0"
```

2. Create an API key with this prompt:

```bash
./bin/orbit.sh key create \
  --adapter support_docs \
  --name "Support Team" \
  --prompt-id 65a4f21cbdf84a789c056e23
```

3. Now when clients use this API key, the LLM will follow the support assistant guidelines.

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

## 🔧 Production Deployment

For production environments, you can use the orbit CLI with process management tools:

### Using systemd

Create a systemd service file:

```bash
sudo vim /etc/systemd/system/orbit-server.service
```

Add this content:

```ini
[Unit]
Description=ORBIT AI Server
After=network.target

[Service]
Type=forking
User=YOUR_USERNAME
WorkingDirectory=/path/to/orbit
ExecStart=/path/to/orbit/bin/orbit.sh start --config config.yaml
ExecStop=/path/to/orbit/bin/orbit.sh stop
ExecReload=/path/to/orbit/bin/orbit.sh restart
Restart=always
RestartSec=3
StandardOutput=append:/var/log/orbit.log
StandardError=append:/var/log/orbit.error.log

[Install]
WantedBy=multi-user.target
```

Replace:
- `YOUR_USERNAME` with your actual username
- `/path/to/orbit` with the full path to your ORBIT installation

Manage the service:
```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable orbit-server

# Start the service
sudo systemctl start orbit-server

# Check status
sudo systemctl status orbit-server

# View logs
sudo journalctl -u orbit-server -f
```

### Using Docker

See [Docker Deployment](docker-deployment.md) for containerized deployment options.

### Background Process

For simple background deployment:

```bash
# Start in background with output logging
nohup ./bin/orbit.sh start > orbit.log 2>&1 &

# Check if running
./bin/orbit.sh status
```

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
 
```bash
# First login to Hugging Face
huggingface-cli login
 
# Then download the restricted model
huggingface-cli download google/gemma-3-4b-it-qat-q4_0-gguf --local-dir gguf
```
 
Make sure you've accepted the model's license terms on the Hugging Face website before downloading.


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

