# PostgreSQL Database Schema

This document describes the PostgreSQL database schema used by Orbit when configured with the PostgreSQL backend.

## Overview

Orbit uses PostgreSQL as an alternative backend to MongoDB and SQLite for data persistence. The logical schema is identical across all three backends (same tables, same columns, same semantics) — `PostgresService` and `SQLiteService` share the same `_schema`/`_indexes` shape and the same `DatabaseService` abstraction, so anything that isn't Postgres-specific below is also documented in more depth in [`docs/sqlite-schema.md`](sqlite-schema.md).

The database contains the following tables:

- `users` - User accounts and authentication
- `sessions` - Active user sessions
- `api_keys` - API keys for authentication
- `system_prompts` - System prompts for chat
- `chat_history` - Chat message history
- `conversation_threads` - Conversation threading for intent adapters
- `thread_datasets` - Database fallback storage for conversation thread datasets
- `uploaded_files` - Uploaded file metadata for file adapter workflows
- `file_chunks` - Chunk metadata for processed uploaded files
- `audit_logs` - Audit trail records for conversation logging and compliance
- `audit_admin_logs` - Audit trail records for admin/auth mutations (user CRUD, API-key management, config changes, login/logout, etc.)
- `feedback` - User feedback (thumbs up/down) on chat responses
- `system_state` - Small durable key/value store for cross-process server coordination state (e.g. the server pause flag)

## Connection Configuration

The PostgreSQL connection is configured in `config/config.yaml`:

```yaml
internal_services:
  backend:
    type: "postgres"  # sqlite, mongodb, or postgres
    postgres:
      host: ${INTERNAL_SERVICES_POSTGRES_HOST}
      port: ${INTERNAL_SERVICES_POSTGRES_PORT}
      database: ${INTERNAL_SERVICES_POSTGRES_DB}
      username: ${INTERNAL_SERVICES_POSTGRES_USERNAME}
      password: ${INTERNAL_SERVICES_POSTGRES_PASSWORD}
      sslmode: ${INTERNAL_SERVICES_POSTGRES_SSLMODE}
```

Unlike SQLite, PostgreSQL requires a running server — the values above are typically supplied via environment variables (`.env`) rather than hardcoded in `config.yaml`.

`PostgresService` connects with `psycopg` (psycopg3), a single shared connection guarded by a lock, mirroring `SQLiteService`'s architecture — the internal-services database has modest throughput needs, and a single connection makes `execute_transaction` trivially correct.

## Tables

All tables use the same `TEXT PRIMARY KEY` (UUID v4 string) convention as the SQLite backend — there is no `SERIAL`/`BIGSERIAL` auto-increment key anywhere in this schema, since IDs are generated application-side and must be portable across backends.

### users

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    roles TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT,
    provider TEXT,
    external_id TEXT,
    email TEXT
)
```

**Indexes:** `idx_users_username` on `username`

See [`docs/sqlite-schema.md#users`](sqlite-schema.md#users) for field descriptions — identical across backends.

---

### sessions

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    expires TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

**Indexes:** `idx_sessions_token` on `token`; `idx_sessions_expires` on `expires`

---

### api_keys

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    api_key TEXT UNIQUE NOT NULL,
    client_name TEXT NOT NULL,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    adapter_name TEXT,
    system_prompt_id TEXT,
    quota_daily_limit INTEGER,
    quota_monthly_limit INTEGER,
    quota_throttle_enabled INTEGER,
    quota_throttle_priority INTEGER
)
```

**Indexes:** `idx_api_keys_api_key` on `api_key`

---

### system_prompts

```sql
CREATE TABLE IF NOT EXISTS system_prompts (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    prompt TEXT NOT NULL,
    version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

**Indexes:** `idx_system_prompts_name` on `name`

---

### chat_history

```sql
CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    api_key TEXT,
    metadata_json TEXT,
    message_hash TEXT,
    token_count INTEGER
)
```

**Indexes:**
- `idx_chat_history_session` on `(session_id, timestamp)`
- `idx_chat_history_user` on `(user_id, timestamp)`
- `idx_chat_history_timestamp` on `timestamp`
- `idx_chat_history_api_key` on `api_key`
- `idx_chat_history_hash` (UNIQUE) on `(session_id, message_hash)`

---

### conversation_threads

```sql
CREATE TABLE IF NOT EXISTS conversation_threads (
    id TEXT PRIMARY KEY,
    parent_message_id TEXT NOT NULL,
    parent_session_id TEXT NOT NULL,
    thread_session_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    query_context TEXT NOT NULL,
    dataset_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    metadata_json TEXT
)
```

**Indexes:**
- `idx_conversation_threads_parent_message` on `parent_message_id`
- `idx_conversation_threads_parent_session` on `parent_session_id`
- `idx_conversation_threads_thread_session` on `thread_session_id`
- `idx_conversation_threads_expires_at` on `expires_at`

---

### thread_datasets

```sql
CREATE TABLE IF NOT EXISTS thread_datasets (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    dataset_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

**Indexes:** `idx_thread_datasets_thread_id` on `thread_id`; `idx_thread_datasets_expires_at` on `expires_at`

---

### uploaded_files

```sql
CREATE TABLE IF NOT EXISTS uploaded_files (
    id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    upload_timestamp TEXT,
    processing_status TEXT,
    storage_key TEXT,
    chunk_count INTEGER DEFAULT 0,
    vector_store TEXT,
    collection_name TEXT,
    storage_type TEXT DEFAULT 'vector',
    metadata_json TEXT,
    embedding_provider TEXT,
    embedding_dimensions INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP::TEXT
)
```

**Indexes:** `idx_uploaded_files_api_key` on `api_key`; `idx_uploaded_files_processing_status` on `processing_status`

> Note the `DEFAULT CURRENT_TIMESTAMP::TEXT` cast — Postgres's `CURRENT_TIMESTAMP` is a `timestamptz`, and the column is `TEXT` for cross-backend consistency with SQLite/MongoDB, so it's cast explicitly. SQLite's equivalent column uses a bare `DEFAULT CURRENT_TIMESTAMP`, which SQLite stores as text natively.

---

### file_chunks

```sql
CREATE TABLE IF NOT EXISTS file_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_index INTEGER,
    vector_store_id TEXT,
    collection_name TEXT,
    chunk_metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP::TEXT,
    FOREIGN KEY (file_id) REFERENCES uploaded_files(id)
)
```

**Indexes:** `idx_file_chunks_file_id` on `file_id`

---

### audit_logs

```sql
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    response_compressed INTEGER NOT NULL DEFAULT 0,
    provider TEXT,
    blocked INTEGER NOT NULL DEFAULT 0,
    ip TEXT,
    ip_type TEXT,
    ip_is_local INTEGER DEFAULT 0,
    ip_source TEXT,
    ip_original_value TEXT,
    api_key_value TEXT,
    api_key_timestamp TEXT,
    session_id TEXT,
    user_id TEXT,
    adapter_name TEXT,
    model TEXT
)
```

**Indexes:**
- `idx_audit_logs_timestamp` on `timestamp`
- `idx_audit_logs_session_id` on `session_id`
- `idx_audit_logs_user_id` on `user_id`
- `idx_audit_logs_blocked` on `blocked`
- `idx_audit_logs_provider` on `provider`
- `idx_audit_logs_adapter_name` on `adapter_name`
- `idx_audit_logs_model` on `model`

**Configuration:** set `internal_services.audit.storage_backend: "database"` (or `"postgres"` explicitly) in `config/config.yaml` — see [`docs/sqlite-schema.md#audit_logs`](sqlite-schema.md#audit_logs) for the full config block and response-compression details, which apply identically here.

---

### audit_admin_logs

Stores audit trail records for privileged operations on `/admin/*` and `/auth/*` endpoints.

```sql
CREATE TABLE IF NOT EXISTS audit_admin_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    actor_username TEXT,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    ip TEXT,
    ip_type TEXT,
    ip_is_local INTEGER DEFAULT 0,
    ip_source TEXT,
    ip_original_value TEXT,
    user_agent TEXT,
    error_message TEXT,
    request_summary TEXT
)
```

**Indexes:**
- `idx_audit_admin_logs_timestamp` on `timestamp`
- `idx_audit_admin_logs_actor_id` on `actor_id`
- `idx_audit_admin_logs_event_type` on `event_type`
- `idx_audit_admin_logs_resource_type` on `resource_type`
- `idx_audit_admin_logs_success` on `success`

See [`docs/sqlite-schema.md#audit_admin_logs`](sqlite-schema.md#audit_admin_logs) for field descriptions and the `admin_events` config block.

---

### feedback

```sql
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT,
    feedback_type TEXT NOT NULL,
    adapter_name TEXT,
    comment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

**Indexes:**
- `idx_feedback_message_session` (UNIQUE) on `(message_id, session_id)`
- `idx_feedback_session` on `session_id`
- `idx_feedback_type` on `feedback_type`
- `idx_feedback_adapter` on `adapter_name`

---

### system_state

Small durable key/value store for cross-process coordination state that must survive cache flushes and worker restarts — currently just the server pause flag set via `POST /admin/pause` / `POST /admin/resume` (see `server/services/pause_state.py`). Not a cache: rows here are never cleared on startup or by any cache-invalidation path.

```sql
CREATE TABLE IF NOT EXISTS system_state (
    id TEXT PRIMARY KEY,
    value INTEGER
)
```

**Fields:**
- `id` (TEXT, PK): Row key. Currently one row: `server_paused`
- `value` (INTEGER): Boolean value for the row (1=true, 0=false)

**Indexes:** none — the single-row PK lookup by `id` doesn't need one.

---

## Data Types

Field-level type/format conventions (ID format, timestamps, booleans, JSON columns) are identical to the SQLite backend — see [`docs/sqlite-schema.md#data-types`](sqlite-schema.md#data-types). The one Postgres-specific wrinkle is the `CURRENT_TIMESTAMP::TEXT` cast noted under `uploaded_files`/`file_chunks` above.

## Schema Migration

Both `_schema` (table definitions) and any newly-added columns are applied automatically on every server startup, in `PostgresService._create_tables()`:

1. `CREATE TABLE IF NOT EXISTS ...` runs for every table on every startup — safe to run repeatedly, and this is what creates any *new* table (like `system_state` above) on a database that predates it. No manual migration step is needed when Orbit adds a table.
2. `_migrate_table_schema()` then runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` for every column in the schema. Unlike SQLite (which has to inspect `PRAGMA table_info` first because it lacks `ADD COLUMN IF NOT EXISTS`), Postgres supports the idempotent form directly, so this step doesn't need a pre-check.

Both steps only ever *add* — nothing here drops or alters existing columns, so it's safe to run against a production database with no separate migration tooling required.

## Maintenance

### Database Inspection

```bash
# Connect with psql
psql -h $INTERNAL_SERVICES_POSTGRES_HOST -p $INTERNAL_SERVICES_POSTGRES_PORT \
     -U $INTERNAL_SERVICES_POSTGRES_USERNAME -d $INTERNAL_SERVICES_POSTGRES_DB

# List all tables
\dt

# Show table schema
\d users

# Query data
SELECT * FROM users;
```

### Backup and Restore

```bash
# Backup
pg_dump -h $INTERNAL_SERVICES_POSTGRES_HOST -U $INTERNAL_SERVICES_POSTGRES_USERNAME \
        -d $INTERNAL_SERVICES_POSTGRES_DB -F c -f orbit_backup.dump

# Restore
pg_restore -h $INTERNAL_SERVICES_POSTGRES_HOST -U $INTERNAL_SERVICES_POSTGRES_USERNAME \
           -d $INTERNAL_SERVICES_POSTGRES_DB orbit_backup.dump
```

### Performance Considerations

PostgreSQL is the recommended backend for:
- Production and high-traffic deployments
- Multi-server / horizontally-scaled setups
- Applications with heavy `chat_history`/`audit_logs` growth, where PostgreSQL's indexing and concurrent-write handling outperform SQLite's single-writer model

For development, testing, or small single-server deployments, SQLite avoids the operational overhead of a separate database server — see [`docs/sqlite-schema.md`](sqlite-schema.md).

## Security

Password storage (PBKDF2, 600,000 iterations, SHA-256) and API key handling are identical across backends — see [`docs/sqlite-schema.md#security`](sqlite-schema.md#security). Additionally for Postgres:

- Use `sslmode` (`require` or stricter) in production rather than `prefer`/`disable`.
- Restrict database user permissions to only the schema Orbit needs; avoid using a Postgres superuser for the application connection.

## Version History

- **v1.0** (2026-07-22): Initial PostgreSQL backend documentation
  - Schema matches SQLite v1.4, including `system_state`
  - See [`docs/sqlite-schema.md#version-history`](sqlite-schema.md#version-history) for the full per-table history, since both backends have shared the same schema since PostgreSQL support was added
