# Tutorial Media To-Do

Running manifest of every screenshot/video placeholder in `docs/tutorial/` (see [_style-guide.md](_style-guide.md) for the `MEDIA:` marker convention). Update this table whenever a placeholder is added, removed, or filled in with a real asset.

Verify sync anytime with:

```bash
grep -rn "<!-- MEDIA:" docs/tutorial/
```

| Slug | Type | Source file | Description | Status |
|---|---|---|---|---|
| `tutorial/overview` | video | `../tutorial.md` | 60s overview: what is ORBIT, tour of the learning path | Needed |
| `before-you-start/terminal-server-start` | screenshot | `before-you-start.md` | Terminal output of a successful `./bin/orbit.sh start` | Needed |
| `before-you-start/admin-login` | screenshot | `before-you-start.md` | Admin panel login screen | Needed |
| `first-chat/persona-create` | screenshot | `first-chat.md` | Creating the "friendly assistant" persona | Needed |
| `first-chat/api-key-create` | screenshot | `first-chat.md` | Creating the "First Chat" API key | Needed |
| `first-chat/admin-panel-walkthrough` | video | `first-chat.md` | 90s walkthrough: persona → API key → copy key | Needed |
| `first-chat/chat-response` | screenshot | `first-chat.md` | OrbitChat showing a successful reply | Needed |
| `creating-api-keys/api-keys-tab` | screenshot | `creating-api-keys.md` | API Keys tab list + creation form | Needed |
| `admin-panel-tour/login` | screenshot | `admin-panel-tour.md` | Login screen | Needed |
| `admin-panel-tour/overview` | screenshot | `admin-panel-tour.md` | Overview dashboard | Needed |
| `admin-panel-tour/api-keys` | screenshot | `admin-panel-tour.md` | API Keys list/detail view | Needed |
| `admin-panel-tour/prompts` | screenshot | `admin-panel-tour.md` | Persona editor | Needed |
| `admin-panel-tour/adapters` | screenshot | `admin-panel-tour.md` | Adapters tab with active adapter | Needed |
| `admin-panel-tour/mcp` | screenshot | `admin-panel-tour.md` | MCP tab with configured server | Needed |
| `sql-database-sqlite/adapter-config` | screenshot | `sql-database-sqlite.md` | `intent-sql-sqlite-hr` adapter YAML in Ace editor | Needed |
| `chat-with-files/upload-and-ask` | screenshot | `chat-with-files.md` | File attached in chat with grounded answer | Needed |
| `vector-store-qa/city-assistant-answer` | screenshot | `vector-store-qa.md` | City Assistant answering from vector-store context | Needed |
| `duckdb-analytics/query-result` | screenshot | `duckdb-analytics.md` | Revenue-trend question answered from DuckDB | Needed |
| `mongodb-queries/movie-result` | screenshot | `mongodb-queries.md` | Movie query answered from MongoDB | Needed |
| `multi-source-composite/adapter-config` | screenshot | `multi-source-composite.md` | `composite-multi-source` child_adapters config | Needed |
| `multi-source-composite/routing-response` | screenshot | `multi-source-composite.md` | `composite_routing` metadata in a real response | Needed |
| `skills-image-generation/generated-image` | screenshot | `skills-image-generation.md` | `/` skill picker and a generated image | Needed |
| `mcp-tool-calling/mcp-tab` | screenshot | `mcp-tool-calling.md` | MCP tab showing `business-sample` configured | Needed |
| `auto-skill-routing/inferred-skill-response` | screenshot | `auto-skill-routing.md` | Response auto-routed with no `skill` field | Needed |
