# Tutorial: Chat with Your Data

This tutorial walks you through connecting ORBIT to a database so you can query it using natural language. ORBIT connects to your databases, vector stores, and APIs so you can query them with natural language.

<div align="center">
  <video src="https://github.com/user-attachments/assets/68190983-d996-458f-8024-c9c15272d1c3" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Querying an HR database through natural language.</i>
</div>

## Prerequisites

- ORBIT installed via [release download](../README.md#option-2-download-latest-release) or [git clone](../README.md#option-3-clone-from-git-development)
- Python environment activated (`source venv/bin/activate`)
- ORBIT server running (`./bin/orbit.sh start`)

> **Note:** The basic Docker image (`schmitech/orbit:basic`) does not include database adapters. Use the release or git install for this tutorial.

---

## Quick Setup (SQLite Example)

This example uses a local SQLite database with sample HR/employee data.

### 1. Generate Test Data

```bash
python utils/sql-intent-template/examples/sqlite/hr/generate_hr_data.py \
  --records 100 \
  --output utils/sql-intent-template/examples/sqlite/hr/hr.db
```

### 2. Restart ORBIT

Restart the server to load the pre-generated SQL templates:

```bash
./bin/orbit.sh restart
```

### 3. Create an API Key

Create an API key configured for the SQLite HR adapter:

```bash
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-hr \
  --name "HR Chatbot" \
  --prompt-file ./examples/prompts/hr-assistant-prompt.txt \
  --prompt-name "HR Assistant"
```

Save the API key from the output (starts with `orbit_`).

### 4. Start Chatting

Use the React chat app to query your database:

```bash
npm install -g orbitchat
orbitchat --api-url http://localhost:3000 --api-key YOUR_API_KEY --open
```

Try questions like:
- "How many employees per department?"
- "What's the average salary per department?"
- "Show me employees hired in the last 30 days"
- "Which departments are over budget on payroll?"

<div align="center">
  <video src="https://github.com/user-attachments/assets/68190983-d996-458f-8024-c9c15272d1c3" controls>
    Your browser does not support the video tag.
  </video>
  <br/>
  <i>Querying an HR database using natural language.</i>
</div>

---

## How It Works

The `intent-sql-sqlite-hr` adapter uses pre-generated SQL templates that map natural language intents to SQL queries. When you ask a question:

1. ORBIT classifies your intent (e.g., "employee count", "salary by department")
2. Selects the appropriate SQL template
3. Executes the query against your database
4. Returns results in natural language

---

## Creating an API Key

API keys control access to ORBIT and define which adapter and system prompt to use. Here's how to create them.

### Using Docker

```bash
# Login as admin (default password: admin123)
docker exec -it orbit-basic python /orbit/bin/orbit.py login --username admin --password admin123

# Create an API key with a custom prompt
docker exec -it orbit-basic python /orbit/bin/orbit.py key create \
  --adapter simple-chat \
  --name "My Chat Key" \
  --prompt-name "My HR Assistant" \
  --prompt-text "You are a helpful HR assistant. Be concise and friendly."
```

### Using CLI (Release/Git Install)

```bash
# Login as admin
./bin/orbit.sh login --username admin --password admin123

# Create an API key
./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "My Chat Key" \
  --prompt-name "My Assistant" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."
```

### Output

The command outputs your API key (starts with `orbit_`):

```
✓ API key created successfully
API Key: orbit_abc123XYZ...
Client: My Chat Key
Adapter: simple-chat
Prompt ID: 12345-abcdefg
```

Save this key—you'll need it to authenticate with ORBIT.

### Key Options

| Option | Description |
|--------|-------------|
| `--adapter` | Which adapter to use (e.g., `simple-chat`, `intent-sql-sqlite-hr` for HR) |
| `--name` | A friendly name for this key |
| `--prompt-text` | Inline system prompt |
| `--prompt-file` | Load system prompt from a file |
| `--prompt-name` | Name for the prompt configuration |

For more details, see the [API Keys Guide](api-keys.md) and [Authentication Guide](authentication.md).

---

## Connecting Your Own Database

The example above uses pre-generated templates. To connect your own database:

1. **Generate templates** from your database schema using the SQL Intent Template utility
2. **Configure an adapter** in `config/adapters.yaml`
3. **Create an API key** for your new adapter

See the detailed guides:
- [SQL Intent Template README](../utils/sql-intent-template/README.md)
- [SQL Intent Template Tutorial](../utils/sql-intent-template/docs/tutorial.md)

---

## Next Steps

- [Configuration Guide](configuration.md) – Customize ORBIT settings
- [Adapters Guide](adapters.md) – Learn about different adapter types
- [Authentication Guide](authentication.md) – Set up API key management
