# Conversation Threading Architecture

## Overview

The conversation threading system enables users to create focused sub-conversations (threads) from any assistant response in intent/QA adapters. This allows follow-up questions on retrieved datasets without re-querying the database, improving performance and maintaining context consistency.

**Key Features:**
- Create threads from any assistant message containing retrieved data
- Reuse cached datasets for follow-up questions
- Automatic expiration with configurable TTL
- Redis-first storage with database fallback
- Cascade deletion on parent conversation cleanup
- Adapter capability-based activation

## Architecture Components

### 1. Core Services

#### ThreadService (`server/services/thread_service.py`)

Manages the lifecycle of conversation threads.

**Responsibilities:**
- Create threads from parent messages
- Store thread metadata in database
- Link threads to their parent conversations
- Retrieve thread information
- Delete threads and associated data
- Clean up expired threads

**Key Methods:**
```python
async def create_thread(message_id: str, session_id: str) -> ThreadInfo
async def get_thread(thread_id: str) -> Optional[Dict[str, Any]]
async def get_thread_dataset(thread_id: str) -> Optional[Tuple[Dict, List]]
async def delete_thread(thread_id: str) -> Dict[str, Any]
async def cleanup_expired_threads() -> int
```

**Thread Metadata:**
```python
{
    "id": str,                      # Unique thread identifier
    "parent_message_id": str,       # Original message that started thread
    "parent_session_id": str,       # Parent conversation session
    "thread_session_id": str,       # Unique session for thread messages
    "adapter_name": str,            # Adapter used
    "query_context": dict,          # Original query parameters
    "dataset_key": str,             # Key for stored dataset
    "created_at": str,              # ISO timestamp
    "expires_at": str,              # Expiration timestamp
    "metadata_json": str            # Additional metadata
}
```

#### ThreadDatasetService (`server/services/thread_dataset_service.py`)

Handles storage and retrieval of datasets for threads.

**Storage Strategy:**
- **Primary:** Redis with TTL (fast, automatic expiration)
- **Fallback:** SQLite/MongoDB (persistent, manual cleanup)
- **Compression:** gzip for efficient storage

**Key Methods:**
```python
async def store_dataset(thread_id: str, query_context: Dict, raw_results: List, ttl_hours: int) -> str
async def get_dataset(dataset_key: str) -> Optional[Tuple[Dict, List]]
async def delete_dataset(dataset_key: str) -> bool
async def cleanup_expired_datasets() -> int
```

**Dataset Structure:**
```python
{
    "query_context": {
        "original_query": str,
        "template_id": str,
        "parameters_used": dict,
        "adapter_name": str
    },
    "raw_results": [
        {
            "content": str,
            "metadata": dict,
            "score": float
        }
    ]
}
```

### 2. Pipeline Integration

#### Context Retrieval Step (`server/inference/pipeline/steps/context_retrieval.py`)

Modified to check for thread context before normal retrieval.

**Flow:**
```python
async def process(context: ProcessingContext):
    # Check if this is a thread request
    if context.thread_id:
        # Load cached dataset from thread service
        dataset = await thread_service.get_thread_dataset(context.thread_id)

        if dataset:
            query_context, raw_results = dataset

            # Switch to thread session for conversation history
            thread_info = await thread_service.get_thread(context.thread_id)
            context.session_id = thread_info['thread_session_id']

            # Convert raw results to retrieved_docs format
            context.retrieved_docs = raw_results

            # Skip normal retrieval
            return context

    # Normal retrieval for non-thread requests
    # ... existing retrieval logic ...
```

#### Response Processor (`server/services/chat_handlers/response_processor.py`)

Stores retrieved documents in message metadata for thread creation.

**Metadata Storage:**
```python
metadata = {
    "adapter_name": adapter_name,
    "client_ip": client_ip,
    "pipeline_processing_time": processing_time,
    "original_query": message,
    "retrieved_docs": retrieved_docs,        # Raw results for threading
    "template_id": template_id,              # From first doc metadata
    "parameters_used": parameters_used       # Query parameters
}
```

#### Conversation History Handler (`server/services/chat_handlers/conversation_history_handler.py`)

Updated to return message IDs for thread creation.

**Key Changes:**
```python
async def store_turn(...) -> tuple[Optional[Any], Optional[Any]]:
    # Store conversation turn
    result = await chat_history_service.add_conversation_turn(...)

    # Return (user_message_id, assistant_message_id)
    return result
```

### 3. Database Schema

#### conversation_threads Table

```sql
CREATE TABLE conversation_threads (
    id TEXT PRIMARY KEY,
    parent_message_id TEXT NOT NULL,
    parent_session_id TEXT NOT NULL,
    thread_session_id TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    query_context TEXT,              -- JSON string
    dataset_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    metadata_json TEXT
);

-- Indexes for efficient querying
CREATE INDEX idx_conversation_threads_parent_message ON conversation_threads(parent_message_id);
CREATE INDEX idx_conversation_threads_parent_session ON conversation_threads(parent_session_id);
CREATE INDEX idx_conversation_threads_thread_session ON conversation_threads(thread_session_id);
CREATE INDEX idx_conversation_threads_expires_at ON conversation_threads(expires_at);
```

#### thread_datasets Collection (Database Fallback)

```javascript
{
    _id: ObjectId,
    id: "thread_dataset_{thread_id}",
    data: Binary,                    // gzip compressed JSON
    created_at: ISODate,
    expires_at: ISODate
}
```

### 4. API Endpoints

#### POST /api/threads

Create a thread from a parent message.

**Request:**
```json
{
    "message_id": "msg_123",
    "session_id": "session_456"
}
```

**Response:**
```json
{
    "thread_id": "thread_789",
    "thread_session_id": "thread_session_xyz",
    "parent_message_id": "msg_123",
    "parent_session_id": "session_456",
    "adapter_name": "intent-customer-support",
    "created_at": "2025-01-19T14:30:00Z",
    "expires_at": "2025-01-20T14:30:00Z"
}
```

#### GET /api/threads/{thread_id}

Retrieve thread information.

**Response:**
```json
{
    "thread_id": "thread_789",
    "thread_session_id": "thread_session_xyz",
    "parent_message_id": "msg_123",
    "parent_session_id": "session_456",
    "adapter_name": "intent-customer-support",
    "created_at": "2025-01-19T14:30:00Z",
    "expires_at": "2025-01-20T14:30:00Z"
}
```

#### DELETE /api/threads/{thread_id}

Delete a thread and its dataset.

**Response:**
```json
{
    "status": "success",
    "message": "Thread deleted successfully",
    "thread_id": "thread_789"
}
```

#### POST /v1/chat (with thread_id)

Send a message in a thread context.

**Request:**
```json
{
    "messages": [
        {"role": "user", "content": "What about pricing?"}
    ],
    "stream": true,
    "thread_id": "thread_789"
}
```

## Data Flow

### Thread Creation Flow

```
1. User clicks "Start Thread" on assistant message
   ↓
2. Frontend calls createThread(messageId, sessionId)
   ↓
3. Backend retrieves message from chat history
   ↓
4. Extracts retrieved_docs from message metadata
   ↓
5. ThreadDatasetService stores dataset with TTL
   - Redis: SET thread_dataset:{thread_id} <compressed_data> EX {ttl_seconds}
   - Database: INSERT into thread_datasets
   ↓
6. ThreadService creates thread record
   - Generates unique thread_id and thread_session_id
   - Stores in conversation_threads table
   ↓
7. Returns ThreadInfo to frontend
   ↓
8. Frontend updates message and conversation state
```

### Thread Usage Flow

```
1. User sends message in thread context
   ↓
2. Frontend includes thread_id in chat request
   ↓
3. ContextRetrievalStep checks for thread_id
   ↓
4. ThreadService.get_thread_dataset(thread_id)
   - Redis: GET thread_dataset:{thread_id}
   - Database: SELECT from thread_datasets WHERE id = {dataset_key}
   ↓
5. Decompress and parse dataset
   ↓
6. Switch session_id to thread_session_id
   ↓
7. Use cached dataset instead of querying database
   ↓
8. Process follow-up question on cached data
   ↓
9. Return response in thread context
```

### Cascade Deletion Flow

```
1. User deletes parent conversation
   ↓
2. ChatHistoryService.clear_conversation_history(session_id)
   ↓
3. Query all threads: find_many("conversation_threads", {"parent_session_id": session_id})
   ↓
4. For each thread:
   - Delete dataset: delete_one("thread_datasets", {"id": dataset_key})
   ↓
5. Delete thread records: delete_many("conversation_threads", {"parent_session_id": session_id})
   ↓
6. Delete conversation messages
   ↓
7. Clear session tracking
```

## Adapter Capability Detection

Only specific adapter types support threading.

**Supported:**
- Intent adapters (`intent-*`)
- QA adapters (`qa-*`)
- Any adapter with `supports_threading: true` in config

**Not Supported:**
- Conversational adapters (`conversational-*`)
- Multimodal adapters (`multimodal-*`)
- File adapters

**Detection Logic:**
```python
# server/adapters/capabilities.py
def for_standard_retriever(adapter_name: str) -> AdapterCapabilities:
    supports_threading = (
        adapter_name.startswith('intent-') or
        adapter_name.startswith('qa-') or
        'qa' in adapter_name.lower()
    ) and not (
        'conversational' in adapter_name.lower() or
        'multimodal' in adapter_name.lower()
    )

    return AdapterCapabilities(supports_threading=supports_threading)
```

## Configuration

### config.yaml

```yaml
conversation_threading:
  enabled: true
  dataset_ttl_hours: 24           # Global default TTL
  storage_backend: "redis"        # redis or database
  redis_key_prefix: "thread_dataset:"
```

### Environment Variables

```bash
# Redis configuration (if using Redis storage)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # Optional
```

## Frontend Integration

### Types (`clients/chat-app/src/types/index.ts`)

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

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  threadInfo?: ThreadInfo;
  supportsThreading?: boolean;
}

interface Conversation {
  sessionId: string;
  messages: Message[];
  currentThreadId?: string;
  currentThreadSessionId?: string;
}
```

### Thread Service (`clients/chat-app/src/services/threadService.ts`)

```typescript
class ThreadService {
  async createThread(messageId: string, sessionId: string): Promise<ThreadInfo>
  async getThreadInfo(threadId: string): Promise<ThreadInfo>
  async deleteThread(threadId: string): Promise<void>
}
```

### UI Component (`clients/chat-app/src/components/Message.tsx`)

```typescript
// "Start Thread" button shown when:
// 1. Message is from assistant
// 2. supportsThreading is true
// 3. threadInfo is not already set
// 4. sessionId is available

{onStartThread && message.supportsThreading && !message.threadInfo && sessionId && (
  <button onClick={() => onStartThread(message.id, sessionId)}>
    <MessageSquare className="h-4 w-4" />
    Start Thread
  </button>
)}
```

## Performance Considerations

### Storage Efficiency

**Compression:**
- gzip compression reduces dataset size by ~70-80%
- Example: 100KB raw JSON → ~20-30KB compressed

**Redis vs Database:**
- Redis: O(1) lookup, automatic TTL expiration
- Database: O(log n) lookup with indexes, manual cleanup required

### Memory Usage

**Redis Memory:**
- Average dataset: ~30KB compressed
- 1000 active threads: ~30MB
- TTL ensures automatic cleanup

**Database Storage:**
- SQLite: Minimal overhead, single file
- MongoDB: Document-based, efficient indexing

### Query Performance

**Thread Retrieval:**
- Redis: < 1ms average
- SQLite: < 5ms with indexes
- MongoDB: < 10ms with indexes

**Dataset Caching:**
- Eliminates database query (typically 50-200ms)
- Reduces load on vector store/SQL database
- Improves response time for follow-up questions

## Expiration and Cleanup

### Automatic Expiration

**Redis:**
- Built-in TTL expiration
- No manual cleanup required
- Configurable per-thread or global default

**Database:**
- Manual cleanup via scheduled task
- `cleanup_expired_threads()` method
- `cleanup_expired_datasets()` method

### Cleanup Schedule

Recommended cleanup intervals:
- Threads: Every 6 hours
- Datasets: Every 12 hours
- Expired sessions: Daily

**Example Cleanup Task:**
```python
async def cleanup_task():
    while True:
        # Clean up expired threads
        deleted_threads = await thread_service.cleanup_expired_threads()

        # Clean up expired datasets
        deleted_datasets = await thread_dataset_service.cleanup_expired_datasets()

        logger.info(f"Cleanup: {deleted_threads} threads, {deleted_datasets} datasets")

        # Wait 6 hours
        await asyncio.sleep(6 * 60 * 60)
```

### Cascade Deletion

**Parent Conversation Deleted:**
1. Query all threads for session
2. Delete thread datasets
3. Delete thread records
4. Delete conversation messages

**Thread Explicitly Deleted:**
1. Delete dataset from Redis/database
2. Delete thread record
3. Keep parent conversation intact

## Error Handling

### Thread Creation Failures

**Message Not Found:**
```json
{
  "error": "Message not found or has no retrieved documents",
  "message_id": "msg_123"
}
```

**Storage Failure:**
- Fallback to database if Redis unavailable
- Return error if both storage backends fail

### Thread Usage Failures

**Thread Expired:**
- Return 404 Not Found
- Frontend shows expiration message
- Option to create new thread

**Dataset Missing:**
- Fallback to normal retrieval
- Log warning about missing dataset
- Continue processing request

### Cascade Deletion Failures

**Partial Deletion:**
- Continue with remaining deletions
- Log warnings for failed operations
- Return success with partial results

## Security Considerations

### Access Control

**Thread Creation:**
- Requires valid API key
- Validates parent message ownership
- Checks adapter supports threading

**Thread Access:**
- Thread ID is globally unique
- No cross-session access validation (stateless)
- Relies on session-based security

### Data Privacy

**Dataset Storage:**
- Compressed but not encrypted
- TTL ensures automatic deletion
- No persistent storage beyond expiration

**Session Isolation:**
- Each thread has unique session ID
- Thread conversations isolated from parent
- No cross-thread data access

## Monitoring and Debugging

### Logging

**Thread Creation:**
```
INFO - Created thread thread_789 for message msg_123
INFO - Stored dataset with key thread_dataset:thread_789 (TTL: 24h)
```

**Thread Usage:**
```
INFO - Loading dataset for thread thread_789
INFO - Switched to thread session thread_session_xyz
```

**Cleanup:**
```
INFO - Deleted 5 expired threads
INFO - Deleted 5 expired datasets
```

### Metrics to Track

- Active threads count
- Thread creation rate
- Thread usage rate
- Dataset hit/miss ratio
- Storage backend performance
- Expiration cleanup effectiveness

### Debug Mode

Enable verbose logging in config:
```yaml
general:
  verbose: true
```

## Migration Guide

### Enabling Threading on Existing System

1. **Update Configuration:**
   ```yaml
   conversation_threading:
     enabled: true
     dataset_ttl_hours: 24
     storage_backend: "redis"
   ```

2. **Database Migration:**
   - SQLite: Table created automatically on initialization
   - MongoDB: Collection created on first insert
   - No manual migration required

3. **Frontend Update:**
   - Update to latest client version
   - No localStorage migration needed

4. **API Compatibility:**
   - All endpoints backward compatible
   - Thread parameters optional
   - Existing conversations unaffected

## Best Practices

### When to Use Threading

**Good Use Cases:**
- Follow-up questions on search results
- Exploring specific documents in dataset
- Drilling down into QA responses
- Iterative refinement of intent queries

**Not Recommended:**
- Conversational chat (use normal flow)
- File-based conversations (not supported)
- Long-running analysis (threads expire)

### TTL Configuration

**Short TTL (1-6 hours):**
- Low memory usage
- Frequent cleanup
- Good for high-volume systems

**Long TTL (24-72 hours):**
- Better user experience
- Higher memory usage
- Good for low-volume systems

### Storage Backend Selection

**Choose Redis when:**
- High thread creation rate
- Need automatic expiration
- Have Redis infrastructure
- Want optimal performance

**Choose Database when:**
- Low thread creation rate
- Need persistent storage
- No Redis available
- Want simpler infrastructure

## Troubleshooting

### Thread Creation Fails

**Symptom:** "Message not found or has no retrieved documents"
- **Cause:** Message doesn't have retrieved_docs in metadata
- **Fix:** Ensure adapter supports threading and stores retrieved_docs

### Dataset Not Found

**Symptom:** 404 when using thread_id
- **Cause:** Thread expired or dataset deleted
- **Fix:** Check TTL configuration, verify Redis/database connectivity

### Cascade Deletion Error

**Symptom:** "Error deleting threads for session"
- **Cause:** Database service method mismatch
- **Fix:** Use `find_many` instead of `find`, ensure database service initialized

### Memory Issues

**Symptom:** High Redis memory usage
- **Cause:** Too many active threads or long TTL
- **Fix:** Reduce TTL, implement cleanup task, increase Redis memory

## Future Enhancements

### Potential Improvements

1. **Thread Branching:**
   - Create sub-threads from thread messages
   - Tree structure for conversations

2. **Thread Merging:**
   - Combine multiple threads
   - Unified context across threads

3. **Thread Sharing:**
   - Share threads between users
   - Collaborative thread exploration

4. **Enhanced Metadata:**
   - Thread titles/descriptions
   - Tags and categories
   - Custom expiration per thread

5. **Analytics:**
   - Thread usage statistics
   - Popular thread patterns
   - Dataset reuse metrics

## Related Documentation

- [Pipeline Inference Architecture](./pipeline-inference-architecture.md)
- [Intent SQL RAG System](./intent-sql-rag-system.md)
- [SQLite Schema](./sqlite-schema.md)
- [Vector Retriever Architecture](./vector-retriever-architecture.md)
- [Conversation History](./conversation_history.md)
