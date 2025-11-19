# SQLite Database Schema

This document describes the SQLite database schema used by Orbit when configured with the SQLite backend.

## Overview

Orbit uses SQLite as an alternative backend to MongoDB for data persistence. The SQLite database contains the following tables:

- `users` - User accounts and authentication
- `sessions` - Active user sessions
- `api_keys` - API keys for authentication
- `system_prompts` - System prompts for chat
- `chat_history` - Chat message history
- `chat_history_archive` - Archived chat messages

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
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
)
```

**Fields:**
- `id` (TEXT, PK): Unique user ID (UUID)
- `username` (TEXT, UNIQUE): Username for login
- `password` (TEXT): Hashed password (PBKDF2)
- `role` (TEXT): User role (e.g., "admin", "user")
- `active` (INTEGER): Whether user is active (1=active, 0=inactive)
- `created_at` (TEXT): ISO format timestamp of account creation
- `last_login` (TEXT): ISO format timestamp of last login

**Indexes:**
- `idx_users_username` on `username`

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
    system_prompt_id TEXT
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
- `api_key` (TEXT): Optional API key used
- `metadata_json` (TEXT): JSON-encoded metadata
- `message_hash` (TEXT): Hash for deduplication
- `token_count` (INTEGER): Token count for the message (used for conversation history management)

**Indexes:**
- `idx_chat_history_session` on `(session_id, timestamp)`
- `idx_chat_history_user` on `(user_id, timestamp)`
- `idx_chat_history_timestamp` on `timestamp`
- `idx_chat_history_api_key` on `api_key`
- `idx_chat_history_hash` (UNIQUE) on `(session_id, message_hash)`

---

### chat_history_archive

Stores archived chat messages (same schema as chat_history).

```sql
CREATE TABLE IF NOT EXISTS chat_history_archive (
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

**Fields:** Same as `chat_history`

**Indexes:**
- `idx_chat_history_archive_session` on `(session_id, timestamp)`
- `idx_chat_history_archive_user` on `(user_id, timestamp)`
- `idx_chat_history_archive_timestamp` on `timestamp`

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

- **v1.0** (2025-10-27): Initial SQLite backend implementation
  - Basic tables for users, sessions, api_keys, system_prompts
  - Chat history and archive tables
  - Full compatibility with MongoDB abstraction layer
