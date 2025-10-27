# SQLite Backend Implementation Plan

## Overview

Implement SQLite as an alternative backend to MongoDB for all data persistence needs (authentication, API keys, system prompts, and chat history). The implementation will use a clean layered architecture with an abstraction layer that keeps existing APIs unchanged.

## Architecture Design

### Database Abstraction Layer

Create a unified interface that both MongoDB and SQLite implementations will follow, ensuring that services remain backend-agnostic.

**Key file to create:** `server/services/database_service.py`

- Abstract base class `DatabaseService` with methods matching current MongoDB operations:
  - `initialize()`, `find_one()`, `find_many()`, `insert_one()`, `update_one()`, `delete_one()`, `delete_many()`
  - `create_index()`, `get_collection()`, `execute_transaction()`
- Factory method `create_database_service(config)` that returns either MongoDBService or SQLiteService based on config

### SQLite Service Implementation

**Key file to create:** `server/services/sqlite_service.py`

- Implement `SQLiteService` class inheriting from `DatabaseService` base
- Use standard `sqlite3` library with `ThreadPoolExecutor` for async operations
- Single database file: `orbit.db` in project root
- Implement singleton pattern matching MongoDB service
- Create tables on initialization:
  - `users` table (id, username, password, role, active, created_at, last_login)
  - `sessions` table (id, token, user_id, username, expires, created_at)
  - `api_keys` table (id, api_key, client_name, notes, active, created_at, adapter_name, system_prompt_id)
  - `system_prompts` table (id, name, prompt, version, created_at, updated_at)
  - `chat_history` table (id, session_id, role, content, timestamp, user_id, api_key, metadata_json)
- Handle ObjectId-like string IDs (UUID or auto-increment)
- JSON serialization for metadata fields

### Configuration Updates

**File:** `config/config.yaml`

Add new `backend` configuration section under `internal_services`:

```yaml
internal_services:
  backend:
    type: "sqlite"  # or "mongodb"
    sqlite:
      database_path: "orbit.db"  # relative to project root
    
  # Existing mongodb config remains for backwards compatibility
  mongodb:
    # ... existing config
```

### Service Modifications

**Files to modify:**

1. `server/services/mongodb_service.py`

   - Refactor to inherit from `DatabaseService` base class
   - Keep existing implementation, just add base class conformance

2. `server/services/api_key_service.py`

   - Change constructor to accept generic `database_service` instead of `mongodb_service`
   - Replace `self.mongodb` references with `self.database`
   - No changes to public API

3. `server/services/prompt_service.py`

   - Change constructor to accept generic `database_service` instead of `mongodb_service`
   - Replace `self.mongodb` references with `self.database`
   - No changes to public API

4. `server/services/auth_service.py`

   - Change constructor to accept generic `database_service` instead of `mongodb_service`
   - Replace `self.mongodb` references with `self.database`
   - Handle ID generation differences (UUID vs ObjectId)
   - No changes to public API

5. `server/services/chat_history_service.py`

   - Change constructor to accept generic `database_service` instead of `mongodb_service`
   - Replace `self.mongodb_service` references with `self.database_service`
   - Handle JSON serialization for metadata in SQLite
   - No changes to public API

6. `server/services/service_factory.py`

   - Update `_initialize_mongodb_if_needed()` to `_initialize_database_if_needed()`
   - Use factory method to create appropriate database service based on config
   - Pass database service to dependent services

### ObjectId Compatibility Layer

**File to create:** `server/utils/id_utils.py`

- Create `generate_id()` function that works for both backends
- For SQLite: generate UUID strings or use auto-increment
- For MongoDB: return ObjectId
- Create `ensure_id()` function for conversion/validation

### Testing Considerations

The implementation should:

- Maintain backward compatibility with MongoDB
- Keep all existing routes and APIs unchanged
- Ensure CLI commands work with both backends
- Support switching backends via config without code changes

## Implementation Steps

### Step 1: Create Database Abstraction Layer

Create `server/services/database_service.py` with:

- Abstract base class defining common interface
- Factory method for creating backend-specific instances
- Type hints and documentation

### Step 2: Implement SQLite Service

Create `server/services/sqlite_service.py` with:

- Full implementation of DatabaseService interface
- Thread pool executor for async operations
- Schema creation and index management
- Singleton pattern implementation

### Step 3: Create ID Utility Layer

Create `server/utils/id_utils.py` for cross-backend ID handling

### Step 4: Update Configuration Schema

Modify `config/config.yaml` to add backend selection option

### Step 5: Refactor MongoDB Service

Update `server/services/mongodb_service.py` to inherit from DatabaseService base class

### Step 6: Update Dependent Services

Modify in order:

1. `api_key_service.py` - replace mongodb with database abstraction
2. `prompt_service.py` - replace mongodb with database abstraction  
3. `auth_service.py` - replace mongodb with database abstraction
4. `chat_history_service.py` - replace mongodb with database abstraction

### Step 7: Update Service Factory

Modify `server/services/service_factory.py` to use database factory method

### Step 8: Update Environment Example

Update `env.example` to document SQLite option

## Files Summary

**New Files:**

- `server/services/database_service.py` (abstraction layer)
- `server/services/sqlite_service.py` (SQLite implementation)
- `server/utils/id_utils.py` (ID compatibility utilities)

**Modified Files:**

- `config/config.yaml` (add backend configuration)
- `server/services/mongodb_service.py` (inherit from base)
- `server/services/api_key_service.py` (use database abstraction)
- `server/services/prompt_service.py` (use database abstraction)
- `server/services/auth_service.py` (use database abstraction)
- `server/services/chat_history_service.py` (use database abstraction)
- `server/services/service_factory.py` (use factory method)
- `env.example` (document new options)

**No Changes Needed:**

- `server/routes/admin_routes.py` (uses services, backend-agnostic)
- `bin/orbit.py` (CLI uses routes, remains unchanged)
- Any other route files (all backend-agnostic)

## Benefits

1. **Simplicity for newcomers:** No MongoDB installation required
2. **Zero-config option:** SQLite works out of the box
3. **Clean architecture:** Services remain backend-agnostic
4. **No API changes:** Existing integrations continue to work
5. **Easy testing:** SQLite enables simpler test setups
6. **Portability:** Single file database is easier to backup/move