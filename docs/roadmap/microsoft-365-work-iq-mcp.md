# Microsoft 365 Work IQ MCP Support

## Summary

Add first-class support for Microsoft-hosted Work IQ MCP servers so ORBIT can
connect to Microsoft 365 data and actions with a user-authorized Microsoft
Entra identity. Start with SharePoint, OneDrive, and Mail, then add Calendar,
Teams, and Word after the authentication and connection lifecycle are proven.

Microsoft exposes Work IQ as a family of tenant-scoped remote MCP servers, not
as one universal Microsoft 365 endpoint. The service is currently preview;
server names, tool schemas, and availability may change. See the [Work IQ MCP
overview](https://learn.microsoft.com/en-us/microsoft-agent-365/mcp-server-reference/admintools)
and [SharePoint server reference](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-sharepoint-work-iq).

## Current state

- `config/mcp_clients.yaml` contains disabled placeholders for SharePoint,
  OneDrive, and Mail. They use a manually supplied bearer token only as a
  short-lived development workaround.
- ORBIT's MCP client supports configured headers and bearer tokens, but does
  not initiate an OAuth authorization-code flow, store per-user grants, or
  refresh access tokens.
- Existing ORBIT Entra/OIDC support validates tokens presented to ORBIT; it is
  not an outbound OAuth client for an MCP server.

## Goals

- Connect to tenant-scoped Work IQ servers over Streamable HTTP.
- Complete Microsoft Entra OAuth with Authorization Code + PKCE for each ORBIT
  user and eligible MCP server.
- Store encrypted, per-user, per-server token state and refresh it safely.
- Let administrators allowlist Work IQ servers and required scopes; let users
  grant only their own delegated access.
- Surface connection state, expiry, and reauthorization in the admin/UI APIs.
- Preserve existing MCP guardrails: server allowlists, timeouts, tool-loop
  iteration limits, sources/audit records, and destructive-tool caution.

## Non-goals

- Making a shared Microsoft 365 service-account token the default access model.
- Supporting every Work IQ server in the first release.
- Promising preview endpoint or tool-schema stability.
- Replacing ORBIT's normal inbound Entra/OIDC authentication.

## Phased plan

### Phase 0 — Validate the vendor contract

1. Confirm the current Streamable HTTP behavior, OAuth metadata, required
   Microsoft Entra permissions, tenant/licensing prerequisites, and tool
   schemas for SharePoint, OneDrive, and Mail using a dedicated test tenant.
2. Verify that the documented server IDs are available to the tenant:
   `mcp_SharePointRemoteServer`, `mcp_OneDriveRemoteServer`, and
   `mcp_MailTools`.
3. Record confirmed endpoint, OAuth scopes, consent requirements, and expected
   read/write tools in a compatibility table in the MCP documentation.
4. Explicitly assess prompt-injection exposure from mail, file, and SharePoint
   content before enabling opportunistic use.

**Exit criteria:** a manual OAuth connection can list tools and make a
read-only call to each pilot server.

### Phase 1 — Outbound OAuth foundation

1. Extend the MCP client configuration schema with an opt-in `oauth` block:
   authorization server metadata/discovery URL, client ID, scopes, redirect
   URI, and token audience/resource where required.
2. Implement authorization-code + PKCE start/callback endpoints, with strict
   `state`, nonce, redirect-URI, issuer, audience, and expiry validation.
3. Create encrypted persistence for token state keyed by ORBIT user, MCP
   server, and tenant. Do not store tokens in YAML, logs, source records, or
   tool-result previews.
4. Implement refresh-token rotation, concurrent-refresh locking, revocation,
   and a clear reauthorize state.
5. Make the selected user grant available only to that user's MCP calls;
   never fall back silently to another user's or an administrator's token.

**Exit criteria:** a user can connect and disconnect one Work IQ server from
ORBIT, restart ORBIT, and retain or refresh only their own grant.

### Phase 2 — MCP connection and authorization behavior

1. Make the HTTP transport obtain a valid OAuth access token immediately before
   connection/discovery and tool calls; retry exactly once after a refresh on
   an authentication failure.
2. Keep static `headers`/`token` support for service integrations, but reject a
   configuration that ambiguously mixes those credentials with user OAuth.
3. Define discovery cache keys that include the server/tenant capability set
   but never a raw token; invalidate when authorization changes.
4. Report actionable errors: no grant, expired/revoked grant, insufficient
   scope, tenant feature unavailable, and Microsoft service failure.
5. Confirm request cancellation, timeout, and multi-worker behavior do not
   leak or reuse a user grant.

**Exit criteria:** concurrent users in the same tenant can call the same MCP
server with isolated permissions and correctly attributed audit events.

### Phase 3 — Work IQ pilot integrations

1. Enable **SharePoint** first, initially read-only in adapter allowlists;
   require explicit user wording for delete/share/write tools.
2. Add **OneDrive** and **Mail** after the OAuth flow and audit trail pass the
   SharePoint test suite.
3. Add **Calendar**, **Teams**, and **Word** only after Phase 0 validates the
   current server IDs, schema, scopes, and supported licensing for each.
4. Default all Work IQ entries to `enabled: false` and
   `allow_opportunistic: false`; require an administrator to opt in per server
   and an adapter to allowlist it.
5. Document least-privilege Entra permissions and a separate read-only versus
   write-capable configuration for each server.

**Exit criteria:** the three pilot servers have integration tests, operational
documentation, and an explicit production-readiness decision.

### Azure DevOps follow-on

The official Azure DevOps MCP server provides two paths:

- A local `stdio` server (`@azure-devops/mcp`) that can use Azure CLI
  authentication. A disabled, deliberately narrow-domain placeholder is in
  `config/mcp_clients.yaml` and can be evaluated independently of this roadmap.
- A Microsoft-hosted Streamable HTTP endpoint at
  `https://mcp.dev.azure.com/{organization}`. It is preview and requires
  Microsoft Entra OAuth dynamic client registration, so it cannot be enabled
  in ORBIT until the outbound OAuth foundation in Phases 1–2 exists.

After Phase 2, validate Azure DevOps as the first non-Work-IQ consumer of the
same OAuth client lifecycle. Cover work-item, pull-request, pipeline, and
wiki read operations before write operations; retain a narrow domain allowlist
so the model is not presented with the entire Azure DevOps tool surface on
every turn. Azure DevOps Server (on-premises) is not in scope because the
official MCP server supports Azure DevOps Services only.

### Phase 4 — Administration, tests, and rollout

1. Add admin/UI actions for Connect, Disconnect, Reauthorize, and inspect
   connection status without exposing token material.
2. Add tests for PKCE/state validation, token encryption, refresh rotation,
   per-user isolation, retry behavior, scope failures, and redaction.
3. Add a mocked Work IQ HTTP server to the test suite so CI does not depend on
   a Microsoft tenant; retain a separately gated manual tenant smoke test.
4. Add metrics for authorization success/failure, refreshes, connection and
   tool latency, and tool errors, all with sensitive values redacted.
5. Gate the feature behind an explicit preview flag until Microsoft publishes
   stable contracts and ORBIT's security/operational tests meet release
   criteria.

## Configuration placeholders

The disabled examples in `config/mcp_clients.yaml` intentionally use
`M365_ACCESS_TOKEN` as a temporary manual-token mechanism. Phase 1 replaces
that pattern with the proposed per-user `oauth` configuration; do not enable
the entries in a shared deployment with a long-lived personal token.

## Open decisions

- Which token-store backend should hold outbound MCP grants: ORBIT's database,
  an existing secret manager abstraction, or both?
- Should Work IQ connections be user-managed, admin-managed with delegated
  consent, or support both models?
- Which write/destructive tools require ORBIT-level confirmation rather than
  relying only on tool descriptions?
- Does the Microsoft preview contract support the exact static-header flow
  used by the interim placeholders, or must Phase 1 land before any ORBIT
  connection is attempted?
- Which Work IQ server IDs and scopes are stable enough to publish beyond the
  initial SharePoint, OneDrive, and Mail pilot?
