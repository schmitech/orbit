# API Key Expiration — Admin Panel Integration Plan

## Summary

Integrate the API-key expiration capability delivered in
[Phase 8](complete/phase-8-api-key-expiration.md) into the browser-native API Keys tab at
`server/admin/admin_panel/tabs/api-keys.js`.

Administrators should be able to see expiration state at a glance, choose an
expiration policy when creating a key, renew an existing or expired key, and
grant a justified non-expiring exception without using the CLI or calling the
API directly.

This is primarily an admin-panel change. The existing create, list, detail,
status, and renewal APIs remain authoritative for policy and validation.

## Current state and backend contract

The API Keys tab currently supports creating, listing, inspecting, testing,
renaming, editing metadata, deactivating, deleting, and managing quotas. It does
not render or submit any expiration fields.

The backend now provides the following contract:

- `POST /admin/api-keys`
  - Omitting both expiration choices creates a managed key with the server's
    configured default lifetime.
  - `expires_at` accepts an absolute, timezone-aware timestamp.
  - `non_expiring: true` creates an exception and requires a non-empty
    `expiration_justification`.
  - `expires_at` and `non_expiring: true` are mutually exclusive.
- `GET /admin/api-keys` and
  `GET /admin/api-keys/{record_id}/detail` return:
  - `expires_at` as a Unix timestamp or `null`;
  - `expiration_policy` (`managed`, `legacy_migration`, or
    `non_expiring_exception`);
  - `expired`;
  - `days_remaining` or `null`.
- **Backend addition required by this plan**: `GET /admin/api-keys` must also
  return a top-level `expiration_warning_days` field (a sibling of the key
  array, not a per-key field) sourced from the existing
  `api_keys.expiration_warning_days` config setting (default 14). The panel
  uses this as the "approaching expiration" and "expiring soon" threshold
  instead of a hardcoded number, so a deployment that changes the config value
  doesn't leave the UI silently out of sync. This endpoint is already gated on
  `apikeys.manage`, so no new permission is introduced; a value it can already
  read is simply exposed alongside the list it can already read. Do not add a
  new endpoint or read `GET /admin/config/sections/api_keys` for this — that
  route requires `config.manage`, which an API-key-only operator may not have.
- `POST /admin/api-keys/{record_id}/renew` requires exactly one of:
  - `{ "expires_at": "<timezone-aware ISO timestamp>" }`; or
  - `{ "non_expiring": true, "expiration_justification": "..." }`.
- Renewal accepts a record ID or a raw key, but the admin panel must always use
  the non-secret record ID already present in list/detail responses.
- Renewal can make an expired key usable again, but it does not reactivate a
  key whose independent `active` flag is false.
- The server enforces future dates, maximum lifetime, exception policy, and
  required justification. The UI may provide immediate validation but must
  display server validation errors unchanged through the existing `api()` and
  `showError()` path.

## User experience

### 1. Expiration state in the key list

Add an **Expiration** column to `renderKeyTable()` and make it sortable through
the existing `createColumnSorter()` integration.

Render one concise state per key:

- expired: `Expired <localized date>` with an error badge;
- managed and approaching expiration: `<localized date> · <N> days` with a
  warning badge;
- managed with more time remaining: localized expiration date;
- non-expiring exception: `Never · Exception` with a neutral badge;
- missing legacy metadata: `Migration pending` rather than incorrectly calling
  the key non-expiring.

Use `expired`, `days_remaining`, and `expiration_policy` from the server. Do not
infer whether a key is expired by comparing browser time with `expires_at`; this
avoids client clock skew overriding the canonical server result. Date formatting
may use the browser's locale and timezone.

For sorting, use a numeric helper that produces a stable order:

- finite timestamps sort chronologically;
- explicit non-expiring exceptions sort after finite timestamps;
- missing metadata sorts last;
- reverse sorting reverses the complete ordering normally.

Update the existing **Active** presentation so an active-but-expired key is not
shown as simply healthy. Prefer an **Access** column/state with the precedence
`Inactive`, `Expired`, `Active`; expiration and deactivation remain independent.

### 2. List filters and pagination correctness

Add an expiration filter beside the existing search field with these options:

- All keys;
- Expired;
- Expiring soon (within the server's `expiration_warning_days`, labeled with
  the actual number, e.g. "Expiring within 14 days");
- Non-expiring exceptions.

Search and expiration filters should compose before data is passed to the
existing client-side paginator.

`loadKeys()` currently requests only the server's default page. Because the UI
filters and paginates locally, filtered results would otherwise be incomplete
when more than 100 keys exist. Add a small `loadAllKeys()` helper that requests
server pages with `limit=1000` and increasing `offset` until a short page is
returned, then updates `cachedKeys` once with the complete result. Keep refresh,
selection cleanup, sorting, and detail refresh behavior unchanged.

The "expiring soon" filter and badge threshold are a presentation shortcut, not
policy enforcement: both compare `days_remaining` against the server-supplied
`expiration_warning_days`, cached from the same response `loadAllKeys()`
already fetches (no extra request). Do not hardcode `14` in the module — a
deployment that changes `api_keys.expiration_warning_days` must see the panel
follow it. Fall back to `14` only if the field is unexpectedly absent (e.g. an
older server), and log a console warning in that case. All actual lifetime
limits remain server-side regardless of this threshold.

### 3. Expiration controls when creating a key

Add an accessible **Expiration policy** fieldset to the New API Key form with
three mutually exclusive choices:

1. **Server default** — selected initially; send no expiration fields.
2. **Custom expiration** — reveal a `datetime-local` input and send its value as
   an absolute UTC ISO timestamp using `new Date(value).toISOString()`.
3. **Non-expiring exception** — reveal a justification textarea (maximum 2000
   characters) and send `non_expiring: true` plus the trimmed
   `expiration_justification`.

Centralize payload construction in a helper such as
`buildExpirationRequest(choice, dateValue, justification)` so create and renew
cannot accidentally diverge. The helper must never produce both `expires_at`
and `non_expiring`.

Client-side checks should reject:

- a missing or invalid custom date;
- a custom date that is not in the future;
- an empty non-expiring justification.

Do not duplicate the configured maximum lifetime in JavaScript. Submit a valid
future timestamp and surface the server's policy error if it exceeds the
deployment's configured maximum.

After a successful create, reset the expiration controls to **Server default**,
clear any hidden values and validation state, and retain the existing behavior
for clearing the rest of the form and refreshing the list.

### 4. Expiration details and renewal

Add an **Expiration** section to `renderKeyDetail()` before quota management.
Show:

- current state (`Active`, `Expired`, `Inactive`, or `Non-expiring exception`);
- localized expiration date and time, or `Never` for an approved exception;
- `days_remaining` with sensible rounding and explicit handling for values
  between zero and one day;
- expiration policy with human-readable labels;
- a note that renewal does not reactivate an inactive key.

Add a **Renew / Change expiration** button that opens an inline form. Reuse the
same expiration-choice builder as creation, except renewal has no **Server
default** option because the endpoint requires exactly one choice.

For a finite renewal:

- require a valid future local date/time;
- convert it to an ISO timestamp;
- call `POST keyPath(keyId, "/renew")` with only `expires_at`.

For a non-expiring exception:

- require a trimmed justification;
- use `confirmAction()` with copy explaining that the key will no longer expire
  automatically;
- call the same renewal endpoint with only `non_expiring: true` and
  `expiration_justification`.

Drive submission through `withButton()` where compatible, prevent duplicate
submissions, show the existing success toast, and call the existing detail/list
refresh path after success. Always build the URL from `key._id`; never use the
displayed or revealed key value.

The current detail response does not expose the stored exception justification.
Do not imply that an omitted justification is unavailable in storage. Initially,
show the justification only in the immediate renewal success state if useful,
then refresh to canonical server data. If operators need persistent visibility,
add `expiration_justification` to the detail response only in a separate,
security-reviewed backend change; it is not required in list responses.

### 5. Shared rendering helpers

Keep `api-keys.js` consistent with the existing no-framework module style. Add
small pure helpers near the top of the module rather than duplicating branching
inside create, table, and detail rendering:

- `expirationState(key)` — canonical display category based on server fields;
- `formatExpiration(key)` — display label and optional secondary text;
- `expirationSortValue(key)` — stable numeric/category sort value;
- `buildExpirationRequest(...)` — mutually exclusive request payload;
- `createExpirationControls(options)` — DOM controls plus `reset()`,
  `validate()`, and `toRequest()` methods.

Export only pure helpers that are useful for automated tests. Keep DOM-specific
state private to `createApiKeysTab()` unless another tab has a concrete need for
it.

## Styling and accessibility

Add narrowly scoped styles to `server/admin/admin_panel.css` for expiration
controls and states. Reuse existing spacing, form, badge, warning, error, and
responsive-table primitives before adding new classes.

- Use a real `<fieldset>` and `<legend>` for expiration choices.
- Associate the custom date and justification controls with labels and helper
  text.
- Hide irrelevant controls from both keyboard navigation and assistive
  technology when the choice changes.
- Announce validation and renewal results through the existing toast/live-region
  behavior.
- Do not communicate expired or expiring-soon state by color alone; include text.
- Ensure the additional table column and renewal form remain usable at the
  existing mobile breakpoints.

## Error handling and security

- Treat server responses as canonical after every mutation and refresh both the
  selected detail and cached list.
- Preserve the raw-key masking/reveal/copy behavior already present.
- Never place a raw API key in the renewal path, logs, local storage, DOM data
  attributes, or audit context.
- Do not log exception justifications or API responses to the browser console.
- Leave failed renewal forms populated so the operator can correct the input.
- Handle a key deleted between list load and renewal using the existing API error
  toast, then offer/perform a list refresh.
- Ensure cancel/reset clears hidden non-expiring justifications so a later
  managed request cannot accidentally retain them.

## Implementation sequence

1. Add the `expiration_warning_days` field to the `GET /admin/api-keys`
   response (backend) and add the pure expiration classification, formatting,
   sorting, and payload helpers in `api-keys.js` (frontend), threading the
   warning-days value through rather than a hardcoded constant.
2. Change key loading to fetch every server page before local filtering and
   pagination, caching the response's `expiration_warning_days` alongside
   `cachedKeys`.
3. Add list expiration/access columns, sorting, and filters.
4. Add the create-form expiration fieldset and mutually exclusive payload
   construction.
5. Add the detail expiration summary and renewal form.
6. Add focused CSS and verify desktop/mobile keyboard interaction.
7. Extend static module tests and complete the manual acceptance matrix.

## Testing plan

Extend `server/tests/test_admin/test_admin_panel_modules.py` with Node-backed
checks for exported pure helpers where practical, while retaining its module
parse/import smoke test.

Automated cases should cover:

- managed, legacy-migration, expired, non-expiring, and missing-metadata display
  categories;
- expiration ordering, including `null` values;
- server `expired` winning over browser-side timestamp assumptions;
- create default producing no expiration properties;
- custom expiration producing only a valid ISO `expires_at`;
- non-expiring producing only `non_expiring` and a trimmed justification;
- rejection of empty justification, invalid/past date, and any conflicting
  choice state;
- multi-page loading continuing at 1000-record offsets and stopping on a short
  page;
- "expiring soon" classification and filter using the server-supplied
  `expiration_warning_days` (e.g. a key at 10 days remaining matching a
  configured threshold of 14 but not one of 7), and falling back to 14 with a
  console warning only when the field is absent from the response;
- search and expiration filters being applied before client pagination;
- renewal paths being built from the record ID.

Manual browser verification should cover:

- create with the server default, a custom date, and a non-expiring exception;
- switching choices repeatedly before submission without stale hidden values;
- server rejection of an over-limit date or disabled exception policy;
- renewing managed to managed, managed to non-expiring, non-expiring to managed,
  and expired to managed;
- renewing an inactive key and confirming it remains inactive;
- list/detail refresh after each mutation;
- expired/soon/non-expiring filtering with more than one server page;
- keyboard-only interaction, screen-reader labels, narrow viewport layout, and
  locale/timezone date rendering;
- confirmation that renewal audit records contain the record ID and canonical
  before/after state, never a raw key.

Run at minimum:

```bash
cd server
python -m pytest -q tests/test_admin/test_admin_panel_modules.py
python -m pytest -q tests/test_admin/test_api_key_route_logging.py \
  tests/test_middleware/test_admin_audit_middleware.py \
  tests/test_auth/test_api_key_service_sqlite.py
```

## Acceptance criteria

- Every key row and detail view communicates its expiration state without
  revealing the raw credential.
- Administrators can create managed and justified non-expiring keys from the
  panel.
- Administrators can renew active, inactive, and expired records using the
  non-secret record ID.
- The UI never submits both expiration choices and never treats omitted metadata
  as an approved non-expiring exception.
- Expiration search/filter/sort results are correct beyond the first server
  page.
- The "expiring soon" threshold shown and filtered on matches the server's
  configured `api_keys.expiration_warning_days`, not a hardcoded constant.
- Server-side policy errors are visible and actionable.
- Existing key metadata, allowlist, quota, deactivate, delete, selection,
  sorting, and pagination flows continue to work.
- Admin-panel module parsing and focused API-key/audit tests pass.

## Out of scope

- Automatic renewal or scheduled expiration notifications.
- Bulk renewal or bulk non-expiring exceptions.
- Editing deployment expiration-policy configuration from the admin panel.
- Reactivating inactive keys as a side effect of renewal.
- Deleting expired records automatically.
- Showing full API keys anywhere new.

## Related documentation

- [Phase 8 — API Key Expiration](complete/phase-8-api-key-expiration.md)
- [API key management](../../api-keys.md)
- [Admin audit coverage](complete/phase-4-auth-audit-trail-coverage.md)
- [SQLite schema](../../sqlite-schema.md)
- [PostgreSQL schema](../../postgres-schema.md)
