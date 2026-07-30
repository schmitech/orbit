# Cost Alerts and Notifications — Implementation Plan

## Summary

Build a transport-neutral cost-alerting system on ORBIT's existing audit cost
aggregates.

The first release will:

- Support webhook notifications.
- Manage rules through YAML.
- Evaluate global or exact-match filtered budgets by provider, model, adapter,
  or user.
- Support daily and monthly calendar budgets in a configured timezone.
- Notify once per threshold, coalescing multiple newly crossed thresholds into
  the highest alert.
- Persist delivery state and retry failures safely across restarts and workers.
- Treat calculated spend as a lower bound when usage is unpriced or unreported.

## Configuration and interfaces

Add an imported `config/notifications.yaml`, mirrored in
`install/default-config`, with alerts disabled by default:

```yaml
notifications:
  transports:
    operations:
      type: webhook
      url: ${ORBIT_COST_ALERT_WEBHOOK_URL:-}
      signing_secret: ${ORBIT_COST_ALERT_WEBHOOK_SECRET:-}
      timeout_seconds: 10
      max_attempts: 5
      allow_insecure_http: false

cost_alerts:
  enabled: false
  timezone: UTC
  evaluation_interval_seconds: 60
  rules:
    - id: monthly-total
      enabled: true
      period: month
      budget_usd: 500
      thresholds_percent: [80, 100, 120]
      filters: {}
      transports: [operations]
```

Rules may use exact-match `provider`, `model`, `adapter_name`, and `user_id`
filters. Validate:

- Unique rule and transport IDs.
- Positive budgets.
- Unique, ascending, positive thresholds.
- Supported periods.
- Referenced transports.
- HTTPS webhook URLs.
- Required secrets whenever the feature is enabled.

Define a transport contract such as
`NotificationTransport.send(notification)`, with a registry or factory keyed by
transport type. Implement only `WebhookTransport` initially, while preserving
the interface for a later SMTP email transport.

Use a versioned webhook payload containing:

- Stable event and delivery IDs.
- Rule, budget period, timezone, and filters.
- Budget, threshold, known spend, and percentage consumed.
- All thresholds crossed during the evaluation.
- Request, unpriced-request, and unreported-request counts.
- A flag indicating that known spend is a lower bound.
- Evaluation and period timestamps.

Send an idempotency header and an HMAC-SHA256 signature over the exact request
body.

## Implementation design

### Service lifecycle

- Add a lifecycle-managed `CostAlertService` after database, audit, pricing,
  and cache initialization.
- Run evaluation outside request handling.
- Cancel background tasks and release delivery leases during graceful
  shutdown.
- Do not create tasks or make outbound requests when cost alerts are disabled.
- **Restart required for rule changes in v1.** `cost_alerts`/`notifications`
  config is loaded at startup, consistent with `pricing.yaml` and every other
  imported config file — no hot-reload path. Editing rules or transports
  requires a server restart to take effect; document this plainly in the
  admin-facing docs so operators don't expect a `reload-adapters`-style
  live update. Revisit hot-reload only if this becomes a real operational
  pain point post-launch.

### Cost evaluation

- Calculate calendar-day and calendar-month boundaries with `zoneinfo`.
- Query the existing audit aggregate for each enabled rule.
- **New backend work required**: `aggregate_usage()` currently accepts only
  `provider`/`adapter_name`/`model` filters (see `admin_routes.py`'s
  `get_observability_usage` and each strategy's signature) — `user_id` is not
  a supported filter today. **Decision: support `user_id` filtering on all
  four audit backends in v1 — SQLite, Postgres, MongoDB, and Elasticsearch.**
  Since per-user/per-provider/per-adapter filtered budgets are a stated v1
  requirement, an ES-backed deployment silently losing that capability would
  be a real functional gap, not just a documented limitation. Track this as
  its own subtask with backend-specific tests for each.
- Add a strict aggregation path for alerts so backend failures are recorded as
  evaluation failures instead of appearing as zero spend.
- Compare known `cost_usd` against each configured percentage of `budget_usd`.
- If multiple unseen thresholds are crossed in one evaluation, enqueue only
  the highest notification and persist the lower thresholds as
  coalesced/satisfied.
- Reset threshold state naturally when a new calendar period begins.
- Never estimate missing costs. Continue evaluating known spend, label it as a
  lower bound, and include pricing-coverage gaps in the payload.

### Durable delivery

Persist threshold and delivery records in the shared application database,
supporting SQLite, PostgreSQL, and MongoDB (the internal-services backends —
Elasticsearch is an audit-only backend and never stores this outbox state
regardless of which backend audit events use). Use deterministic IDs derived
from the rule, period, threshold, and transport.

Implement an outbox with these states:

- `pending`
- `delivering`
- `retry`
- `delivered`
- `dead`
- `coalesced`

Store the attempt count, next-attempt time, lease expiry, response status, and
sanitized error details.

Atomically claim deliveries so multiple workers cannot send the same event
concurrently. Reclaim expired leases after worker failure. Delivery remains
at-least-once; webhook receivers should use the idempotency key to collapse the
narrow send-before-ack failure window.

Treat network errors, timeouts, HTTP 408/429, and HTTP 5xx responses as
retryable. Respect a bounded `Retry-After` value when provided; otherwise use
exponential backoff. Mark other HTTP 4xx responses permanently failed.

### Webhook security and observability

- Require HTTPS unless `allow_insecure_http` is explicitly enabled.
- Sign the exact request body with the configured HMAC-SHA256 secret.
- Never log webhook credentials, authorization headers, or signatures.
- Add structured logs for evaluations, threshold crossings, delivery
  attempts, retries, failures, and dead-lettered notifications.
- Add Prometheus counters for evaluations and deliveries, labelled by status
  and transport without exposing rule secrets or recipient URLs.

## Test plan

### Configuration

- Enabled and disabled configurations.
- Environment-resolved URLs and secrets.
- Duplicate IDs, malformed budgets, invalid thresholds, unsupported periods,
  missing transports, and insecure URLs.

### Evaluation

- Daily and monthly boundaries.
- Configured timezone and daylight-saving transitions.
- Period resets.
- Global and exact provider, model, adapter, and user filters.
- One event per threshold and period.
- Multi-threshold jump coalescing.
- Known-spend alerts containing unpriced or unreported requests.
- Aggregate-backend failures that must not be interpreted as zero spend.

### Delivery

- Versioned payload serialization.
- HMAC signatures and idempotency headers.
- HTTP 2xx success.
- Permanent HTTP 4xx failures.
- HTTP 408/429/5xx retries.
- `Retry-After`, timeouts, exponential backoff, and maximum attempts.
- Lease recovery after worker termination.
- Restart deduplication and concurrent-worker claims.
- Secret and header redaction in logs.

### Storage and compatibility

- Backend contract tests for SQLite, PostgreSQL, and MongoDB outbox state.
- Aggregate-filter tests (including the new `user_id` filter) for all four
  supported audit backends — SQLite, Postgres, MongoDB, and Elasticsearch.
  Elasticsearch has no outbox-state tests (it never stores that data — see
  "Durable delivery" above) but does need `user_id`-filter test coverage.
- Schema creation and additive migrations for existing installations.
- Existing cost tracking and observability behavior remains unchanged when
  alerts are disabled.

## Assumptions

- Webhook is the only initial transport; email is a future transport using the
  same interface and outbox.
- Rules are YAML-managed with no admin CRUD API or UI in the first release.
- Budgets use estimated local pricing, not provider billing APIs.
- Crossing a budget sends notifications but does not block inference requests.
- Cost alerting requires inference audit events and cost tracking to be enabled.

## Known gaps in v1

- **Evaluation cadence vs. real-time spend.** A 60s poll interval means a
  runaway spend spike (e.g. a bug looping an expensive model call) can exceed
  a configured budget by a meaningful margin before the first alert fires.
  This is an accepted tradeoff for a notification feature (vs. a hard spend
  cap), not an oversight — document it in user-facing docs so operators don't
  assume near-real-time enforcement.
- **No hard spend enforcement (deliberate v1 decision).** Crossing a budget
  only notifies — it never blocks or throttles inference. "Budget alert"
  language can imply enforcement to some readers, so this is called out
  explicitly: notification-only is the intended v1 scope, not a gap to
  revisit before implementation.
- **Rule/transport changes require a restart.** No hot-reload path for
  `cost_alerts`/`notifications` config in v1 (see "Service lifecycle" above)
  — consistent with `pricing.yaml` and other imported config, but worth
  surfacing here as a deliberate v1 constraint rather than only in the
  lifecycle section.
