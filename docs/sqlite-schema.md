# SQLite Database Schema

This document describes the SQLite database schema used by Orbit when configured with the SQLite backend.

## Overview

Orbit uses SQLite as an alternative backend to MongoDB for data persistence. The SQLite database contains the following tables:

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
- `adapter_reload_state` - Durable generation counters propagating adapter/template reloads across `performance.workers` processes

## Database File Location

The database file location is configured in `config/config.yaml`:

```yaml
internal_services:
  backend:
    type: "sqlite"
    sqlite:
      database_path: "orbit.db"  # Default: orbit.db in project root
```

## Tables

### users

Stores user account information for authentication.

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

**Fields:**
- `id` (TEXT, PK): Unique user ID (UUID)
- `username` (TEXT, UNIQUE): Username for login. For externally-authenticated users this is the synthetic `"{provider}:{external_id}"` key (e.g. `entra:<sub>`, `auth0:<sub>`)
- `password` (TEXT): Hashed password (PBKDF2). Externally-authenticated users store a random unusable hash — they can only sign in through their identity provider
- `role` (TEXT): Primary user role (e.g., "admin", "user")
- `roles` (TEXT): JSON array of additional roles assigned to the user (optional)
- `active` (INTEGER): Whether user is active (1=active, 0=inactive)
- `created_at` (TEXT): ISO format timestamp of account creation
- `last_login` (TEXT): ISO format timestamp of last login
- `provider` (TEXT): External identity provider that authenticated the user (`entra` or `auth0`); `NULL` for built-in username/password users
- `external_id` (TEXT): The provider's immutable subject (`sub`) claim; `NULL` for built-in users
- `email` (TEXT): Email/`preferred_username` claim captured from the provider (for display/audit); `NULL` for built-in users

**Indexes:**
- `idx_users_username` on `username`

> **External identity providers.** The `provider`, `external_id`, and `email` columns support just-in-time provisioning of users who authenticate via Microsoft Entra ID or Auth0 (see `docs/authentication.md`). They are nullable and added to pre-existing databases automatically by the additive-column migration on startup (`_migrate_table_schema`). Uniqueness of external users is enforced through the existing `UNIQUE(username)` index using the `provider:external_id` username.

---

### sessions

Stores active user sessions for authentication.

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

**Fields:**
- `id` (TEXT, PK): Unique session ID (UUID)
- `token` (TEXT, UNIQUE): Session token
- `user_id` (TEXT): ID of the user this session belongs to
- `username` (TEXT): Username for quick reference
- `expires` (TEXT): ISO format timestamp when session expires
- `created_at` (TEXT): ISO format timestamp of session creation

**Indexes:**
- `idx_sessions_token` on `token`
- `idx_sessions_expires` on `expires`

---

### user_blacklist

Stores pattern-based identity denial rules, evaluated on every authentication.

```sql
CREATE TABLE IF NOT EXISTS user_blacklist (
    id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    reason TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
)
```

**Fields:**
- `id` (TEXT, PK): Unique rule ID (UUID)
- `pattern` (TEXT): Lowercased match pattern; `*` and `?` are wildcards (e.g. `*@spam-domain.com`)
- `entry_type` (TEXT): Identity field the pattern matches — `email`, `user_id`, or `username`
- `reason` (TEXT, nullable): Free-text operator note
- `created_by` (TEXT, nullable): Username of the administrator who added the rule
- `created_at` (TEXT): ISO format timestamp of rule creation

**Indexes:**
- `idx_user_blacklist_entry_type_pattern` unique on `(entry_type, pattern)` — created by
  `AuthService.initialize()` via `create_index` rather than declared in the backend's
  `_indexes` map, so MongoDB gets the same constraint (it never reads those SQL definitions)

---

### api_keys

Stores API keys for authentication and adapter configuration.

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
    quota_throttle_priority INTEGER,
    allowed_user_ids TEXT,
    allowed_emails TEXT
)
```

**Fields:**
- `id` (TEXT, PK): Unique API key ID (UUID)
- `api_key` (TEXT, UNIQUE): The actual API key string
- `client_name` (TEXT): Name of the client/application
- `notes` (TEXT): Optional notes about the API key
- `active` (INTEGER): Whether key is active (1=active, 0=inactive)
- `created_at` (TEXT): ISO format timestamp of creation
- `adapter_name` (TEXT): Associated adapter name (optional)
- `system_prompt_id` (TEXT): Associated system prompt ID (optional)
- `quota_daily_limit` (INTEGER): Optional per-key daily quota override
- `quota_monthly_limit` (INTEGER): Optional per-key monthly quota override
- `quota_throttle_enabled` (INTEGER): Optional per-key throttling override (1=true, 0=false)
- `quota_throttle_priority` (INTEGER): Optional per-key throttling priority override
- `allowed_user_ids` (TEXT): JSON-encoded array of ORBIT `users.id` values permitted to use this key. `NULL`/empty = unrestricted (any valid key works, current behavior). Matched against the authenticated caller's internal user id, which for external Entra/Auth0 users is assigned on first JIT-provisioned login (see `users.provider`/`external_id`)
- `allowed_emails` (TEXT): JSON-encoded array of normalized email addresses permitted to use this key before the user has logged in. A caller matching either this list or `allowed_user_ids` is authorized. Entries are lowercased and retained after login; an IdP email change will no longer match, so use user-ID restrictions for durable sensitive access.

**Indexes:**
- `idx_api_keys_api_key` on `api_key`

---

### system_prompts

Stores system prompts used for chat completions.

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

**Fields:**
- `id` (TEXT, PK): Unique prompt ID (UUID)
- `name` (TEXT, UNIQUE): Unique name for the prompt
- `prompt` (TEXT): The actual prompt text
- `version` (TEXT): Version identifier
- `created_at` (TEXT): ISO format timestamp of creation
- `updated_at` (TEXT): ISO format timestamp of last update

**Indexes:**
- `idx_system_prompts_name` on `name`

---

### chat_history

Stores chat message history.

```sql
CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    api_key TEXT,
    api_key_hash TEXT,
    metadata_json TEXT,
    message_hash TEXT,
    token_count INTEGER
)
```

**Fields:**
- `id` (TEXT, PK): Unique message ID (UUID)
- `session_id` (TEXT): Session identifier for grouping messages
- `role` (TEXT): Message role ("user", "assistant", "system")
- `content` (TEXT): Message content
- `timestamp` (TEXT): ISO format timestamp of message
- `user_id` (TEXT): Optional user ID
- `api_key` (TEXT): Optional API key used, stored **masked** (`...` + last 6 characters, via `mask_api_key`). Display/audit only — never use it for authorization
- `api_key_hash` (TEXT): Hex-encoded SHA-256 of the full API key that created the message (via `hash_api_key`). This is the session-ownership binding enforced on deletion; see **Session ownership** below. `NULL` for rows written before v1.8
- `metadata_json` (TEXT): JSON-encoded metadata
- `message_hash` (TEXT): Hash for deduplication
- `token_count` (INTEGER): Token count for the message (used for conversation history management)

**Indexes:**
- `idx_chat_history_session` on `(session_id, timestamp)`
- `idx_chat_history_user` on `(user_id, timestamp)`
- `idx_chat_history_timestamp` on `timestamp`
- `idx_chat_history_api_key` on `api_key`
- `idx_chat_history_api_key_hash` on `(session_id, api_key_hash)`
- `idx_chat_history_hash` (UNIQUE) on `(session_id, message_hash)`

**Session ownership:**

`DELETE /admin/chat-history/{session_id}` and `DELETE /admin/conversations/{session_id}` are authenticated by `X-API-Key` but are *not* admin-gated, so a valid key must additionally be proven to own the session it targets. `ChatHistoryService._api_key_owns_session()` resolves that by comparing `hash_api_key(caller_key)` against the session's stored `api_key_hash`; a mismatch returns HTTP 403 and deletes nothing. Validating that a key is merely active is not sufficient — without this check any tenant's key can delete any other tenant's session (cross-tenant IDOR).

**Ownership requires *every* row in the session to match, not any row.** Matching a single row would make the check an allow-list, and `session_id` is client-supplied (`X-Session-ID`) and unvalidated. An attacker who got one message into a victim's session would thereby authorize deletion of the whole session. Two independent defences prevent that:

1. `add_message()` refuses to append to a session owned by a different key, raising `SessionOwnershipError`. This is the primary guard — it also prevents the victim's history being pulled into the attacker's LLM context.
2. `_api_key_owns_session()` requires all rows to share the caller's fingerprint. A session whose rows disagree has no single owner and is refused outright, so a poisoned row grants nothing even if one is inserted out-of-band.

Resolution order, given `total` = message count in the session:

| Condition | Result |
|---|---|
| `total == 0` | **allow** — nothing to protect |
| rows matching caller's `api_key_hash` == `total` | **allow** — sole owner |
| rows matching caller's `api_key_hash` > 0 but < `total` | **deny** — mixed ownership |
| any row carries a hash, none the caller's | **deny** |
| no row carries any hash, all masked `api_key`s match caller | **allow** — legacy fallback |
| non-empty with no owner marker at all | **deny** — unattributable |

Notes on the last two rows:

- **Legacy rows** (`api_key_hash IS NULL`) fall back to comparing the masked `api_key`. That is weaker — a 6-character suffix — but keeps pre-v1.8 sessions both protected and deletable by their owner. It applies *only* when no row in the session carries a hash; otherwise a key sharing the owner's suffix could use the fallback to sidestep the hash comparison.
- **Markerless non-empty sessions** are denied rather than allowed. Such rows cannot be attributed to anyone, so no caller can prove ownership. Any write path that fails to propagate its API key produces them — A2A `tasks/send` did until v1.8, making its sessions deletable by any valid key. Voice websockets on adapters without `requires_api_key_validation` can still produce them by design.

The ownership check fails closed — a database error during the lookup denies the deletion rather than falling through to it.

**Reads are gated by the same rule.** `session_id` is client-supplied, so an unauthorized *read* would replay another tenant's conversation into the caller's LLM prompt. Authorization therefore happens **before context retrieval**, not after:

- `PipelineChatService.authorize_session_access()` is called from the route before dispatch and raises **403** for a foreign or markerless session. It must run at the route layer because `process_chat_stream` is an async generator — a rejection raised inside it would surface only after the response had begun.
- `ConversationHistoryHandler.get_context()` re-checks and raises `SessionOwnershipError`, as defence in depth for any read path that skips the gate. It deliberately does **not** downgrade this to an empty result: empty context would hide the authorization failure while still letting the caller drive a turn against another tenant's session id.
- For thread requests, `owner_api_key_hash` on the thread record authorizes turn 1; legacy threads without it fall back to authorizing both the thread session and its parent before either is read.
- `POST /api/threads` verifies the caller owns the parent session before creating a thread on it.

Requests with no API key (key enforcement disabled) skip all of this unchanged.

> **Known race.** Ownership is derived from message rows, not from an immutable session-owner record. Two concurrent first writes to the same new client-supplied `session_id` can both observe an empty session and both stamp their own fingerprint, producing a mixed-owner session. That no longer authorizes deletion or reads — mixed ownership is denied for everyone — but it can strand the session for both parties. Closing this cleanly needs a dedicated session-ownership record with a unique `session_id` constraint and atomic create-or-compare. Not implemented.

The raw key is never persisted in this table. `uploaded_files.api_key` stores keys in plain text and enforces its own ownership check by direct comparison; the two are independent.

---

### conversation_threads

Stores conversation thread metadata for follow-up questions on retrieved datasets from intent/QA adapters.

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
    metadata_json TEXT,
    owner_api_key_hash TEXT
)
```

**Fields:**
- `id` (TEXT, PK): Unique thread ID (UUID)
- `parent_message_id` (TEXT): ID of the parent message that triggered the thread (references chat_history.id)
- `parent_session_id` (TEXT): Session ID of the parent conversation
- `thread_session_id` (TEXT): New session ID for the thread conversation
- `adapter_name` (TEXT): Name of the adapter that generated the original response
- `query_context` (TEXT): JSON-encoded query context (original query, parameters, template_id)
- `dataset_key` (TEXT): Key/reference to stored dataset in Redis or fallback storage
- `created_at` (TEXT): ISO format timestamp of thread creation
- `expires_at` (TEXT): ISO format timestamp when thread expires (TTL)
- `metadata_json` (TEXT): JSON-encoded additional metadata
- `owner_api_key_hash` (TEXT): `hash_api_key()` of the key that owned the parent session when the thread was created. Binds the thread — and the thread session it spawns — to that key. Required because on the thread's **first** turn the thread session is still empty and has no owner rows of its own to check; without this record there would be nothing to authorize against. `NULL` for threads created before v1.8, which fall back to authorizing the thread and parent sessions directly

**Indexes:**
- `idx_conversation_threads_parent_message` on `parent_message_id`
- `idx_conversation_threads_parent_session` on `parent_session_id`
- `idx_conversation_threads_thread_session` on `thread_session_id`
- `idx_conversation_threads_expires_at` on `expires_at`
- `idx_conversation_threads_owner` on `owner_api_key_hash`

---

### thread_datasets

Stores retrieved dataset content for conversation threads when Redis storage is unavailable or disabled.

```sql
CREATE TABLE IF NOT EXISTS thread_datasets (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    dataset_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

**Fields:**
- `id` (TEXT, PK): Dataset key, typically `thread_dataset_{thread_id}_{timestamp}`
- `thread_id` (TEXT): Conversation thread ID associated with the dataset
- `dataset_json` (TEXT): JSON-encoded dataset payload containing query context and raw results
- `expires_at` (TEXT): ISO format timestamp when the fallback dataset expires
- `created_at` (TEXT): ISO format timestamp of dataset creation

**Indexes:**
- `idx_thread_datasets_thread_id` on `thread_id`
- `idx_thread_datasets_expires_at` on `expires_at`

---

### uploaded_files

Stores uploaded file metadata for retrieval and file adapter workflows.

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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Fields:**
- `id` (TEXT, PK): Unique uploaded file ID (UUID)
- `api_key` (TEXT): API key that uploaded the file
- `filename` (TEXT): Original filename
- `mime_type` (TEXT): File MIME type
- `file_size` (INTEGER): File size in bytes
- `upload_timestamp` (TEXT): Upload timestamp
- `processing_status` (TEXT): Processing state for the file
- `storage_key` (TEXT): Storage key for persisted file content
- `chunk_count` (INTEGER): Number of generated chunks
- `vector_store` (TEXT): Vector store backend name
- `collection_name` (TEXT): Collection/index used for retrieval
- `storage_type` (TEXT): Storage mode, defaults to `vector`
- `metadata_json` (TEXT): JSON-encoded file metadata
- `embedding_provider` (TEXT): Embedding provider used
- `embedding_dimensions` (INTEGER): Embedding vector dimensions
- `created_at` (TEXT): Creation timestamp

**Indexes:**
- `idx_uploaded_files_api_key` on `api_key`
- `idx_uploaded_files_processing_status` on `processing_status`

---

### file_chunks

Stores metadata for chunks produced from uploaded files.

```sql
CREATE TABLE IF NOT EXISTS file_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_index INTEGER,
    vector_store_id TEXT,
    collection_name TEXT,
    chunk_metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES uploaded_files(id)
)
```

**Fields:**
- `id` (TEXT, PK): Unique chunk ID (UUID)
- `file_id` (TEXT): Parent uploaded file ID
- `chunk_index` (INTEGER): Chunk position within the file
- `vector_store_id` (TEXT): Vector-store-specific chunk/document ID
- `collection_name` (TEXT): Collection/index holding the chunk embedding
- `chunk_metadata` (TEXT): Serialized chunk metadata
- `created_at` (TEXT): Creation timestamp

**Indexes:**
- `idx_file_chunks_file_id` on `file_id`

---

### audit_logs

Stores audit trail records for conversation logging and compliance.

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
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    reasoning_tokens INTEGER,
    cached_prompt_tokens INTEGER,
    cost_usd REAL,
    input_rate_per_1m REAL,
    output_rate_per_1m REAL,
    pricing_source TEXT,
    usage_unit TEXT,
    usage_quantity REAL,
    call_type TEXT
)
```

**Fields:**
- `id` (TEXT, PK): Unique audit record ID (UUID)
- `timestamp` (TEXT): ISO format timestamp of the conversation
- `query` (TEXT): The user's query/message
- `response` (TEXT): The system's response (plain text or base64-encoded gzip if compressed)
- `response_compressed` (INTEGER): Whether response is compressed (1=compressed, 0=plain text)
- `provider` (TEXT): The inference provider used (e.g., `ollama`, `openai`, `anthropic`)
- `blocked` (INTEGER): Whether the query was blocked (1=blocked, 0=allowed)
- `ip` (TEXT): Client IP address
- `ip_type` (TEXT): IP address type ("ipv4", "ipv6", "local", "unknown")
- `ip_is_local` (INTEGER): Whether the IP is local/private (1=true, 0=false)
- `ip_source` (TEXT): IP source ("direct", "proxy", "unknown")
- `ip_original_value` (TEXT): Original IP value before processing
- `api_key_value` (TEXT): API key used for the request (if any), stored **masked** (`...` + last 6 characters, via `mask_api_key`). Display/audit only — never use it for authorization. Groupable as the logical `api_key` dimension on `GET /admin/observability/usage` (the Costs tab), which resolves this column; two keys sharing their last 6 characters would collapse into one group
- `api_key_timestamp` (TEXT): ISO timestamp when API key was used
- `session_id` (TEXT): Session identifier for the conversation
- `user_id` (TEXT): User identifier (if authenticated)
- `adapter_name` (TEXT): Adapter used to service the request
- `model` (TEXT): Actual model used for the request after all adapter/default/runtime resolution
- `prompt_tokens` (INTEGER): Input token count reported by the provider; `NULL` if usage was unreported (un-migrated provider, cancelled stream, cache hit)
- `completion_tokens` (INTEGER): Output token count reported by the provider, inclusive of any billed reasoning tokens
- `total_tokens` (INTEGER): `prompt_tokens + completion_tokens`
- `reasoning_tokens` (INTEGER): Reasoning/thinking tokens broken out from `completion_tokens` where the provider reports them separately (OpenAI-shaped `completion_tokens_details`/`output_tokens_details`, Gemini/Vertex `thoughts_token_count`); `NULL` when the provider doesn't report this breakdown
- `cached_prompt_tokens` (INTEGER): Subset of `prompt_tokens` served from a provider-side prompt cache (Anthropic `cache_control` breakpoints, DeepSeek/xAI automatic caching); already included in `prompt_tokens`/`total_tokens`, and priced at a discount when `config/pricing.yaml` has a `cached_input_per_1m` tier for that provider/model (see `docs/token-usage-and-cost-tracking.md`). `NULL` when the provider doesn't report a cache hit
- `cost_usd` (REAL): Estimated cost from `config/pricing.yaml` (see `docs/token-usage-and-cost-tracking.md`). `NULL` means unpriced (no matching rate), distinct from `0.0` which means an explicit free/local rate
- `input_rate_per_1m` (REAL): Input rate ($/1M tokens) used for this estimate, captured at write time so historical rows stay auditable after `pricing.yaml` changes
- `output_rate_per_1m` (REAL): Output rate ($/1M tokens) used for this estimate
- `pricing_source` (TEXT): How the rate was resolved — `exact`, `pattern`, `provider_default`, `local_zero`, or `unpriced`
- `usage_unit` (TEXT): Discrete billing unit for media requests (`images`, `seconds`, `characters`, `audio_seconds`, `pages`, `audio_tokens`); `NULL` for token-billed requests
- `usage_quantity` (REAL): Quantity in `usage_unit` for this request; `NULL` for token-billed requests. `cost_usd` is the single summable cost column across both token- and unit-billed requests
- `call_type` (TEXT): Coarse classification of the AI call this row represents — `inference` (chat/text generation, the default), `embedding`, `image`, `video`, `audio`, or `document` (OCR). Set at the usage-recording call site (`record_usage`/`record_media_generation_usage` in `server/inference/pipeline/steps/_utils.py`), not inferred from `provider`/`model`. A chat turn that also folds in retrieval-embedding cost (per `docs/embedding-cost-tracking.md`) is still `inference` — only usage-only rows with no generation call (e.g. the standalone `/api/files/{file_id}/query` audit row) get `embedding`. `NULL` for rows written before this field was added, displayed as `inference` by the admin panel

**Indexes:**
- `idx_audit_logs_timestamp` on `timestamp`
- `idx_audit_logs_session_id` on `session_id`
- `idx_audit_logs_user_id` on `user_id`
- `idx_audit_logs_blocked` on `blocked`
- `idx_audit_logs_provider` on `provider`
- `idx_audit_logs_adapter_name` on `adapter_name`
- `idx_audit_logs_model` on `model`
- `idx_audit_logs_call_type` on `call_type`
- `idx_audit_logs_api_key_value` on `api_key_value`

**Configuration:**
The audit storage backend is configured in `config/config.yaml`:

```yaml
internal_services:
  audit:
    enabled: true
    storage_backend: "database"  # "elasticsearch", "sqlite", "mongodb", or "database"
    collection_name: "audit_logs"
    compress_responses: false    # Enable gzip compression for response field
```

When `storage_backend` is set to `"database"`, the audit service uses the same backend as configured in `internal_services.backend.type`.

**Response Compression:**
When `compress_responses: true`, the response field is stored as base64-encoded gzip data. This typically reduces storage by 70-90% for LLM responses. The `response_compressed` field indicates whether decompression is needed when reading. Set to `false` during development/testing to see plain text responses in the database.

---

### audit_admin_logs

Stores audit trail records for privileged operations on `/admin/*` and `/auth/*` endpoints. Populated by the admin-audit middleware when `internal_services.audit.admin_events.enabled` is `true`. Only mutations (POST/PUT/PATCH/DELETE) are recorded; read-only GETs are skipped.

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

**Fields:**
- `id` (TEXT, PK): Unique record ID (UUID)
- `timestamp` (TEXT): ISO format timestamp of the event
- `event_type` (TEXT): Canonical event name (e.g. `auth.login`, `admin.api_key.create`, `admin.config.update`)
- `action` (TEXT): Operation class (`CREATE`, `UPDATE`, `DELETE`, `LOGIN`, `LOGOUT`, `CONTROL`)
- `resource_type` (TEXT): Kind of resource affected (`user`, `api_key`, `adapter`, `config`, `prompt`, `session`, `server`, ...)
- `resource_id` (TEXT): Identifier of the affected resource (path param, body field, or actor id, depending on the route)
- `actor_type` (TEXT): Who initiated the action (`user`, `api_key`, `anonymous`)
- `actor_id` (TEXT): User ID for `user` actors; masked API key for `api_key` actors; `NULL` for anonymous
- `actor_username` (TEXT): Username (when the actor is an authenticated user)
- `method` (TEXT): HTTP method (POST/PUT/PATCH/DELETE)
- `path` (TEXT): Concrete request path (not a template)
- `status_code` (INTEGER): HTTP response status
- `success` (INTEGER): `1` if `status_code < 400`, else `0`
- `ip` (TEXT): Client IP address (cleaned)
- `ip_type` (TEXT): IP address type (`ipv4`, `ipv6`, `local`, `unknown`)
- `ip_is_local` (INTEGER): Whether the IP is local/private (1=true, 0=false)
- `ip_source` (TEXT): `direct` or `proxy` (from `X-Forwarded-For`)
- `ip_original_value` (TEXT): Raw IP value before parsing
- `user_agent` (TEXT): Request `User-Agent` header
- `error_message` (TEXT): Short marker for failed requests (e.g. `HTTP 401`)
- `request_summary` (TEXT): JSON-encoded, secret-scrubbed subset of the request body. Per-route allowlists ensure passwords, raw API keys, and prompt bodies are never stored; config/adapter-config updates record only the list of changed top-level keys (no values).

**Indexes:**
- `idx_audit_admin_logs_timestamp` on `timestamp`
- `idx_audit_admin_logs_actor_id` on `actor_id`
- `idx_audit_admin_logs_event_type` on `event_type`
- `idx_audit_admin_logs_resource_type` on `resource_type`
- `idx_audit_admin_logs_success` on `success`

**Configuration:**
Admin-event auditing is opt-in and configured in `config/config.yaml` under the main audit block:

```yaml
internal_services:
  audit:
    enabled: true                     # Master audit toggle (required)
    admin_events:
      enabled: true                   # Enable admin/auth event auditing
      collection_name: "audit_admin_logs"
```

When `audit.enabled` is `false`, admin-event auditing is forced off regardless of the `admin_events.enabled` flag. Audit write failures are logged and swallowed — they never break the underlying admin action.

---

### feedback

Stores user feedback (thumbs up/down) on chat responses.

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

**Fields:**
- `id` (TEXT, PK): Unique feedback ID (UUID)
- `message_id` (TEXT): Database message ID of the assistant response (references chat_history.id)
- `session_id` (TEXT): Session identifier
- `user_id` (TEXT): Optional user ID (when auth is enabled)
- `feedback_type` (TEXT): Feedback value ("up" or "down")
- `adapter_name` (TEXT): Adapter that generated the response
- `comment` (TEXT): Optional free-text comment accompanying the rating (captured on thumbs-down); `NULL` when none. Bounded to 2000 characters (enforced server-side and by clients)
- `created_at` (TEXT): ISO format timestamp of feedback creation
- `updated_at` (TEXT): ISO format timestamp of last update

**Indexes:**
- `idx_feedback_message_session` (UNIQUE) on `(message_id, session_id)` - one feedback per message per session
- `idx_feedback_session` on `session_id`
- `idx_feedback_type` on `feedback_type`
- `idx_feedback_adapter` on `adapter_name`

---

### system_state

Small durable key/value store for cross-process coordination state that must survive cache flushes and worker restarts — currently just the server pause flag set via `POST /admin/pause` / `POST /admin/resume`. Not a cache: rows here are never cleared on startup or by any cache-invalidation path.

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

### adapter_reload_state

Durable generation counters for propagating `POST /admin/reload-adapters` / `POST /admin/reload-templates` across all `performance.workers` processes — see `server/services/adapter_reload_state.py`. Under multiple workers, a reload request only updates the one worker that served it; every worker polls this table every 5s and fully reloads locally when it sees a stale generation.

```sql
CREATE TABLE IF NOT EXISTS adapter_reload_state (
    id TEXT PRIMARY KEY,
    generation INTEGER
)
```

**Fields:**
- `id` (TEXT, PK): Row key. Two rows: `reload:adapter_config`, `reload:templates`
- `generation` (INTEGER): Monotonic counter, incremented by 1 on every successful reload of that kind

**Indexes:** none — the single-row PK lookup by `id` doesn't need one.

---

## Data Types

### ID Fields
All `id` fields use UUID v4 format as TEXT:
```
"550e8400-e29b-41d4-a716-446655440000"
```

### Timestamps
All timestamp fields use ISO 8601 format as TEXT:
```
"2025-10-27T12:58:34.123456"
```

### Boolean Fields
Boolean values are stored as INTEGER:
- `1` = True
- `0` = False

### JSON Fields
Fields ending in `_json` store JSON-encoded data as TEXT:
```json
{"key": "value", "nested": {"data": 123}}
```

---

## Compatibility Notes

### MongoDB Field Mapping

When migrating from MongoDB or using code that expects MongoDB format:

| MongoDB Field | SQLite Field | Notes |
|--------------|-------------|-------|
| `_id` | `id` | Converted automatically in abstraction layer |
| ObjectId | UUID string | Both are unique identifiers |
| `metadata` | `metadata_json` | JSON serialization/deserialization |
| ISODate | ISO string | Datetime to/from string conversion |
| Boolean | Integer | 1/0 for true/false |

### Query Translation

MongoDB-style queries are automatically translated to SQL:

| MongoDB Query | SQL Translation |
|--------------|----------------|
| `{"field": "value"}` | `WHERE field = 'value'` |
| `{"field": {"$gt": 10}}` | `WHERE field > 10` |
| `{"field": {"$in": [1, 2, 3]}}` | `WHERE field IN (1, 2, 3)` |
| `{"field": {"$regex": "pattern"}}` | `WHERE field LIKE '%pattern%'` |

---

## Maintenance

### Database File Management

The SQLite database is a single file that can be:
- **Backed up**: Simply copy the `orbit.db` file
- **Restored**: Replace the `orbit.db` file
- **Moved**: Update the `database_path` in config
- **Deleted**: Remove the file to start fresh

### Performance Considerations

SQLite is suitable for:
- Development and testing
- Small to medium deployments
- Single-server setups
- Applications with < 100k chat messages

For larger deployments, consider using MongoDB backend.

### Database Inspection

You can inspect the SQLite database using the `sqlite3` command-line tool:

```bash
# Open the database
sqlite3 orbit.db

# List all tables
.tables

# Show table schema
.schema users

# Query data
SELECT * FROM users;

# Exit
.quit
```

Or use a GUI tool like:
- [DB Browser for SQLite](https://sqlitebrowser.org/)
- [SQLite Studio](https://sqlitestudio.pl/)
- [DBeaver](https://dbeaver.io/)

---

## Migration

### From MongoDB to SQLite

There is no built-in migration tool. To migrate:

1. Export data from MongoDB using `mongoexport`
2. Transform to SQLite-compatible format
3. Import using SQL INSERT statements or Python script

### From SQLite to MongoDB

1. Read data from SQLite using Python
2. Transform IDs (UUID → ObjectId)
3. Insert into MongoDB collections

---

## Security

### Password Storage

User passwords are hashed using PBKDF2 with:
- 600,000 iterations
- SHA-256 hash function
- Salt per password

### API Keys

API keys are stored in plain text as they need to be compared directly. Ensure:
- Database file permissions are restricted
- Use strong, random API keys
- Rotate keys regularly

### Database File Permissions

Secure the database file:
```bash
chmod 600 orbit.db  # Owner read/write only
```

---

## Troubleshooting

### Common Issues

**Database locked error:**
- SQLite uses file-level locking
- Ensure only one process accesses the database
- Use WAL mode for better concurrency (enabled by default)

**Performance issues:**
- Add indexes for frequently queried fields
- Use VACUUM to reclaim space
- Consider switching to MongoDB for high-traffic scenarios

**Corruption:**
- Run integrity check: `sqlite3 orbit.db "PRAGMA integrity_check;"`
- Restore from backup if corrupted

---

## Version History

- **v1.13** (2026-08-21): Cost aggregation by API key
  - Added index `idx_audit_logs_api_key_value` on the existing `audit_logs.api_key_value` column, which now backs the `api_key` group-by dimension on `GET /admin/observability/usage` (admin panel Costs tab). Every other groupable dimension already had one
  - No column was added — the masked API key was already recorded on every audit row. See `docs/roadmap/costs-by-api-key.md` for the phased plan; a stable (non-masked) key identifier is deferred to a later phase
  - Created automatically on existing databases via `CREATE INDEX IF NOT EXISTS` on startup; MongoDB and Elasticsearch group on the nested `api_key.key` field and need no migration
  - `install/orbit.db.default` (the default database shipped with new installs) updated in place to include the index
- **v1.12** (2026-08-13): Cached prompt token tracking
  - Added `audit_logs.cached_prompt_tokens` — the subset of `prompt_tokens` served from a provider-side prompt cache (Anthropic `cache_control`, DeepSeek/xAI automatic caching), already priced at a discount by `PricingService.estimate()` when configured; previously computed but silently dropped before reaching the audit ledger
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`); MongoDB is schemaless and needs no migration; the Elasticsearch mapping gained an explicit `integer` type for the same reason `reasoning_tokens` has one
  - `install/orbit.db.default` (the default database shipped with new installs) updated in place to include the column
- **v1.11** (2026-08-05): Email-preauthorized API keys
  - Added `api_keys.allowed_emails` (JSON array of normalized email addresses), allowing an administrator to restrict a key before an OIDC user has been JIT-provisioned. A caller matching either `allowed_emails` or `allowed_user_ids` is authorized; any configured allowlist fails closed for anonymous callers
  - Applied to existing SQLite/Postgres databases by the additive startup migration (`_migrate_table_schema`); schemaless backends need no migration

- **v1.10** (2026-08-04): Per-user API key restriction
  - Added `api_keys.allowed_user_ids` (JSON array of ORBIT `users.id`) — lets an admin restrict a key/adapter to specific logged-in users (including JIT-provisioned Entra/Auth0 users) instead of it being usable by anyone who holds the key. `NULL`/empty preserves current unrestricted behavior
  - Enforced in `ApiKeyService.validate_api_key`/`get_adapter_for_api_key` against the caller's authenticated user id (resolved the same way `get_optional_user` already resolves bearer tokens, including external-provider JWTs via the existing `OIDCValidator`/JIT-provisioning pipeline) — no new identity-verification code was needed
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`); MongoDB is schemaless and needs no migration
- **v1.9** (2026-07-31): Audit ledger call-type classification
  - Added `audit_logs.call_type` (`inference`, `embedding`, `image`, `video`, `audio`, `document`) and index `idx_audit_logs_call_type` — lets the admin panel Audit Ledger label and filter rows by the kind of AI call instead of showing every row as "Inference"
  - Set at the usage-recording call site (`record_usage`/`record_media_generation_usage`), not inferred from `provider`/`model` after the fact
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`); MongoDB and Elasticsearch need no migration (schemaless / dynamic mapping with an explicit `keyword` type added)
  - Existing rows keep `call_type = NULL`, displayed and filterable as `inference` by the admin panel and API — no visual regression, but historical embedding/media rows won't retroactively reclassify
- **v1.8** (2026-07-31): Session ownership binding for chat history
  - Added `chat_history.api_key_hash` (SHA-256 of the creating API key) and index `idx_chat_history_api_key_hash` on `(session_id, api_key_hash)`
  - Closes a cross-tenant IDOR on `DELETE /admin/chat-history/{session_id}` and `DELETE /admin/conversations/{session_id}`, which previously checked only that the caller's key was valid, never that it owned the target session
  - Ownership requires *all* rows in a session to match, and `add_message()` refuses to append to a session owned by another key — together these close an escalation where one injected message authorized deletion of the whole session
  - Non-empty sessions with no owner marker are now denied. A2A `tasks/send`/`tasks/sendSubscribe` now propagate their Bearer key into `process_chat` so their history is attributable
  - Added `conversation_threads.owner_api_key_hash` + index `idx_conversation_threads_owner`, binding a thread to its parent session's owner
  - Extended the same rule to **reads**: context retrieval is authorized before it runs, closing a cross-tenant leak where a caller supplying another tenant's `session_id` had that tenant's conversation replayed into their LLM prompt
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`); MongoDB is schemaless and needs no migration
  - **Backfill still pending.** Existing rows keep `api_key_hash = NULL` and fall back to the weaker masked-suffix comparison until backfilled. Pre-v1.8 markerless sessions (e.g. old A2A history) are now undeletable through these endpoints until backfilled
- **v1.7** (2026-07-30): Media (image/video/audio/OCR) usage and cost tracking
  - Added `audit_logs.usage_unit`, `usage_quantity` — discrete-unit billing (images, video seconds, TTS characters, STT seconds, OCR pages) for non-token media requests, alongside the existing token columns; `cost_usd` remains the single summable cost column across both
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`); see `docs/token-usage-and-cost-tracking.md`
- **v1.6** (2026-07-29): Token usage and cost tracking
  - Added `audit_logs.prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens`, `cost_usd`, `input_rate_per_1m`, `output_rate_per_1m`, `pricing_source`
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`); see `docs/token-usage-and-cost-tracking.md`
- **v1.5** (2026-07-22): Multi-worker adapter reload coordination state
  - Added `adapter_reload_state` table (propagates `/admin/reload-adapters` and `/admin/reload-templates` across `performance.workers` processes; see `server/services/adapter_reload_state.py`)
  - Created automatically on existing databases via `CREATE TABLE IF NOT EXISTS` on startup (no manual migration needed)
- **v1.4** (2026-07-22): Server pause coordination state
  - Added `system_state` table (server pause flag; see `server/services/pause_state.py`)
  - Created automatically on existing databases via `CREATE TABLE IF NOT EXISTS` on startup (no manual migration needed)
- **v1.3** (2026-07-18): Feedback comments
  - Added nullable `feedback.comment` for the optional free-text comment captured on thumbs-down
  - Applied to existing databases via the additive-column migration on startup (`_migrate_table_schema`)
- **v1.2** (2026-07-03): External identity provider support
  - Added `users.provider`, `users.external_id`, and `users.email` (all nullable) for JIT-provisioned Entra ID / Auth0 users
  - Applied to existing databases via the additive-column migration on startup
- **v1.1** (2026-05-26): Audit schema updates
  - `audit_logs.backend` renamed to `audit_logs.provider`
  - Added `audit_logs.model`
  - Added `idx_audit_logs_provider` and `idx_audit_logs_model`
- **v1.0** (2025-10-27): Initial SQLite backend implementation
  - Basic tables for users, sessions, api_keys, system_prompts
  - Chat history and archive tables
  - Full compatibility with MongoDB abstraction layer
