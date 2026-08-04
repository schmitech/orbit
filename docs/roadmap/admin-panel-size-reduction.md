# Admin Panel Modularization Roadmap

## Goal and Guardrails

Break the vanilla admin panel into native ES modules without changing routes,
API payloads, permission checks, URLs, or existing CSS/DOM contracts. Each
feature module owns its state and exposes a small lifecycle interface:
render(container) and, when needed, dispose().

Keep /static/admin_panel.js as the public entry asset. Do not introduce a
bundler or framework as part of this refactor.

## Progress

### Phase 1 — shared core + Feedback — completed

Completed:

- [x] Switched the panel script in admin_panel.html to type="module".
- [x] Extracted shared browser modules:
  - [x] server/admin/admin_panel/core/api.js: endpoint constants and
    authenticated request helper.
  - [x] server/admin/admin_panel/core/dom.js: DOM creation, clearing, and table
    wrapper helpers.
  - [x] server/admin/admin_panel/core/charts.js: shared Chart.js defaults.
  - [x] server/admin/admin_panel/core/metrics.js: shared summary metric-card
    renderer used by Feedback and Costs.
- [x] Extracted server/admin/admin_panel/tabs/feedback.js.
  - [x] It owns the selected time window, request-version guard, Chart instances,
    rendering, and cleanup.
  - [x] The legacy app creates it with explicit dependencies and calls
    feedbackTab.render() / feedbackTab.dispose() during tab transitions.
- [x] Updated the admin template version calculation so a change in any module
  under server/admin/admin_panel/ refreshes the panel entry asset.
- [x] Added server/tests/test_admin/test_admin_panel_modules.py, which checks
  the module entrypoint, local import paths, and JavaScript parsing when Node
  is available.

Result: server/admin/admin_panel.js was reduced from 8,367 to 7,930 lines.
The new module source adds structure without retaining a duplicate Feedback
implementation.

Verified:

- [x] Parsed the entrypoint and every current admin module with
  node --input-type=module --check.
- [x] Ran the new module smoke checks directly; they passed.
- [x] git diff --check passed.
- [ ] The existing pytest route test was not run locally because this environment
  does not have pytest installed. Run
  python -m pytest server/tests/test_routes/test_admin_panel_feedback_analytics.py -q
  in the project test environment before merging.

### Phase 2 — observability — next

Extract the following in this order:

1. [ ] Costs into tabs/costs.js, using the existing shared API, DOM, and chart
   helpers. Preserve all query controls, chart tooltip behavior, and stale
   request handling.
2. [ ] Audit into tabs/audit.js. Keep filters, pagination, selected dossier
   state, and error messaging module-local.
3. [ ] Overview into tabs/overview.js after Costs and Audit. Preserve WebSocket
   connection/reconnect behavior, chart teardown, filters, tables, and
   beforeunload cleanup.

Before each extraction, use the Feedback pattern: instantiate the module in
the legacy shell with only its needed dependencies, replace the matching
render branch, route exit cleanup through dispose(), then remove the original
implementation in the same change.

### Phase 3 — access and content management

- [ ] Extract Users, API Keys, and Prompts into feature modules.
- [ ] Promote form validation, selection-table, and detail-pane helpers only after
  at least two modules use them.

### Phase 4 — operations and configuration

- [ ] Extract Ops, Adapters, Settings, and MCP modules.
- [ ] Keep Ace editor setup/teardown and dirty-state confirmation within the
  owning module.

## Completion Criteria for Every Phase

- No duplicate feature implementation remains in admin_panel.js.
- The affected tab loads, refreshes, handles errors, and survives navigation
  away and back.
- Permission-gated states and all mutation confirmation flows still work.
- Module smoke checks and relevant backend route tests pass.
- In a browser, test the affected tab with a representative permitted role;
  additionally verify Overview WebSocket cleanup and Settings/Adapters dirty
  prompts when those modules are extracted.
