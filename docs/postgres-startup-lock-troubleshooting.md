# Troubleshooting: PostgreSQL Startup Hangs / Statement Timeouts

Guide for diagnosing ORBIT startup hangs against a PostgreSQL internal-services
backend (`internal_services.backend.type: postgres`), where the server appears
stuck creating/migrating tables, or fails with `canceling statement due to
statement timeout`.

## Symptom

Startup logs stop partway through table creation, eventually followed by an
error like:

```
2026-07-04 14:08:41,898 - services.postgres_service - DEBUG - Created table: users
2026-07-04 14:08:42,833 - services.postgres_service - DEBUG - Created table: sessions
2026-07-04 14:08:43,378 - services.postgres_service - DEBUG - Created table: api_keys
2026-07-04 14:10:43,460 - services.postgres_service - ERROR - Failed to ensure column 'id' on table 'api_keys': canceling statement due to statement timeout
```

The gap before the error (here, ~2 minutes) matches your Postgres/Supabase
`statement_timeout` — the server isn't doing 2 minutes of work, it's **blocked
waiting on a lock** until the timeout cancels the statement.

## Root cause

On every startup, `PostgresService._create_tables()`
(`server/services/postgres_service.py`) runs `CREATE TABLE IF NOT EXISTS` for
each table, then `_migrate_table_schema()` runs
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` for every column in the schema
— including columns that already exist. This is intentionally idempotent, but
Postgres still requires an **`ACCESS EXCLUSIVE`** lock on the table for any
`ALTER TABLE` statement, even a no-op `IF NOT EXISTS` check.

If any other session holds so much as an `ACCESS SHARE` lock on that table via
an open transaction, the `ALTER TABLE` queues behind it and blocks until
`statement_timeout` cancels it.

The most common source of that lingering lock is an **idle-in-transaction
session** — a connection that ran a read query and never committed or rolled
back. Versions of ORBIT prior to the fix in
[`postgres_service.py`](../server/services/postgres_service.py) had this bug:
`_execute_sql_fetchone`, `_execute_sql_fetchall`, and `_table_exists` executed
reads but never called `.commit()`. Since the shared Postgres connection isn't
in autocommit mode, every read left its transaction open indefinitely unless
some later write happened to land on the same connection and commit it. On a
low-write deployment (e.g. `/auth/me` or API-key lookups with little other DB
activity), that transaction — and its lock — could sit open for hours,
eventually blocking the next startup's schema migration.

A second, unrelated contributor is **running more than one ORBIT process**
against the same database at once (e.g. a previous `python3 server/main.py`
that didn't fully exit before you started a new one). Two processes racing
`_create_tables()`/migration on the same tables compete for the same
`ACCESS EXCLUSIVE` locks.

## Diagnosis

### 1. Check for duplicate local ORBIT processes

```bash
ps aux | grep "server/main.py" | grep -v grep
```

If you see more than one, stop all of them before restarting:

```bash
kill <pid> <pid>
# if a process doesn't exit after a few seconds:
kill -9 <pid>
```

### 2. Check for blocking sessions on Postgres

Run this against your database (Supabase SQL editor, `psql`, or any client):

```sql
SELECT pid, state, query, xact_start, state_change
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid()
  AND state != 'idle'
ORDER BY xact_start;
```

Look for a row with `state = 'idle in transaction'` and an old `xact_start` —
that's a stuck transaction holding a lock. A `query` like
`SELECT * FROM api_keys WHERE "api_key" = $1 LIMIT 1` that's been open for
minutes or hours (rather than milliseconds) is the signature of this issue.

### 3. Confirm no locks remain

```sql
SELECT pid, state, query, xact_start, state_change
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid()
  AND state != 'idle'
ORDER BY xact_start;
```

`Success. No rows returned` (or only your own session) means it's clear.

## Fix

1. **Terminate any stuck sessions** found in step 2:

   ```sql
   SELECT pg_terminate_backend(<pid>);
   ```

2. **Make sure no duplicate ORBIT processes are running locally** (step 1).

3. **Restart ORBIT.** With the connection-commit fix in place, reads no longer
   leave transactions open, so this class of lock shouldn't recur under normal
   operation.

## Prevention

- Always stop ORBIT cleanly (`./bin/orbit.sh stop`, or wait for a graceful
  shutdown) before starting a new instance, rather than starting a second
  process on top of a still-running one.
- If you're running ORBIT behind a process manager or during development with
  frequent restarts, periodically check `ps aux | grep server/main.py` to make
  sure you don't accumulate stray processes.
- If you see this again on a fixed version of ORBIT, it likely means some
  *other* application sharing the same Postgres database (or database role) is
  leaving transactions open — check `pg_stat_activity` for sessions from
  clients other than ORBIT.

## Related

- [SQLite Schema Reference](sqlite-schema.md) — the logical schema
  (`users`, `sessions`, `api_keys`) that both the SQLite and PostgreSQL
  backends implement.
- [Service Singleton Configuration Guide](service_singleton_configuration_guide.md) —
  how ORBIT caches/reuses backend service instances.
