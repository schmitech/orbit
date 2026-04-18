# Audit Ledger — Integration Plan (Path A)

**Status:** Ready to execute when the tab work is scheduled.
**Prototype reference:** `docs/prototypes/audit_ledger.html`
**Backend dependency:** `AuditService.query_admin_events()` (already shipped — see `server/services/audit/audit_service.py`).

---

## Context

The admin audit logging backend is live (`audit_admin_logs` table, middleware-populated). The prototype at `docs/prototypes/audit_ledger.html` is a design spike with an intentionally distinctive editorial aesthetic (Fraunces / cream paper / vermillion accent) — **not production-shaped.** Dropping that aesthetic next to the existing Inter/navy admin panel would look bolted-on.

Path A reimplements the prototype's *information architecture* — register + dossier, outcome/domain filters, section-grouped fields, secret-scrubbed summary — as a **new tab inside the existing SPA** (`admin_panel.js`) using the tokens in `admin_panel.css`. Same cookie session, same shell, consistent visual language.

What is kept from the prototype:
- Two-pane layout: register (list) on the left, dossier (detail) on the right
- Outcome filter (All / Succeeded / Failed) + domain filter (Auth / API Keys / Config / …) + free-text search
- Dossier sections: Principals / Request / Origin / Request Summary
- Visual distinction for failures via `--danger-*` tokens
- "Summary block" framing that makes secret-scrubbing visible as a feature

What is dropped:
- Fraunces display + paper texture + drop caps + Roman-numeral dates
- Custom palette — replaced by existing `--ink`, `--brand-*`, `--danger-*`, `--success-*`

---

## Backend work

### 1. Expose `query_admin_events` over HTTP

Add an admin-protected endpoint in `server/routes/admin_routes.py`:

```
GET /admin/audit/events
```

**Query params:**
- `limit` (int, default 50, max 500)
- `offset` (int, default 0)
- `event_type` (string, optional, exact match)
- `actor_id` (string, optional, exact match)
- `success` (bool, optional)
- `resource_type` (string, optional)
- `q` (string, optional — free-text; implement as `LIKE %q%` over `actor_username`, `path`, `resource_id`, `ip` in the SQLite strategy; keyword search in ES; simple regex in Mongo)
- `since` / `until` (ISO timestamp, optional — `timestamp` range)

**Handler shape:**

```python
@admin_router.get("/admin/audit/events")
async def list_admin_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    success: Optional[bool] = None,
    resource_type: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    authorized: bool = Depends(admin_auth_check),
):
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is None or not audit_service.admin_events_enabled:
        raise HTTPException(503, "Admin audit is not enabled")
    filters = {k: v for k, v in {
        "event_type": event_type,
        "actor_id": actor_id,
        "success": success,
        "resource_type": resource_type,
    }.items() if v is not None}
    # Timestamp range + free-text search need strategy-specific support —
    # extend query() signatures or implement filtering server-side.
    events = await audit_service.query_admin_events(filters=filters, limit=limit, offset=offset)
    return {"events": events, "limit": limit, "offset": offset}
```

**Notes:**
- Reuse the existing `admin_auth_check` dependency — same auth gate as every other `/admin/*` route.
- `since` / `until` / `q` aren't natively supported by the current strategy interfaces. Easiest path: extend `AdminAuditStorageStrategy.query()` to accept them, or do post-filtering in Python for SQLite until volume requires otherwise.

### 2. Tests

Add to `server/tests/test_services/test_admin_audit.py` (or a new file under `tests/test_admin/`):
- Endpoint returns 503 when admin audit is disabled
- Endpoint returns 200 + empty list when enabled with no rows
- Filter by `event_type` works
- Filter by `success=false` works
- `limit`/`offset` pagination works
- Requires admin auth (401 without cookie/API key)

---

## Frontend work

### 3. Register the new tab in `admin_panel.js`

The SPA is a single 4300-line file that owns navigation, tab registration, and rendering. Locate the tab registry (grep for how existing tabs like "API Keys", "Prompts", "Config" are registered) and add:

```js
{
  id: "audit",
  label: "Audit",
  icon: /* inline SVG — use a stroke-style clipboard/ledger */,
  order: /* slot between "Config" and "Logs" */,
  render: renderAuditView,
}
```

Access control: tab should only be visible for users whose `role === 'admin'` — check how the existing SPA filters tabs by role and follow the same pattern.

### 4. `renderAuditView()` — register table (left column, ~60%)

```
┌──────────────────────────────────────────────────────┐
│  Audit                               [outcome chips] │
│  ─────                                [domain chips] │
│                                       [search …   ⌕] │
├──────────────────────────────────────────────────────┤
│  #   Time      Event            Actor      Status    │
│  137 Apr 18…   auth.login       r.schm…    200  ok   │
│  136 Apr 18…   auth.login       —          401 fail  │
│  135 Apr 18…   admin.api_key.   r.schm…    201  ok   │
│       …                                              │
└──────────────────────────────────────────────────────┘
```

- Column set: `№` / `Time` / `Event (type + one-line summary)` / `Actor (name + role)` / `Resource` / `Status (code + chip)`
- Row click → populate the dossier pane. Active row gets the existing "selected row" treatment.
- Failure rows: `status` cell uses `color: var(--danger-500)`; chip uses `--danger-50` bg + `--danger-text` fg — reuse existing danger-chip styles in `admin_panel.css`.
- Success chip: existing `--success-50` / `--success-text`.
- Scrolling: the table body scrolls independently; the dossier is sticky on desktop ≥ 1100px.

### 5. `renderAuditView()` — dossier pane (right column, ~40%)

```
┌────────────────────────────────┐
│ Dossier · adm-00231        [×] │
├────────────────────────────────┤
│ auth.login                     │
│ Session created for admin.     │
│ [ succeeded ]                  │
│                                │
│ PRINCIPALS                     │
│ Actor       r.schmilinsky      │
│ Capacity    user               │
│ Resource    —                  │
│                                │
│ REQUEST                        │
│ Method      POST               │
│ Path        /auth/login        │
│ Status      200                │
│ Timestamp   2026-04-18 14:31   │
│ Action      LOGIN              │
│                                │
│ ORIGIN                         │
│ IP          172.19.4.112       │
│ Source      proxy              │
│ User-Agent  orbit-cli/1.8.3    │
│                                │
│ REQUEST SUMMARY                │
│ fields recorded; secrets scrubbed │
│ ┌──────────────────────────┐   │
│ │ username: "r.schmilinsky" │   │
│ └──────────────────────────┘   │
└────────────────────────────────┘
```

- Three section headings as small-caps tags (reuse existing admin_panel section-header style).
- `request_summary` rendered in a mono code block using `--font-mono` — this is the "this is what we stored, no secrets" block from the prototype.
- When no row is selected: show an empty state with prose ("Select an entry to inspect its dossier").
- Close button (×) clears selection. ESC key also clears.

### 6. Filters + search

- Outcome chips: `All` / `Succeeded` / `Failed` — three-way toggle, URL-synced via query string (`?outcome=failed`) so views are bookmarkable.
- Domain chips: `All` / `Auth` / `API Keys` / `Config` / `Server` / `Prompts` — filter by `event_type` prefix.
- Search input debounced at 250ms, posts to the `q` query param.
- Each filter change refetches from `/admin/audit/events`.

### 7. Pagination

Audit tables grow without bound. Two options:

- **Infinite scroll** with `IntersectionObserver` on the last row → fetch next `limit`-sized page, append. Matches the "feed" feel.
- **Paged** with `< 1 2 3 … >` footer. Cleaner for forensic scrubbing ("give me page 4").

**Recommendation:** paged — auditors often need stable page numbers to share. Reuse whatever the existing admin panel does for lists (API keys list, prompts list) for consistency.

### 8. CSV export (optional, valuable)

Add an "Export" button next to the filters that posts current filters to a new `GET /admin/audit/events.csv` endpoint. Compliance / review workflows always end up in a spreadsheet.

### 9. CSS additions

Aim for zero new tokens. If anything is missing in `admin_panel.css`:
- A two-column `--ledger-grid` layout (likely already exists for other split views).
- A `.mono-block` style for the summary block (check existing `.code-block` or similar).
- Section-header smallcaps style (likely exists).

Only add new classes scoped under `.audit-view` to avoid bleed.

---

## Files to touch

**Modify:**
- `server/routes/admin_routes.py` — new `/admin/audit/events` (+ optional `.csv`) endpoints
- `server/services/audit/admin_audit_storage_strategy.py` — extend `query()` with timestamp range + free-text if the simple dict filter is insufficient
- `server/services/audit/{sqlite,mongodb,elasticsearch}_admin_audit_strategy.py` — implement the extended filter support per backend
- `server/admin/admin_panel.js` — add tab registration + `renderAuditView` + `renderDossier` + filter handling
- `server/admin/admin_panel.css` — minimal scoped additions under `.audit-view` if needed

**Create:**
- `server/tests/test_admin/test_audit_endpoint.py` (or add to existing admin tests) — endpoint integration tests

**Reuse (no changes):**
- `AuditService.query_admin_events` — already shipped
- `admin_auth_check` dependency — already shipped
- Admin panel design tokens in `admin_panel.css`

---

## Verification

1. **Backend:**
   - `curl -b cookies.txt http://localhost:3000/admin/audit/events?outcome=failure` returns filtered JSON
   - Pagination: `?limit=10&offset=20` returns expected slice
   - 401 without the admin cookie / 503 when `admin_events.enabled=false`
2. **Frontend:**
   - Sign in as admin → `Audit` tab appears; as non-admin → tab is hidden
   - Click any row → dossier populates; ESC clears
   - Outcome chips filter; domain chips filter; search filters
   - URL query string reflects current filter state; page refresh restores it
   - Failure rows visually distinct
3. **Regression:**
   - Existing admin tabs (API Keys, Prompts, Config) unaffected
   - No new CSS tokens introduced; no font imports added

---

## Out of scope for this pass

- Real-time streaming (SSE/WebSocket) for live event feed — defer until a concrete need lands.
- Retention UI (delete old audit rows) — operators can use backend tooling (MongoDB TTL, SQLite VACUUM) until the use case is proven.
- Audit-log analytics (charts, trend lines) — this viewer is a register, not a dashboard.
- Any reshaping of the prototype's distinctive aesthetic. That file stays a reference; no production code imports from it.
