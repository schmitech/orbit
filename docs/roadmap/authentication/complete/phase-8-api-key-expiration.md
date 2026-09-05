# API Key Expiration — Implementation Plan

## Summary

Add enforceable expiration to ORBIT API keys so newly created keys have a finite
lifetime by default, expired keys are rejected on all API-key authentication paths,
administrators can renew keys explicitly, and lifecycle changes are auditable.

The implementation must preserve existing adapter scoping, user/email allowlists,
quotas, masking, and API compatibility wherever possible.

**Roadmap position:** Phase 8. This plan is documentation-only; implementation is
deferred.

## Policy and data model

- Add `expires_at` as a UTC timestamp to API-key records.
- Add an expiration-policy marker:
  - `managed` — normal expiring key.
  - `non_expiring_exception` — explicitly approved exception.
  - `legacy_migration` — existing key during rollout.
- New keys default to a 90-day lifetime.
- New keys may specify an earlier expiration, but not later than 365 days from creation.
- Non-expiring keys require an explicit admin-only request, a non-empty justification,
  and an audit event.
- Existing keys are grandfathered during rollout but receive an expiration date 90
  days after migration. No existing key remains permanently non-expiring by default.
- Store and compare expiration timestamps in UTC. Treat a key as expired when
  `now >= expires_at`.
- Retain expired records for audit, reporting, and investigation; do not delete them
  automatically.

Update SQLite/PostgreSQL schemas and schema documentation. MongoDB requires no
structural migration, but existing documents must receive the migration fields when
the service initializes.

## Validation and service behavior

Update `ApiKeyService` and the central `validate_api_key()` path:

- Reject expired keys with the same generic invalid-key response used for disabled or
  unknown keys.
- Check expiration before adapter resolution, user/email allowlists, quotas, and
  downstream dispatch.
- Ensure an expired explicit key cannot fall through to `api_keys.allow_default`.
- Preserve `active: false` deactivation independently from expiration.
- Return `expires_at`, `expiration_policy`, `expired`, and optionally `days_remaining`
  from status, list, and detail operations.
- Apply the check consistently to HTTP inference, files, voice/A2A paths, message-queue
  consumers, admin API-key authentication, and any direct service call that authenticates
  an API key.
- Avoid per-request audit writes for expired-key rejections to prevent log flooding;
  emit a masked warning or metric and retain lifecycle audit events.

## Admin, CLI, and API interfaces

Extend API-key creation and management:

- Add optional `expires_at` and explicit non-expiring-exception fields to the create
  request.
- If no expiration is supplied, assign `now + 90 days`.
- Reject malformed, timezone-naive, past, or over-limit expiration dates.
- Add an admin expiration-update/renewal operation accepting a new absolute
  `expires_at` or an approved non-expiring exception.
- Require the existing API-key management permission for renewal and expiration updates.
- Record the actor, key ID, previous expiration, new expiration, policy, and justification.
- Extend admin list/detail/status responses and the UI with expiration state, sortable
  expiration date, expired/expiring-soon indicators, and a renewal action.
- Add CLI support for creating, renewing, and listing expired or soon-to-expire keys.
- Never expose full API keys in list responses or audit records.

Use lifecycle audit events such as:

- `admin.api_key.create`
- `admin.api_key.expiration.update`
- `admin.api_key.expiration.exception`
- `admin.api_key.deactivate`
- `admin.api_key.delete`

## Configuration and migration

Add API-key policy settings to the default configuration:

```yaml
api_keys:
  default_lifetime_days: 90
  max_lifetime_days: 365
  legacy_migration_lifetime_days: 90
  allow_non_expiring_exceptions: true
  expiration_warning_days: 14
```

Migration behavior:

- On service initialization, detect API-key records without expiration metadata.
- Set `expiration_policy: legacy_migration`.
- Set `expires_at` to the migration timestamp plus 90 days.
- Make the migration idempotent and safe across multiple workers.
- Do not rewrite already-managed expiration dates.
- Log the number of migrated keys and the earliest expiration date.
- Surface migration results in admin status or observability output.

## Testing and acceptance criteria

Add unit, integration, and route-level coverage for:

- validity immediately before expiration;
- rejection exactly at and after `expires_at`;
- UTC and timezone-aware date handling;
- default 90-day expiration and 365-day maximum validation;
- past and malformed dates;
- justified non-expiring exceptions;
- rejection across every API-key authentication path;
- no fallback to default-adapter behavior for expired explicit keys;
- independent disabled and expired states;
- idempotent legacy-key migration;
- renewal of active and expired keys;
- unauthorized renewal rejection;
- audit records containing no raw key or secret material;
- correct list/detail/status metadata;
- CLI and admin UI compatibility;
- SQLite, PostgreSQL, and MongoDB behavior;
- preservation of existing API-key, quota, allowlist, adapter-scoping, and audit tests.

Acceptance requires:

- every newly created managed key has an expiration date;
- every expired API key is rejected before request dispatch;
- every non-expiring exception is explicit, justified, permission-gated, and auditable;
- every existing key receives a finite migration expiration;
- `ruff check server/` and relevant authentication/admin test suites pass.

## Assumptions and defaults

- Default lifetime: 90 days.
- Maximum normal lifetime: 365 days.
- Existing-key migration grace period: 90 days.
- Expiration is enforced lazily during validation; records are retained.
- Renewal is manual and administrator-controlled; automatic renewal is out of scope.
- API-key storage remains unchanged; key confidentiality is a separate hardening effort.
- Expiration enforcement contributes to authenticator-management controls but does not
  alone satisfy the complete NIST requirement without deployment evidence, monitoring,
  review, and lifecycle procedures.

## Related documentation

- [API key management](../../api-keys.md)
- [SQLite schema](../../sqlite-schema.md)
- [Authentication guide](../../authentication.md)
- [RBAC architecture](../../rbac-architecture.md)
