# Example 1: SQL Database (SQLite)

**Level 1 · Foundations**

This is the Intent adapter family from [Adapter Types](adapter-types.md) — one query template gets picked and its parameterized SQL run, rather than free-form SQL generation. Let's try the most common ORBIT pattern: asking questions in English against a real SQL database. We'll use a small local SQLite file with sample HR data.

### 1. Generate sample data

```bash
python examples/intent-templates/sql-intent-template/examples/sqlite/hr/generate_hr_data.py \
  --records 100 \
  --output examples/intent-templates/sql-intent-template/examples/sqlite/hr/hr.db
```

### 2. Restart ORBIT

ORBIT preloads intent templates at startup, so a restart picks them up:

```bash
./bin/orbit.sh restart
```

### 3. Create an API key for the HR adapter

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** using the text from `./examples/prompts/hr-assistant-prompt.txt`.

Then go to **API Keys** → **+ Create**:

1. Choose `intent-sql-sqlite-hr` as the adapter.
2. Name the key `HR Chatbot`.
3. Select the `HR Assistant` persona.
4. Save the key and copy the `orbit_…` value shown once.

<!-- MEDIA: screenshot | sql-database-sqlite/adapter-config | Adapters tab showing the intent-sql-sqlite-hr adapter's YAML in the Ace editor -->
> 🖼️ **Screenshot placeholder:** the `intent-sql-sqlite-hr` adapter config in the Adapters tab.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### 4. Test the query with `curl`

You can test the adapter directly through the chat API before starting a browser client. Replace `orbit_YOUR_KEY` with the key created above:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_YOUR_KEY' \
  -H 'X-Session-ID: hr-example' \
  -d '{
    "messages": [
      {"role": "user", "content": "How many employees per department?"}
    ],
    "stream": false
  }'
```

The response should contain the department counts returned by the parameterized SQL template.

### 5. Start chatting

```bash
ORBIT_ADAPTER_KEYS='{"intent-sql-sqlite-hr":"orbit_YOUR_KEY"}' orbitchat --open
```

Try:

- "How many employees per department?"
- "What's the average salary per department?"
- "Show me employees hired in the last 30 days"
- "Which departments are over budget on payroll?"

### What's happening under the hood

1. ORBIT classifies the intent of your question.
2. It picks the closest SQL template from `intent-sql-sqlite-hr`'s template library.
3. An LLM extracts parameters (dates, names, numbers) from your question.
4. ORBIT runs the parameterized SQL against your database.
5. Results are formatted back into natural language.

Templates — not free-form SQL generation — are what make this safe and reliable. You'll see the same pattern in DuckDB, MongoDB, HTTP, and GraphQL adapters.

---

[Tutorial home](../tutorial.md) | [Previous: Adapter Types Overview](adapter-types.md) | [Next: Example 2: Chat with Files](chat-with-files.md)

---
