# 🚀 ORBIT Server

## 🛠️ Installation

Follow the main installation guide in the project root:

```bash
# Download and extract the latest release
curl -L https://github.com/schmitech/orbit/releases/download/v2.10.1/orbit-2.10.1.tar.gz -o orbit-2.10.1.tar.gz
tar -xzf orbit-2.10.1.tar.gz
cd orbit-2.10.1

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

### API Documentation
- **Swagger UI**: `GET /docs`
- **ReDoc**: `GET /redoc`
- **OpenAPI Schema**: `GET /openapi.json`

These endpoints are enabled by default in development. Set `ENVIRONMENT=production` to disable all three autogenerated FastAPI docs endpoints in production deployments.

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

### Message Queue (Async) Protocol

In addition to the synchronous HTTP surfaces (REST, OpenAI-compatible, A2A, MCP), ORBIT can run as a **message-queue consumer** for decoupled, batch-style workloads. Instead of making a blocking HTTP call, a client **publishes a request message** to a broker queue; ORBIT consumes it, runs it through the same inference pipeline, and **publishes a response envelope** back to the message's `reply_to` (correlated by `correlation_id`).

This surface is **disabled by default** and requires the optional messaging dependency profile:

```bash
./install/setup.sh --profile messaging   # installs aio-pika (RabbitMQ client)
```

> **Note:** The MQ path bypasses the HTTP middleware stack (CORS, rate limiting, audit, security headers). Authentication is enforced by the consumer itself — a valid ORBIT API key (in the message body or an AMQP header) is required whenever the API-key service is active, exactly as on the HTTP surfaces.

#### Configuration (`config.yaml`)

```yaml
messaging:
  enabled: false                # master switch
  provider: "rabbitmq"          # rabbitmq
  run_in_server: false          # true = consumer runs inside the server process;
                                # false = run it via the standalone `orbit worker` command
  rabbitmq:
    url: ${MESSAGING_RABBITMQ_URL}      # amqp://user:pass@host:5672/vhost
    requests_queue: "orbit.requests"    # queue ORBIT consumes requests from
    results_queue: "orbit.results"      # default reply target when a message has no reply_to
    dead_letter_queue: "orbit.dlq"      # unparseable/failed deliveries land here
    prefetch: 8                         # max unacked messages in flight (backpressure)
    durable: true
```

#### Running the consumer

Choose **one** of these (running both against the same queue would double-consume):

**A. Standalone worker (recommended; scale/deploy independently of the web server).**
The `orbit worker` command has a managed, PID-file-based lifecycle mirroring the server:

```bash
# Start in the background (writes logs/worker.pid, logs to logs/worker.log)
./bin/orbit.sh worker start --config config.yaml

# Check status / stop / restart
./bin/orbit.sh worker status
./bin/orbit.sh worker restart --config config.yaml
./bin/orbit.sh worker stop            # graceful (SIGTERM); add --force for SIGKILL

# Run in the foreground instead (blocks; for dev, or when a supervisor like
# systemd/Docker manages the process lifecycle itself)
./bin/orbit.sh worker run --config config.yaml
```

Options: `worker start --delete-logs`, `worker stop --timeout <s> --force --delete-logs`.
Run several `worker start` invocations across hosts to scale throughput — RabbitMQ
distributes messages across all consumers (bounded per worker by `prefetch`).

For production supervision, run the worker in the foreground under systemd (it
handles daemonization, restart, and logging):

```ini
[Unit]
Description=ORBIT MQ Worker
After=network.target

[Service]
WorkingDirectory=/path/to/orbit
ExecStart=/path/to/orbit/bin/orbit.sh worker run --config config.yaml
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**B. In-process.** Set `messaging.run_in_server: true` and start the server normally;
the consumer runs inside the server process (simplest, but shares the event loop with
live HTTP traffic, and with `performance.workers > 1` every worker process starts its
own consumer):

```bash
./bin/orbit.sh start
```

#### Message contract

**Request** (JSON body published to `orbit.requests`):
```json
{
  "id": "client-supplied-id",
  "message": "Your message here",
  "api_key": "orbit_abcd1234",
  "adapter": "optional-adapter-override",
  "session_id": "optional-session-id",
  "metadata": {}
}
```
The API key may instead be supplied as an AMQP header (`x-api-key`). Set the AMQP `reply_to` and `correlation_id` properties so ORBIT can route and correlate the response.

**Response envelope** (published to the message's `reply_to`, or `results_queue` as a fallback, with the same `correlation_id`):
```json
{
  "id": "client-supplied-id",
  "status": "completed",
  "response": "Generated response...",
  "sources": [],
  "error": null,
  "metadata": {}
}
```
Business-level failures (missing/invalid API key, empty message, pipeline error) return an envelope with `"status": "failed"` and a populated `error` — the client always gets an answer. Only **unparseable messages** and **unexpected exceptions** are rejected (no requeue) and routed to the **dead-letter queue** for operational inspection/retry.

#### Minimal client example (aio-pika)

```python
import asyncio, json, uuid, aio_pika

async def main():
    conn = await aio_pika.connect_robust("amqp://guest:guest@localhost:5672/")
    channel = await conn.channel()
    replies = await channel.declare_queue(exclusive=True)   # temporary reply queue

    corr_id = str(uuid.uuid4())
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps({"id": corr_id, "message": "Hello", "api_key": "orbit_abcd1234"}).encode(),
            correlation_id=corr_id,
            reply_to=replies.name,
            content_type="application/json",
        ),
        routing_key="orbit.requests",
    )

    async with replies.iterator() as it:
        async for msg in it:
            if msg.correlation_id == corr_id:
                async with msg.process():
                    print(json.loads(msg.body))
                break
    await conn.close()

asyncio.run(main())
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

ORBIT serves HTTPS natively via uvicorn. When enabled, the server binds exclusively on the TLS port (default 3443) using TLS 1.2+ with forward-secrecy cipher suites. TLS 1.0 and 1.1 are not negotiated.

### Configuration Reference

All HTTPS options live under `general.https` in `config.yaml`:

```yaml
general:
  https:
    enabled: true
    port: 3443                  # TLS listener port (HTTP port is not opened when HTTPS is on)
    cert_file: "/path/to/fullchain.pem"
    key_file: "/path/to/privkey.pem"
    key_password: ${ORBIT_TLS_KEY_PASSWORD}  # optional: passphrase for encrypted private key
```

`key_password` is optional and only needed when the private key is passphrase-protected. Set it via the `ORBIT_TLS_KEY_PASSWORD` environment variable rather than storing it in the config file.

### Startup Validation

Before the server accepts any connections, ORBIT validates the TLS configuration:

- Checks that `cert_file` and `key_file` exist and are readable.
- Loads the cert and key together to confirm they are a matched pair (a mismatched pair is rejected immediately with a clear error).
- If the `cryptography` package is installed, checks the certificate expiry date — an expired cert raises an error; a cert expiring within 30 days logs a warning.

A misconfigured certificate produces a descriptive error at startup rather than an opaque SSL failure at connection time.

### Security Headers

When HTTPS is enabled, ORBIT includes the `Strict-Transport-Security` (HSTS) header on all responses, instructing browsers to always use HTTPS for the domain. This header is suppressed when running in plain HTTP mode, as browsers ignore HSTS delivered over unencrypted connections (RFC 6797).

### HTTP → HTTPS Redirect

ORBIT does not open a second HTTP listener for redirects. HTTP-to-HTTPS redirection should be handled by a reverse proxy (nginx, Caddy, HAProxy) sitting in front of ORBIT. This is the recommended production topology regardless, as a reverse proxy handles TLS termination, load balancing, and rate limiting at the edge.

**nginx example** (`/etc/nginx/sites-available/orbit`):

```nginx
server {
    listen 80;
    server_name your-domain.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.example.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Alternatively, if you prefer ORBIT to terminate TLS directly (without nginx), simply leave port 80 closed — clients connecting to HTTP will get a connection refused rather than a redirect.

### Obtaining a Certificate with Let's Encrypt

1. Install Certbot:
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install certbot python3-certbot-nginx
```

2. Issue a certificate (HTTP challenge, requires port 80 to be reachable):
```bash
sudo certbot certonly --standalone -d your-domain.example.com
```

   For domains where port 80 is blocked, use the DNS challenge instead:
```bash
sudo certbot certonly --manual --preferred-challenges dns -d your-domain.example.com
```

3. Update `config.yaml`:
```yaml
general:
  https:
    enabled: true
    port: 3443
    cert_file: "/etc/letsencrypt/live/your-domain.example.com/fullchain.pem"
    key_file: "/etc/letsencrypt/live/your-domain.example.com/privkey.pem"
```

4. Set file permissions so the ORBIT process can read the certificates:
```bash
sudo chown -R $USER:$USER /etc/letsencrypt/live/your-domain.example.com
sudo chown -R $USER:$USER /etc/letsencrypt/archive/your-domain.example.com
sudo chmod -R 755 /etc/letsencrypt/live /etc/letsencrypt/archive
sudo chmod 644 /etc/letsencrypt/archive/your-domain.example.com/*.pem
```

5. Test the HTTPS endpoint:
```bash
curl -I https://your-domain.example.com:3443/health
```

Let's Encrypt certificates expire after 90 days. Renew them with:
```bash
sudo certbot renew
```

Consider adding a cron job or systemd timer to run `certbot renew` automatically (e.g. twice daily).

### Using Let's Encrypt with Azure

If your domain is an Azure-managed domain (`*.cloudapp.azure.com`), the DNS challenge is required since Azure manages the domain's DNS zone. See [Azure DNS challenge documentation](https://certbot-dns-azure.readthedocs.io/) for the Azure DNS plugin setup.

After obtaining the certificate, open the HTTPS port in your Azure Network Security Group:

```
Priority: 100 | Port: 3443 | Protocol: TCP | Action: Allow  (HTTPS)
Priority: 110 | Port: 80   | Protocol: TCP | Action: Allow  (HTTP — only needed during cert issuance)
```

---

# System Prompts

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

### Benign gRPC Fork Warnings with `workers > 1`

When `performance.workers` in `config.yaml` is set above `1`, you may occasionally see log lines like this at startup:

```
WARNING: All log messages before absl::InitializeLog() is called are written to STDERR
I0000 00:00:1783186897.127984  432192 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
```

**Cause**: ORBIT builds the full FastAPI app (including any Gemini or gRPC-backed vector store clients such as Milvus, Qdrant, or Weaviate) once in the main process before uvicorn spawns its worker pool. Uvicorn's "spawn" worker mode is implemented on POSIX via `fork()` followed by `exec()`. If a gRPC client has already started its background threads in the main process by the time the workers are forked, gRPC's fork-safety handlers print this diagnostic once per worker spawned. It depends on init/request timing, so it doesn't happen on every startup.

**Impact**: None — each worker process fully re-initializes after `exec()`, so there's no shared or corrupted gRPC state. This is log noise, not an error.

**To silence it**: Set `performance.workers: 1` in `config.yaml`, or run multiple independent ORBIT processes behind a reverse proxy/load balancer instead of using uvicorn's built-in multi-worker mode.

---

## 🔧 Production Deployment

For production environments, you can use the orbit CLI with process management tools:

Set `ENVIRONMENT=production` in your runtime environment or `.env` file for production deployments. This disables the autogenerated FastAPI documentation endpoints `/docs`, `/redoc`, and `/openapi.json`.

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
Environment=ENVIRONMENT=production
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
hf login
 
# Then download the restricted model
hf download google/gemma-3-4b-it-qat-q4_0-gguf --local-dir gguf
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

## ⚡ Performance Optimizations

ORBIT includes several performance optimizations to improve response times and reduce bandwidth usage.

### ORJSON Fast JSON Serialization

ORBIT uses [orjson](https://github.com/ijl/orjson) as the default JSON serializer, providing 20-40% faster JSON serialization compared to the standard library.

This is enabled by default and requires no configuration.

### GZip Response Compression (Opt-in)

Large JSON responses can be compressed using GZip, typically reducing response sizes by 30-60%. This is **disabled by default** as it adds overhead that may not benefit chat-focused deployments.

**When to enable**: Deployments with large JSON responses on non-streaming endpoints (e.g., admin APIs returning large datasets).

**Important**: Streaming endpoints (`/v1/chat`, `/ws`, `/mcp`) are automatically excluded from compression to preserve word-by-word streaming behavior.

**Configuration** (`config.yaml`):
```yaml
performance:
  compression:
    enabled: true           # Set to true to enable
    minimum_size: 2048      # Only compress responses larger than this (bytes)
    excluded_paths:         # Paths excluded from compression (streaming)
      - "/v1/chat"          # SSE streaming endpoint
      - "/ws"               # WebSocket endpoints
      - "/mcp"              # MCP protocol endpoints
```

**Verification**:
```bash
# Check that compression is working on non-streaming endpoints
curl -H "Accept-Encoding: gzip" http://localhost:3000/health/adapters -v
# Look for "Content-Encoding: gzip" in response headers
```

### ETag Caching (Opt-in)

GET requests with JSON responses can include ETag headers for client-side caching. This is **disabled by default** as it's most useful for read-heavy REST APIs, not chat-focused deployments.

**When to enable**: Deployments where clients make repeated GET requests to the same endpoints and implement ETag caching.

**Configuration** (`config.yaml`):
```yaml
performance:
  etag_caching:
    enabled: true           # Set to true to enable
    excluded_paths:         # Paths to exclude from ETag processing
      - "/v1/chat"          # SSE streaming endpoint
      - "/ws"               # WebSocket endpoints
      - "/mcp"              # MCP protocol endpoints
```

**Verification**:
```bash
# First request - returns full response with ETag header
curl -v http://localhost:3000/health/adapters
# Note the ETag value (e.g., "abc123def456")

# Second request with If-None-Match - returns 304 if unchanged
curl -H 'If-None-Match: "abc123def456"' http://localhost:3000/health/adapters -v
# Should return 304 Not Modified
```

**Client Compatibility**: These optimizations are transparent to clients:
- GZip decompression is handled automatically by `fetch`, `httpx`, `requests`, and other HTTP clients
- ETag caching is opt-in for both server and clients
- JSON format remains unchanged - only serialization speed improves

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
- orjson (for fast JSON serialization)
- llama-cpp-python (for local LLM inference)
- huggingface-hub (for model downloading)
- tqdm (for progress bars)

---

## 📃 License

Apache 2.0 License - See [LICENSE](LICENSE).
