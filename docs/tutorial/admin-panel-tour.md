# Admin Panel Tour

**Level 0 · Orientation**

The admin panel (`http://localhost:3000/admin`) is where you'll do almost every setup and monitoring task in this tutorial — creating keys, wiring up adapters, watching what your server is doing. This page is a screen-by-screen tour of all 12 tabs, so you know what's there before you need it. If you just want to create your first key right now, go to [Your first chat](first-chat.md) or [Creating API Keys](creating-api-keys.md) instead — come back here when you want the full map.

Sign in with the default credentials (`admin` / the value of `ORBIT_DEFAULT_ADMIN_PASSWORD`, or `ChangeMe!2026` if unset — change this before any real deployment).

<!-- MEDIA: screenshot | admin-panel-tour/login | Admin panel login screen -->
> 🖼️ **Screenshot placeholder:** the login screen.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

## The four tabs you'll use to get started

### Overview

The first thing you see after logging in: live server health, CPU/memory, requests/sec, error rate and response-time charts, cached adapter/provider counts, and a link to the Prometheus metrics endpoint. Check this after `./bin/orbit.sh start` to confirm the server is actually healthy before you start configuring anything.

<!-- MEDIA: screenshot | admin-panel-tour/overview | Overview tab dashboard with health/metrics charts -->
> 🖼️ **Screenshot placeholder:** the Overview dashboard.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### API Keys

Create, search, and manage keys — the primary onboarding task. Each key is tied to one adapter and one persona/system-prompt. See [Creating API Keys](creating-api-keys.md) for the full walkthrough. Also supports bulk actions, quotas, and per-key notes.

<!-- MEDIA: screenshot | admin-panel-tour/api-keys | API Keys tab list view -->
> 🖼️ **Screenshot placeholder:** the API Keys list and detail view.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### Prompts / Personas

Author and edit system prompts ("personas"). Changes here propagate automatically to every API key attached to that persona — you don't need to rotate keys to change behavior. Try creating a second persona with a different tone and swapping it onto your `First Chat` key to see the effect immediately.

<!-- MEDIA: screenshot | admin-panel-tour/prompts | Prompts/Personas tab showing the persona editor -->
> 🖼️ **Screenshot placeholder:** the persona editor.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### Adapters

List every configured adapter, toggle `enabled` live (takes effect immediately, no restart), and edit an adapter's YAML directly in an in-browser Ace editor. This is where you'll spend time once you start connecting your own data — see [Connecting Your Own Data](connecting-your-own-data.md). Also triggers `reload-adapters` / `reload-templates` without a server restart.

<!-- MEDIA: screenshot | admin-panel-tour/adapters | Adapters tab showing the adapter list with enabled toggles -->
> 🖼️ **Screenshot placeholder:** the Adapters tab with an active adapter listed.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

## Tabs for when you go further

### Users

Create/edit/delete admin accounts, assign roles, reset passwords. Relevant once more than one person administers the server.

### MCP

Add and configure MCP servers — tool discovery/timeout defaults and per-server settings. Ping a server to inspect its live tools. Its **Playbooks** section lists database-authored Tool Skills whose `mcp_tools` patterns match those discovered, already-namespaced tool names. File-authored playbooks can still be active at runtime even though this cross-reference intentionally lists database records only. Only relevant once you're using [MCP tool calling](mcp-tool-calling.md); skip this tab entirely until then.

<!-- MEDIA: screenshot | admin-panel-tour/mcp | MCP tab showing a configured MCP server -->
> 🖼️ **Screenshot placeholder:** the MCP tab.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### Skills

Create, edit, enable/disable, and delete database-authored procedural
playbooks bound to MCP tools with case-sensitive `mcp_tools` glob patterns.
Changes become live without restarting ORBIT. A database playbook with the
same name as `config/skills/<name>/SKILL.md` overrides that file; disabling or
deleting the database record restores the file. This tab lists database
records only, not the active file library. In governed or multi-tenant
deployments, pair new playbooks with explicit adapter
`capabilities.tool_skills` allowlists—omitting the field makes every playbook
matching a visible tool eligible for that adapter.

See [MCP Agent Skill](../adapters/mcp-agent.md#mcp-tool-skill-playbooks) for
authoring and runtime details.

### Settings

Edit `config.yaml` in the browser, with validation before save, grouped into sections (General & Performance, Auth & Security, Internal Services & Storage, Retrieval & Files, Reliability & Messaging). The CLI/manual-YAML-edit equivalent for anyone who prefers a UI over `vim config/config.yaml`.

### Costs

Token usage and estimated-cost charts — prompt/completion tokens, cost per time bucket, cumulative spend. Useful once you're running real traffic against paid providers.

### Feedback

Satisfaction analytics per adapter, plus a table of recent negative feedback with the conversation context that produced it. Useful for tuning prompts/adapters based on real usage.

### Ops

Server restart/shutdown controls and a live log viewer. These are operational, potentially disruptive actions — not something you'll touch during onboarding.

### Audit

An event ledger for admin, auth, and inference activity — filterable, with drill-down into individual events. Relevant for compliance/security review once you're running in production.

---

[Tutorial home](../tutorial.md) | [Previous: Before you start](before-you-start.md) | [Next: Your first chat](first-chat.md)
