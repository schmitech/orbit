# MCP Connection Editing — stdio and custom headers

## Summary

The MCP panel's per-server Connection section (added alongside hot reload)
only supports editing `url` and `token` for `http`/`sse` transports — both are
single scalar YAML lines, which the existing line-patcher
(`_patch_yaml_scalars` in `server/routes/admin_routes.py`) can already set in
place safely. Two cases are deliberately left read-only for now:

- **stdio servers** (`command`, `args`, `env`) — switching a local MCP server's
  command or arguments (e.g. pointing `args` at a different local path) still
  requires editing `mcp_clients.yaml` directly and reloading via the panel's
  existing "saved and applied" flow on another field, or a full restart.
- **Servers authenticating via an explicit `headers` map** (e.g. the `github`
  entry in `config/mcp_clients.yaml`, which sets `headers.Authorization`
  instead of using the `token` shorthand) — `update_mcp_server` rejects a
  `token` edit for these with a 422 explaining that `headers` overrides it, so
  no confusing no-op edit is possible, but there's no editable path for the
  header value itself.

## Why these were left out

`args` is a YAML list and `env`/`headers` are nested maps. `_patch_yaml_scalars`
only knows how to set or delete one `key: value` scalar line within a block —
rewriting a list or a map safely (preserving comments, handling additions and
removals of individual entries, quoting each value correctly) is materially
more YAML-patching logic than the url/token case, and higher risk of silently
corrupting `mcp_clients.yaml`'s ~240 lines of commented-out server catalogue
if done carelessly.

## Suggested approach

Extend the line-patcher with a block-aware variant, e.g.
`_patch_yaml_mapping(lines, start, end, key, mapping, indent)` that:
- Locates the `key:` block (e.g. `env:` or `headers:`) the same way
  `_find_adapter_block` locates a server's `- name:` block.
- Rewrites each `subkey: value` line inside it in place (reusing the same
  quoting from `_patch_yaml_scalars`), inserting new subkeys and deleting ones
  mapped to `None`, without disturbing lines outside the block.
- Creates the block (with the parent's `key:` header line) if it doesn't
  exist yet and the caller is adding the first entry.

`args` (a list, not a mapping) would need its own single-line list rewrite,
e.g. re-emitting `args: ["-y", "pkg", "value"]` wholesale, which is simpler
than the mapping case since ORBIT's example configs always keep `args` on one
line already.

Once available, extend `_validate_mcp_connection` (or a sibling validator) to
accept `command`/`args`/`env` for stdio and `headers` for any transport, and
add matching fields to the panel's Connection section — a per-row model
similar to the existing `mcpConnectionRow` should extend directly to a
key/value list editor for `env`/`headers`.
