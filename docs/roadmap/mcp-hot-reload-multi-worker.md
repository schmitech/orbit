# MCP Hot Reload — Multi-Worker Propagation

## Summary

MCP client hot reload (added in `server/services/mcp_client_service.py` and
`server/routes/admin_routes.py`) rebuilds the `MCPClientManager` singleton only
in the worker process that handled the admin request. Under
`performance.workers > 1`, sibling workers keep their old manager, so requests
routed to them can still expose a removed tool or keep calling a server that
was just disabled — despite the admin response reporting the change as applied.

## Review comment

- **[P1] Propagate MCP reloads to every worker** —
  `server/routes/admin_routes.py:_reload_mcp_clients` (currently `:2508`)
  When `performance.workers > 1`, this only replaces the singleton in the
  worker that handled the admin request. Other workers retain their old
  `MCPClientManager`, so requests routed to them can still expose removed
  tools or continue calling a server that was disabled, despite the response
  saying the change was applied. Propagate an MCP reload through the existing
  cross-worker reload mechanism (or retain a restart-required warning for
  multi-worker deployments).

## Suggested approach

Mirror the existing adapter-reload propagation in
`server/services/adapter_reload_state.py`: add an `"mcp_config"` kind to
`_KINDS`, bump its generation whenever `_reload_mcp_clients` succeeds, and add
an `_apply_reload` branch that rebuilds each polling worker's manager
(`reload_mcp_client_manager` + `refresh_tool_cache()`). This was deliberately
left out of the initial hot-reload change (see the plan at
`mcp-hot-reloading-plan.md`, "Not in scope") to keep that change scoped to a
single-worker rebuild-and-swap.

Since that plan, `_reload_mcp_clients` gained a per-server scoped path: editing
one server (`update_server(name, entry)` + `refresh_tool_cache([name])`) no
longer rebuilds the whole manager or re-dials unrelated servers in the request
worker (see `server/services/mcp_client_service.py`). The generation-bump
payload should therefore carry which server changed (or "all", for a
defaults-level edit) so `_apply_reload` in sibling workers can call the same
scoped path instead of always doing a full rebuild — otherwise propagation
would reintroduce the "one edit redials every server" behavior on every
worker except the one that took the request.

Until this lands, deployments with `performance.workers > 1` should treat MCP
panel saves as applied only to one worker and still restart the server to
guarantee the change reaches every worker.
