# Costs by API Key — Implementation Plan

## Summary

Add API key as a first-class dimension to the Costs tab, so an operator can
answer "which client is spending what" from the admin panel.

Every audit record already stores the API key used for the request, and the
same row already carries `cost_usd` and the token counts. Nothing new has to
be captured for a first cut — the missing piece is that `group_by` is
allowlisted to a fixed set of columns that excludes it. The phases below go
from that minimal grouping to a labelled, filterable, drill-down view.

The plan is deliberately incremental: each phase ships something usable on its
own, and no phase depends on a later one.

## Current state

`AuditService.log_conversation` (`server/services/audit/audit_service.py`)
builds `AuditRecord.api_key` as `{"key": <masked>, "timestamp": <iso>}`, where
the masked value comes from
`mask_api_key(api_key, show_last=True, num_chars=6)` — i.e. `"...abc123"`.
Each backend persists it differently:

| Backend | Field |
|---|---|
| SQLite | `api_key_value` column (`services/sqlite_service.py`) |
| Postgres | `api_key_value` column (`services/postgres_service.py`) |
| MongoDB | nested `api_key.key` (via `AuditRecord.to_dict`) |
| Elasticsearch | nested `api_key.key`, mapped `keyword` |

`aggregate_usage` in all four strategies gates the dimension through
`_GROUP_BY_COLUMNS = {"model", "provider", "adapter_name", "user_id",
"call_type"}` and then interpolates the requested name directly as a column or
field name. The route
(`server/routes/admin/observability.py`) constrains `group_by` with a regex
over the same set, and `costs.js` lists the same five options in its dropdown.

Two properties of the stored value shape the plan:

- **It is masked, not the key itself.** That is fine as a grouping identity —
  the mask is deterministic, so all requests made with one key collapse to one
  group. But it is only the last six characters, so two keys sharing that
  suffix would merge into a single group. Rare, but silently wrong when it
  happens.
- **It is not human-meaningful.** `"...abc123"` tells an operator nothing in a
  demo. The `api_keys` collection holds `client_name` alongside the key, so a
  label can be resolved at read time without changing the audit schema.

Records written before API key auditing existed have no value there. The group
query filters `IS NOT NULL` / equivalent, so those rows are excluded from
grouped views while still counting toward totals — the same behaviour every
other dimension already has.

## Phase 1 — Group by API key — **done** (2026-08-21)

Make `api_key` a valid `group_by` value end to end, using the masked value as
both the group key and its display label.

The one piece of real design here is that `api_key` is a *logical* dimension
name whose backend field differs per store (`api_key_value` in SQL,
`api_key.key` in Mongo and Elasticsearch). The current
`group_column = group_by if group_by in _GROUP_BY_COLUMNS else None` pattern
assumes the logical name *is* the field name. Replace the set with a mapping
from logical name to backend field in each of the four strategies, keeping the
existing five entries as identity mappings. This keeps the field name
server-controlled — the value is still never interpolated from user input.

Then widen the route's `group_by` pattern and add the option to the `costs.js`
dropdown.

- Verify: unit test per backend asserting a grouped aggregate returns rows
  keyed by the masked value, with correct `cost_usd` and request counts, and
  that rows with no API key are excluded from `groups` but still included in
  `totals`.
- Verify: a request with `group_by=api_key` returns 200 with grouped rows; an
  unknown `group_by` still 422s.
- Verify: selecting "api_key" in the panel renders the bar chart and the cost
  share donut with masked-key labels.

**As shipped.** `_GROUP_BY_COLUMNS` became `_GROUP_BY_FIELDS` in all four
strategies; the route pattern and the `costs.js` dropdown gained `api_key`; the
base-class docstring now documents the full dimension list (it was also missing
`call_type`). One addition beyond the plan: `idx_audit_logs_api_key_value` on
`audit_logs`, since every other groupable dimension already had a supporting
index — added to the SQLite and Postgres schemas, to `install/orbit.db.default`,
and documented as SQLite schema v1.13 / Postgres v1.4. No column was added.

Backend coverage is split by what can be tested without a live server:
`TestGroupByFieldMapping` asserts the field mapping for all four backends,
while the end-to-end grouped-aggregate assertions run against real SQLite.
Labels remain the raw masked value until Phase 2.

## Phase 2 — Resolve client names as labels — **done** (2026-08-21)

Turn `"...abc123"` into `"Acme Corp (...abc123)"`.

The `api_keys` collection stores the key in plaintext alongside `client_name`,
so the route can build a masked-value → `client_name` map by applying the same
`mask_api_key` call to each stored key, then decorate the grouped rows before
returning them. Resolution belongs in the route, not the storage strategies —
it is presentation, it needs a service the strategies have no handle on, and
doing it once over at most `limit_groups` rows costs nothing.

Design points to settle while implementing:

- Add the label as a separate field on each group row (e.g. `label`) rather
  than overwriting `key`, so the panel keeps a stable identity for filtering
  in Phase 3 and the response stays backward compatible.
- Fall back to the masked value when no key matches — deleted keys and
  historical records must still show their spend rather than vanishing or
  rendering as "unknown".
- If two active keys mask to the same value, the label is ambiguous; mark the
  row rather than picking one arbitrarily. Phase 4 removes the ambiguity at the
  source.
- Do not send the plaintext key to the client under any circumstance.

`costs.js` then renders `label || key`.

- Verify: unit test that a group row for a key with a known `client_name` gets
  the label, an unmatched masked value falls back to the masked string, and
  the plaintext key appears nowhere in the response.
- Verify: a suffix collision between two active keys produces the ambiguity
  marker, not a silently wrong name.

**As shipped.** Resolution lives in `server/routes/admin/observability.py`
(`_label_api_key_groups`), called only when `group_by == "api_key"`. It reads
active keys via `api_key_service.database.find_many(collection_name,
{"active": True})` — the same generic-database pattern already used by
`routes/admin/api_keys.py` — masks each plaintext key with
`mask_api_key(key, show_last=True, num_chars=6)` (matching the audit writer
exactly), and groups the resulting masked→`client_name` map by masked value.
A masked value mapping to more than one distinct `client_name` sets
`label: null, ambiguous: true` on that group row instead of guessing; no
match leaves `label` unset entirely, so `costs.js` (`label || key`) falls
back to the masked value. Lookup failure or a missing `api_key_service` is
caught and logged, never surfaces as a 500 — the endpoint just returns
unlabeled groups. Plaintext keys are never included in the response; a test
asserts this directly against the raw response body.

No schema change — labeling is a read-time join, so
`docs/sqlite-schema.md`, `docs/postgres-schema.md`, and
`install/orbit.db.default` are unaffected this phase.

## Phase 3 — Filter by API key

Grouping answers "who spends the most"; filtering answers "what does this one
client spend over time". Today the filter allowlist in each strategy is
`{provider, adapter_name, model, call_type}`, so an API key cannot be scoped.

Add `api_key` to the filter allowlist in all four strategies (reusing the same
logical-name → backend-field mapping introduced in Phase 1), and add an
`api_key` query parameter to the route. With a filter applied, the whole page —
totals, both time series, and whichever secondary grouping is selected —
narrows to that key.

In the panel, make the grouped rows clickable: selecting a row sets the filter,
and a dismissable chip shows the active scope. This is the interaction that
actually answers the demo question, so it is worth doing properly rather than
adding a second dropdown.

- Verify: unit test per backend that a filtered aggregate's totals equal the
  matching group's row from the unfiltered aggregate.
- Verify: the filter composes with the existing `provider` / `adapter_name` /
  `call_type` filters rather than replacing them.
- Verify: clicking a group row narrows the page and the chip clears it.

## Phase 4 — Stable key identity

Only now change what is written. Grouping on a six-character suffix is
correct in practice but not by construction, and a masked value cannot survive
a key being rotated or renamed.

Add a non-secret stable identifier for the key to the audit record — the key
document's `_id`, or a hash of the key — as an additive nullable column/field
across all four backends, populated going forward. Group and filter on that
identifier when present, falling back to the masked value so historical rows
keep working. Existing rows cannot be backfilled: the audit log stores only the
mask, which is exactly the ambiguity being fixed.

This also makes Phase 2's label lookup exact rather than suffix-based, and lets
a renamed client keep its history.

- Verify: unit test that new records carry the identifier, that grouping
  prefers it, and that a store containing both old and new rows produces one
  group per key rather than duplicates.
- Verify: schema migration is additive — an existing database opens and queries
  without error before any new row is written.

## Phase 5 — Per-key spend surfaced outside the Costs tab

Optional, and only worth doing once Phases 1–4 are settled. Two candidates,
in rough order of value:

- Show a key's spend over the current window on the API key management view, so
  cost is visible where keys are administered rather than only in aggregate.
- Let the existing cost-alert rules
  (`docs/roadmap/cost-alerts-and-notifications.md`) filter by API key, which
  turns per-key visibility into per-client budget enforcement. That plan's
  filters already cover `provider`, `model`, `adapter_name`, and `user_id`;
  `api_key` is the natural fifth, and it depends on Phase 4's stable
  identifier to be meaningful across a rotation.

## Out of scope

- Backfilling API key identity onto historical audit records — the data to do
  it does not exist.
- Any change to how cost itself is estimated. This plan adds a dimension to
  existing aggregates; `config/pricing.yaml` and `PricingService` are
  untouched, and cost remains an estimate rather than a provider invoice.
- Exposing per-key cost to non-admin callers. All of this stays behind the
  existing `audit.read` permission that already gates the Costs tab.
