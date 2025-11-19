# Conversation Threading for Intent Adapters

## Overview

Enable follow-up conversations on retrieved datasets from one-shot intent/QA adapters. Users can click a "Start Thread" button on assistant responses to create a sub-conversation thread that uses the stored dataset instead of re-querying.

## Architecture

### Storage Strategy

- **Thread Metadata**: New `conversation_threads` table/collection storing parent-child relationships
- **Dataset Storage**: Redis (if enabled) with TTL, fallback to SQLite/MongoDB
- **Query Context**: Stored separately from raw results for efficient retrieval

### Adapter Detection

- Support all one-shot retrievers: intent adapters (SQL, DuckDB, PostgreSQL, Elasticsearch, MongoDB, HTTP, Firecrawl) and QA adapters
- Exclude: conversational and multimodal adapters

## Implementation Tasks

### 1. Backend: Database Schema

**Files:**

- `server/services/sqlite_service.py` - Add `conversation_threads` table schema
- `server/services/mongodb_service.py` - Add collection support
- `docs/sqlite-schema.md` - Document schema

**Schema:**

```sql
CREATE TABLE conversation_threads (
    id TEXT PRIMARY KEY,
    parent_message_id TEXT NOT NULL,  -- References chat_history.id
    parent_session_id TEXT NOT NULL,   -- References chat_history.session_id
    thread_session_id TEXT NOT NULL,   -- New session ID for thread
    adapter_name TEXT NOT NULL,
    query_context TEXT NOT NULL,       -- JSON: original query, parameters, template_id
    dataset_key TEXT NOT NULL,         -- Redis key or storage reference
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,          -- TTL expiration
    metadata_json TEXT                 -- Additional metadata
)
```

### 2. Backend: Configuration

**Files:**

- `config/config.yaml` - Add threading configuration

**Config:**

```yaml
conversation_threading:
  enabled: true
  dataset_ttl_hours: 24  # Global default TTL
  storage_backend: "redis"  # redis, sqlite, mongodb
  redis_key_prefix: "thread_dataset:"
```

### 3. Backend: Dataset Storage Service

**New File:**

- `server/services/thread_dataset_service.py`

**Responsibilities:**

- Store/retrieve datasets from Redis (with TTL) or fallback storage
- Store query context separately from raw results
- Generate unique dataset keys
- Handle expiration and cleanup

**Key Methods:**

- `store_dataset(thread_id, query_context, raw_results) -> dataset_key`
- `get_dataset(dataset_key) -> (query_context, raw_results)`
- `delete_dataset(dataset_key)`

### 4. Backend: Thread Management Service

**New File:**

- `server/services/thread_service.py`

**Responsibilities:**

- Create threads from parent messages
- Manage thread lifecycle
- Link threads to stored datasets
- Validate thread access

**Key Methods:**

- `create_thread(parent_message_id, parent_session_id, adapter_name, query_context, raw_results) -> thread_id`
- `get_thread(thread_id) -> thread_info`
- `get_thread_dataset(thread_id) -> (query_context, raw_results)`
- `delete_thread(thread_id)`

### 5. Backend: API Endpoints

**Files:**

- `server/routes/routes_configurator.py` - Add thread endpoints

**New Endpoints:**

- `POST /api/threads` - Create thread from message
  - Body: `{ message_id, session_id }`
  - Returns: `{ thread_id, thread_session_id }`
- `POST /v1/chat` - Modify to accept `thread_id` parameter
  - When `thread_id` present, use stored dataset instead of retrieval
- `GET /api/threads/{thread_id}` - Get thread info
- `DELETE /api/threads/{thread_id}` - Delete thread

### 6. Backend: Pipeline Integration

**Files:**

- `server/inference/pipeline/steps/context_retrieval.py` - Modify to check for thread_id
- `server/services/pipeline_chat_service.py` - Pass thread_id through pipeline

**Changes:**

- If `thread_id` in context, skip retrieval and load dataset from storage
- Inject stored dataset as `retrieved_docs` in ProcessingContext
- Log thread usage for debugging

### 7. Backend: Adapter Detection

**Files:**

- `server/adapters/capabilities.py` - Add `supports_threading` capability
- `server/inference/pipeline/steps/context_retrieval.py` - Check capability

**Logic:**

- Intent adapters: `adapter == "intent"` → supports threading
- QA adapters: `adapter == "qa"` → supports threading
- Conversational/Multimodal: `adapter == "conversational"` or `adapter == "multimodal"` → no threading

### 8. Backend: Response Metadata

**Files:**

- `server/services/pipeline_chat_service.py` - Add threading metadata to response
- `server/services/chat_handlers/response_processor.py` - Include threading info

**Response Format:**

```json
{
  "response": "...",
  "sources": [...],
  "threading": {
    "supports_threading": true,
    "message_id": "...",
    "session_id": "..."
  }
}
```

### 9. Frontend: Types

**Files:**

- `clients/chat-app/src/types/index.ts` - Add thread types

**New Types:**

```typescript
interface ThreadInfo {
  thread_id: string;
  thread_session_id: string;
  parent_message_id: string;
  created_at: Date;
}

interface Message {
  // ... existing fields
  threadInfo?: ThreadInfo;
  supportsThreading?: boolean;
}
```

### 10. Frontend: Message Component

**Files:**

- `clients/chat-app/src/components/Message.tsx` - Add "Start Thread" button

**Changes:**

- Add button next to Copy/Retry buttons (only for assistant messages)
- Show button only when `message.supportsThreading === true`
- Button text: "Start Thread" with thread icon (from lucide-react)
- On click: Call API to create thread, update message with thread info

### 11. Frontend: Thread UI

**Files:**

- `clients/chat-app/src/components/ChatInterface.tsx` - Add thread indicator
- `clients/chat-app/src/components/MessageList.tsx` - Show thread context

**UI Elements:**

- Thread badge/indicator when in thread mode
- Show parent message reference
- "Exit Thread" button to return to main conversation

### 12. Frontend: API Integration

**Files:**

- `clients/chat-app/src/contexts/ChatContext.tsx` - Add thread handling
- `clients/chat-app/src/stores/chatStore.ts` - Store thread state

**Changes:**

- Add `createThread(messageId, sessionId)` method
- Modify `sendMessage` to accept optional `threadId`
- Track current thread state in conversation
- Update message sending to include `thread_id` when in thread

### 13. Frontend: Thread Management

**Files:**

- `clients/chat-app/src/services/threadService.ts` (new) - API client for threads

**Methods:**

- `createThread(messageId, sessionId) -> Promise<ThreadInfo>`
- `sendThreadMessage(threadId, message) -> Promise<Response>`
- `getThreadInfo(threadId) -> Promise<ThreadInfo>`
- `deleteThread(threadId) -> Promise<void>`

### 14. Node.js API Client: Thread Support

**Files:**

- `clients/node-api/api.ts` - Add thread management methods to ApiClient class

**New Methods:**

- `createThread(messageId: string, sessionId: string) -> Promise<ThreadInfo>`
  - POST to `/api/threads` with message_id and session_id
  - Returns thread_id and thread_session_id
- `getThreadInfo(threadId: string) -> Promise<ThreadInfo>`
  - GET from `/api/threads/{thread_id}`
- `deleteThread(threadId: string) -> Promise<void>`
  - DELETE to `/api/threads/{thread_id}`
- Modify `streamChat()` and `createChatRequest()` to accept optional `threadId` parameter
  - Add `thread_id` to ChatRequest interface
  - Include thread_id in request body when provided

**New Interfaces:**

```typescript
interface ThreadInfo {
  thread_id: string;
  thread_session_id: string;
  parent_message_id: string;
  parent_session_id: string;
  adapter_name: string;
  created_at: string;
  expires_at: string;
}

interface ChatRequest {
  // ... existing fields
  thread_id?: string;  // Optional thread ID for follow-up questions
}
```

## Testing Considerations

1. **Thread Creation**: Verify thread created with correct parent relationship
2. **Dataset Storage**: Verify dataset stored in Redis/SQLite with TTL
3. **Thread Queries**: Verify follow-up questions use stored dataset, not re-query
4. **Expiration**: Verify threads expire after TTL
5. **Adapter Detection**: Verify only one-shot adapters show "Start Thread" button
6. **UI Flow**: Verify thread creation and message sending works end-to-end

## Configuration Defaults

- TTL: 24 hours (configurable in config.yaml)
- Storage: Redis if enabled, fallback to SQLite/MongoDB
- Enabled: true by default

## Notes

- Threads are independent sessions but linked to parent message
- Dataset storage uses compressed JSON for efficiency
- Thread expiration cleanup runs on thread access (lazy cleanup)
- Thread metadata persists in database, datasets expire per TTL