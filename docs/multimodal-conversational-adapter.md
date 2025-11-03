# Multimodal Conversational Adapter Guide

## Overview

The multimodal conversational adapter (`conversational-multimodal`) combines conversation history management with file-based retrieval capabilities. This enables ChatGPT-like conversations where users can:

- Maintain conversation history across multiple messages
- Upload files (PDFs, images, documents, etc.)
- Query uploaded files during conversations
- Have context-aware responses that use both conversation history and file content

## Architecture Overview

The multimodal adapter is a hybrid system that:

1. **Maintains conversation history** (like `conversational-passthrough`)
2. **Processes files from request** (stateless - no server-side tracking)
3. **Retrieves relevant file chunks** (from vector stores like ChromaDB)
4. **Combines conversation context with file chunks** for LLM processing

**Note:** File tracking is managed by the frontend (localStorage). The backend is stateless and only processes `file_ids` sent with each request. This eliminates the need for Redis and simplifies deployment.

```
┌─────────────────┐
│   Chat Client   │
│   (chat-app)    │
└────────┬────────┘
         │
         │ 1. Upload file → GET file_id
         │ 2. Send message + file_ids
         │
         ▼
┌─────────────────────────────────────┐
│       API Endpoints                  │
│  - POST /api/files/upload            │
│  - POST /v1/chat (with file_ids)    │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   PipelineChatService               │
│   - Creates ProcessingContext        │
│   - Includes: message, file_ids,     │
│     session_id                        │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   ContextRetrievalStep               │
│   - Detects multimodal adapter       │
│   - Passes file_ids + session_id      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│   MultimodalImplementation          │
│   (conversational-multimodal)        │
│   - Stateless design                 │
│   - Uses file_ids from request       │
└─────────────┬───────────────────────┘
              │
              │ file_ids from frontend
              │
              ▼
┌─────────────────────────┐
│  FileVectorRetriever     │
│  (Vector store query)   │
│                          │
│ - Query chunks by        │
│   similarity             │
│ - Return top chunks      │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────┐
│  File Chunks Returned │
│  + Conversation Hist  │
└──────────┬────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   LLM Inference      │
              │   - Full context     │
              │   - Conversation +   │
              │     file chunks      │
              └──────────────────────┘
```

## Complete Flow

### Phase 1: File Upload and Processing

**Step 1: User uploads a file**

```typescript
// Frontend: chat-app sends file to backend
POST /api/files/upload
Headers: X-API-Key: <api_key>
Body: FormData with file
```

**Step 2: Backend processes file**

1. `FileProcessingService.quick_upload()` stores file
2. File metadata saved to `FileMetadataStore` (SQLite/MongoDB)
3. Content extracted (text from PDFs, images processed via vision API)
4. Content chunked using configured strategy (semantic or fixed)
5. Chunks embedded and indexed into vector store (ChromaDB)
6. Returns `file_id` to frontend

**Step 3: Frontend stores file_id**

- Frontend adds file to conversation's `attachedFiles` array
- File appears in UI with status (processing/completed)

### Phase 2: Conversation with File Context

**Step 4: User sends message with file context**

```typescript
// Frontend: chat-app sends message with file_ids
POST /v1/chat
Headers: 
  - X-API-Key: <api_key>
  - X-Session-ID: <session_id>
Body: {
  "messages": [...],
  "file_ids": ["file_123", "file_456"],  // File IDs to include
  "stream": true
}
```

**Step 5: PipelineChatService creates ProcessingContext**

```python
context = ProcessingContext(
    message=last_user_message,
    adapter_name="conversational-multimodal",
    session_id=session_id,
    api_key=api_key,
    file_ids=["file_123", "file_456"]  # From request
)
```

**Step 6: ContextRetrievalStep routes to multimodal adapter**

The `ContextRetrievalStep` checks:
- Is adapter type `passthrough`? → Skip for most passthrough adapters
- Exception: `conversational-multimodal` → Execute retrieval

```python
# In ContextRetrievalStep.should_execute()
if adapter_config.get('type') == 'passthrough':
    # Allow multimodal adapter to execute (it needs file retrieval)
    if context.adapter_name != 'conversational-multimodal':
        return False  # Skip retrieval
```

**Step 7: ContextRetrievalStep passes context to adapter**

```python
# Pass file_ids and session_id to adapter
retriever_kwargs = {
    'file_ids': context.file_ids,
    'session_id': context.session_id,
    'api_key': context.api_key
}

docs = await retriever.get_relevant_context(
    query=context.message,
    **retriever_kwargs
)
```

### Phase 3: Multimodal Adapter Processing

**Step 8: MultimodalImplementation processes file_ids from request**

```python
# In MultimodalImplementation.get_relevant_context()

# Backend is stateless - just use file_ids from the request
# No server-side tracking needed (frontend manages this in localStorage)

# If no file_ids provided, return empty context (conversation-only mode)
if not file_ids:
    return []
```

**Frontend Storage (localStorage):**

```javascript
// Frontend manages file associations
conversation = {
  id: "conv_123",
  sessionId: "session_456",
  attachedFiles: [
    { file_id: "file_123", filename: "doc.pdf" },
    { file_id: "file_456", filename: "image.jpg" }
  ]
}

// Frontend sends file_ids with every message
const fileIds = conversation.attachedFiles.map(f => f.file_id);
await api.streamChat(message, true, fileIds);
```

**Step 9: MultimodalImplementation retrieves file chunks**

```python
# Use FileVectorRetriever to get relevant chunks
chunks = await file_retriever.get_relevant_context(
    query=query,  # User's message
    api_key=api_key,
    file_ids=all_file_ids,  # All files in session
    collection_name=None  # Auto-detect collections by file_id
)
```

**Step 10: FileVectorRetriever queries vector store**

1. Get collection names for each file_id from `FileMetadataStore`
2. For each collection:
   - Generate query embedding
   - Search vector store with similarity search
   - Filter results by file_id (if multiple files)
   - Return top N chunks (based on `return_results` config)

**Step 11: Format results**

Chunks are formatted with metadata:
```python
{
    "content": "chunk text content...",
    "metadata": {
        "file_id": "file_123",
        "chunk_id": "chunk_abc",
        "chunk_index": 5,
        "confidence": 0.85
    }
}
```

**Step 12: Return to pipeline**

- Empty list if no files → Pure conversation mode (like conversational-passthrough)
- List of chunks if files present → Combined conversation + file context

### Phase 4: LLM Processing

**Step 13: ContextRetrievalStep formats context**

```python
# Format chunks for LLM
formatted_context = _format_context(docs, "conversational-multimodal")

# Clean format (no citations) to prevent LLM from adding markers:
# chunk_content_1
# 
# chunk_content_2
# 
# ...
```

**Step 14: Conversation history retrieved**

`ChatHistoryService` retrieves conversation messages for session:
```python
context_messages = await chat_history_service.get_conversation_history(
    session_id=session_id,
    limit=max_conversation_messages  # Dynamic based on model context window
)
```

**Step 15: LLM receives full context**

The LLM prompt includes:

```
System Prompt: ...

Conversation History:
- User: "Hello, I uploaded a document about renewable energy"
- Assistant: "I'm ready to help you with questions about renewable energy."
- User: "What are the main types mentioned?"  # Current message

Relevant Document Context:
[Chunk 1 from file_123]
[Chunk 2 from file_123]
[Chunk 3 from file_456]

User Query: "What are the main types mentioned?"
```

**Step 16: LLM generates response**

- Uses conversation history for context continuity
- Uses file chunks to answer document-specific questions
- Streams response back to frontend

### Phase 5: Response and History Storage

**Step 17: Response streamed to frontend**

```python
# Streaming response chunks
async for chunk in chat_service.process_chat_stream(...):
    yield chunk  # Text chunks streamed in real-time
```

**Step 18: Conversation turn saved**

```python
await chat_history_service.add_conversation_turn(
    session_id=session_id,
    user_message=message,
    assistant_response=full_response,
    api_key=api_key,
    metadata={
        "file_ids": file_ids,  # Track which files were used
        "chunk_count": len(chunks)
    }
)
```

## Key Components

### 1. MultimodalImplementation

**Location:** `server/implementations/passthrough/multimodal/multimodal_implementation.py`

**Responsibilities:**
- Extends `BaseRetriever` for pipeline compatibility
- Integrates `FileVectorRetriever` for chunk retrieval
- **Stateless design** - processes file_ids from request only
- Returns empty context when no files (conversation-only mode)
- Returns file chunks when file_ids are provided

**Key Design Decision:** No server-side file tracking. The frontend manages file associations in localStorage, making the backend stateless and simpler to deploy.

### 2. FileVectorRetriever

**Location:** `server/retrievers/implementations/file/file_retriever.py`

**Responsibilities:**
- Queries vector store (ChromaDB) for relevant chunks
- Supports multiple file_ids in single query
- Filters chunks by file_id
- Returns top N chunks by similarity score

### 4. ContextRetrievalStep

**Location:** `server/inference/pipeline/steps/context_retrieval.py`

**Key Changes for Multimodal:**
- Allows `conversational-multimodal` to execute (exception to passthrough skip)
- Passes `file_ids` and `session_id` to adapter
- Formats chunks with clean format (no citations)

## Configuration

### Adapter Configuration (adapters.yaml)

```yaml
- name: "conversational-multimodal"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "multimodal"
  implementation: "implementations.passthrough.multimodal.MultimodalImplementation"
  inference_provider: "ollama_cloud"
  model: "minimax-m2:cloud"
  embedding_provider: "ollama"
  vision_provider: "gemini"
  
  config:
    # File adapter configuration
    storage_backend: "filesystem"
    storage_root: "./uploads"
    max_file_size: 52428800  # 50MB
    
    chunking_strategy: "semantic"
    chunk_size: 1000
    chunk_overlap: 200
    
    vector_store: "chroma"
    collection_prefix: "files_"
    
    confidence_threshold: 0.3
    max_results: 5
    return_results: 3
```

### Backend Configuration

**No Redis required!** The multimodal adapter is stateless and doesn't need server-side session tracking.

The only configuration needed is for the vector store and file processing (same as file-document-qa adapter).

## Usage Examples

### Example 1: Simple Conversation (No Files)

```python
# Request
POST /v1/chat
{
  "messages": [{"role": "user", "content": "Hello!"}],
  "file_ids": []
}

# Flow:
# 1. MultimodalImplementation.get_relevant_context()
# 2. No files in session → returns []
# 3. Pure conversation mode (like conversational-passthrough)
# 4. LLM receives only conversation history
```

### Example 2: Upload File and Query

```python
# Step 1: Upload file
POST /api/files/upload
# Returns: {"file_id": "file_abc123", ...}

# Step 2: Send message with file
POST /v1/chat
{
  "messages": [{"role": "user", "content": "Summarize this document"}],
  "file_ids": ["file_abc123"]
}

# Flow:
# 1. Frontend sends file_ids with message: ["file_abc123"]
# 2. Backend (MultimodalImplementation) receives file_ids
# 3. FileVectorRetriever queries chunks from file_abc123
# 4. Returns top 3 chunks by similarity
# 5. LLM receives conversation history + file chunks
```

### Example 3: Multi-Turn Conversation with Files

```python
# Turn 1: Upload and ask
POST /v1/chat
{
  "messages": [{"role": "user", "content": "What's in this PDF?"}],
  "file_ids": ["file_123"]
}
# Files tracked: ["file_123"]

# Turn 2: Follow-up question
POST /v1/chat
{
  "messages": [
    {"role": "user", "content": "What's in this PDF?"},
    {"role": "assistant", "content": "The PDF discusses..."},
    {"role": "user", "content": "Can you explain section 3?"}
  ],
  "file_ids": []  # No new files, but file_123 still in session
}
# Files tracked: ["file_123"] (from previous turn)
# Query searches chunks from file_123 again

# Turn 3: Upload another file
POST /v1/chat
{
  "messages": [...],
  "file_ids": ["file_456"]  # New file added
}
# Files tracked: ["file_123", "file_456"]
# Query searches chunks from both files
```

## Benefits

1. **Persistent File Context**: Files stay associated with conversation session across multiple turns
2. **Automatic Context Management**: No need to resend file_ids in every message
3. **Efficient Retrieval**: Only retrieves relevant chunks (semantic search)
4. **Conversation Continuity**: Maintains full conversation history alongside file context
5. **Multi-File Support**: Can query across multiple files in single conversation
6. **Fallback to Pure Conversation**: Works like conversational-passthrough when no files present

## Troubleshooting

### Issue: Files not found

**Symptoms:** No chunks returned even though file_ids were provided

**Check:**
1. Frontend is sending file_ids with message (check browser console/network tab)
2. File processing status (check `/api/files/{file_id}`)
3. File exists and belongs to the API key being used

**Solution:**
- Verify frontend is passing `attachedFiles` file IDs: `fileIds = conversation.attachedFiles.map(f => f.file_id)`
- Check file processing completed: `processing_status: "completed"`
- Verify file ownership matches API key

### Issue: Chunks not retrieved

**Symptoms:** File exists but no chunks returned

**Check:**
1. File was indexed: `collection_name` in file metadata
2. Vector store connection
3. Chunking completed successfully

**Solution:**
- Re-upload file if indexing failed
- Verify vector store (ChromaDB) is running
- Check adapter logs for chunk retrieval errors

### Issue: Wrong chunks returned

**Symptoms:** Irrelevant chunks in response

**Check:**
1. `confidence_threshold` in adapter config (too low?)
2. `return_results` setting (too many chunks?)
3. Query embedding quality

**Solution:**
- Increase `confidence_threshold` (e.g., 0.3 → 0.5)
- Reduce `return_results` (e.g., 5 → 3)
- Try more specific queries

## Related Documentation

- [Conversation History System](./conversation_history.md) - How conversation history works
- [File Adapter Guide](./file-adapter-guide.md) - File upload and processing details
- [Vector Store Architecture](./vector_store_architecture.md) - How vector stores work
- [Pipeline Inference Architecture](./pipeline-inference-architecture.md) - Pipeline system overview

