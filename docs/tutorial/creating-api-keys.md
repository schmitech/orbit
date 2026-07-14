# Creating API Keys

API keys decide *which adapter* a caller uses and *which system prompt* gets injected. One key, one adapter, one prompt — that's the model.

These tutorial flows use the web admin panel; the CLI remains available for automation if you need it.

### Option A — Admin panel (recommended for exploration)

1. Open **`http://localhost:3000/admin`** and sign in (default username `admin`, password from `ORBIT_DEFAULT_ADMIN_PASSWORD`).
2. Go to **API Keys** → **+ Create**.
3. Pick the adapter, name the key, select or create a persona, and save.
4. The `orbit_…` key is shown once — copy it immediately; ORBIT never shows it again.

The admin panel also lets you:

- Bulk-delete keys, search by name/adapter, and edit metadata/notes (markdown-rendered in the detail view).
- Attach or switch prompts (managed under the **Prompts / Personas** tab) without rotating the key.
- See recent activity for a key in the **Audit** tab (admin events auditing was added in 2.6.6).

### CLI reference

If you need scripted setup, see [Server](../server.md) for the `orbit` command reference and the API key management commands.

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

[Tutorial home](../tutorial.md) | [Previous: Example 12: Message Queue (Async) Requests](message-queue-async.md) | [Next: Connecting Your Own Data](connecting-your-own-data.md)

---
