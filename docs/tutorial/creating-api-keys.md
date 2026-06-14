# Creating API Keys

API keys decide *which adapter* a caller uses and *which system prompt* gets injected. One key, one adapter, one prompt — that's the model.

You can create and manage keys either from the web admin panel or from the CLI.

### Option A — Admin panel (recommended for exploration)

1. Open **`http://localhost:3000/admin`** and sign in (default username `admin`, password from `ORBIT_DEFAULT_ADMIN_PASSWORD`).
2. Go to **API Keys** → **+ Create**.
3. Pick the adapter, name the key, paste or attach a system prompt, and save.
4. The `orbit_…` key is shown once — copy it immediately; ORBIT never shows it again.

The admin panel also lets you:

- Bulk-delete keys, search by name/adapter, and edit metadata/notes (markdown-rendered in the detail view).
- Attach or switch prompts (managed under the **Prompts / Personas** tab) without rotating the key.
- See recent activity for a key in the **Audit** tab (admin events auditing was added in 2.6.6).

### Option B — CLI (faster for scripted setup)

```bash
# Log in first
./bin/orbit.sh login --username admin --password admin123

# Inline prompt
./bin/orbit.sh key create \
  --adapter simple-chat \
  --name "My Assistant" \
  --prompt-text "You are a helpful assistant."

# Prompt from file
./bin/orbit.sh key create \
  --adapter intent-sql-sqlite-hr \
  --name "HR Bot" \
  --prompt-file ./examples/prompts/hr-assistant-prompt.txt \
  --prompt-name "HR Assistant"

# List & delete
./bin/orbit.sh key list
./bin/orbit.sh key delete --key orbit_abc123...
```

### CLI options

| Option | Description |
|:---|:---|
| `--adapter` | Which adapter to bind |
| `--name` | Friendly name |
| `--prompt-text` | Inline system prompt |
| `--prompt-file` | Load system prompt from file |
| `--prompt-name` | Name the prompt for reuse |
| `--notes` | Optional notes (markdown rendered in admin) |

### What else lives in the admin panel

Beyond API keys, the panel at `/admin` handles everything you'd otherwise edit by hand or script:

| Tab | What you can do |
|:---|:---|
| **Overview** | Live system health, metrics, cached adapter/provider counts, Prometheus endpoint link |
| **Users** | Create/edit/delete admin users, reset passwords, bulk-delete |
| **API Keys** | CRUD with prompt attach/switch, search, quotas, bulk actions |
| **Prompts / Personas** | Author/edit/rename system prompts; changes propagate to associated API keys |
| **Adapters** | List all adapters, toggle `enabled` live (applies immediately as of 2.6.6), edit per-adapter YAML in an Ace editor, trigger `reload-adapters` and `reload-templates` |
| **Settings** | Edit `config.yaml` in the browser with validation before save |
| **Audit** | Browse admin/auth events (login, key mutations, config edits) and conversation audit logs when enabled |

> Tip: adapter toggles from the Adapters tab now notify the running server immediately (fix in 2.6.6) — no separate "Reload Adapter" click needed.

---

[Tutorial home](../tutorial.md) | [Previous: Example 9: Skills and Image Generation](skills-image-generation.md) | [Next: Connecting Your Own Data](connecting-your-own-data.md)

---
